"""
通用网页侦察器

复用同一套方法论：
1. 传输层：status / final_url / Last-Modified / ETag
2. 结构层：title / meta / scripts / styles / anchors
3. 源码层：同源脚本探针
4. 语义层：extractor 解析
"""

import hashlib
import json
import re
from datetime import datetime
from typing import Any, Dict, List
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree as ET

import aiohttp
from bs4 import BeautifulSoup

from utils.recon_registry import build_signal_extractor, get_allowed_site_keys, infer_extractor_name
from utils.source_probe import merge_signal_maps, pick_interesting_links, probe_script_assets


SITEMAP_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}


class SurfaceRecon:
    def __init__(self, config: Dict):
        self.config = config
        self.session = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(
                total=self.config.get("monitoring", {}).get("timeout_seconds", 30)
            )
            user_agent = self.config.get("browser", {}).get(
                "user_agent",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            )
            self.session = aiohttp.ClientSession(
                timeout=timeout,
                headers={"User-Agent": user_agent},
            )
        return self.session

    async def run(self, surfaces: List[Dict], expand_discovered: int = 0) -> Dict[str, Any]:
        session = await self._get_session()
        rows = []
        requested_urls = set()

        for surface in surfaces:
            snapshot = await self._fetch_surface(session, surface)
            rows.append(snapshot)
            requested_urls.add(snapshot["url"])

        if expand_discovered > 0:
            discovered_surfaces = []
            for row in rows:
                for link in row.get("signals", {}).get("discovered_links", []):
                    if link in requested_urls:
                        continue
                    requested_urls.add(link)
                    discovered_surfaces.append(
                        {
                            "name": self._name_from_url(link),
                            "url": link,
                            "parser": "html",
                            "extractor": row.get("extractor"),
                            "allowed_site_keys": row.get("allowed_site_keys", []),
                            "script_probe_limit": row.get("script_probe_limit", 3),
                            "discovered_from": row.get("url"),
                        }
                    )
                    if len(discovered_surfaces) >= expand_discovered:
                        break
                if len(discovered_surfaces) >= expand_discovered:
                    break

            for surface in discovered_surfaces:
                rows.append(await self._fetch_surface(session, surface))

        return {
            "timestamp": datetime.now().isoformat(),
            "surfaces": rows,
        }

    async def _fetch_surface(self, session: aiohttp.ClientSession, surface: Dict) -> Dict[str, Any]:
        parser = surface.get("parser", "html")
        extractor_name = surface.get("extractor") or infer_extractor_name(surface["url"])
        signal_extractor = build_signal_extractor(extractor_name)
        allowed_site_keys = surface.get("allowed_site_keys") or get_allowed_site_keys(extractor_name)

        async with session.get(surface["url"], allow_redirects=True) as response:
            content = await response.text(errors="ignore")
            final_url = str(response.url)
            headers = response.headers
            base = {
                "name": surface.get("name") or self._name_from_url(surface["url"]),
                "url": surface["url"],
                "final_url": final_url,
                "parser": parser,
                "extractor": extractor_name,
                "allowed_site_keys": allowed_site_keys,
                "script_probe_limit": surface.get("script_probe_limit", 4),
                "status_code": response.status,
                "content_type": headers.get("Content-Type", ""),
                "last_modified": headers.get("Last-Modified", ""),
                "etag": headers.get("ETag", ""),
                "observed_at": datetime.now().isoformat(),
                "discovered_from": surface.get("discovered_from", ""),
                "html_hash": hashlib.md5(content.encode("utf-8")).hexdigest(),
            }

            if parser == "sitemap" or "xml" in base["content_type"]:
                parsed = self._parse_sitemap(content)
                signals = parsed.get("signals", {})
                return {
                    **base,
                    **parsed,
                    "source_time": base["last_modified"],
                    "source_time_type": "http_last_modified" if base["last_modified"] else "unknown",
                    "signal_counts": {
                        "urls": len(signals.get("urls", [])),
                    },
                }

            parsed = self._parse_html(content, final_url)
            signals = merge_signal_maps(parsed.get("signals", {}), signal_extractor(content, parsed["normalized_text"]))
            discovered_links = pick_interesting_links(
                final_url,
                [item["href"] for item in parsed.get("anchors", [])],
                allowed_site_keys=allowed_site_keys or None,
                limit=20,
            )
            if discovered_links:
                signals["discovered_links"] = discovered_links

            script_probe = await probe_script_assets(
                session,
                final_url,
                signals.get("scripts", []),
                lambda script_text: signal_extractor(script_text, ""),
                limit=surface.get("script_probe_limit", 4),
            )
            signals = merge_signal_maps(signals, script_probe.get("signals", {}))
            signals["script_probe"] = script_probe.get("probe", {})

            source_time = base["last_modified"] or ""
            source_time_type = "http_last_modified" if source_time else "unknown"
            article_dates = signals.get("article_dates", [])
            if not source_time and article_dates:
                source_time = article_dates[0]
                source_time_type = "page_date_signal"

            return {
                **base,
                **parsed,
                "signals": signals,
                "source_time": source_time,
                "source_time_type": source_time_type,
                "signal_counts": {
                    "scripts": len(signals.get("scripts", [])),
                    "styles": len(signals.get("styles", [])),
                    "anchors": len(signals.get("anchors", [])),
                    "discovered_links": len(signals.get("discovered_links", [])),
                    "script_probe": (signals.get("script_probe") or {}).get("probed_count", 0),
                },
            }

    def _parse_html(self, html: str, base_url: str) -> Dict[str, Any]:
        soup = BeautifulSoup(html, "html.parser")

        title = ""
        if soup.title and soup.title.string:
            title = " ".join(soup.title.string.split())

        metas = {}
        for meta in soup.find_all("meta"):
            key = meta.get("name") or meta.get("property")
            value = meta.get("content")
            if key and value:
                metas[key] = value.strip()

        scripts = self._collect_urls(soup.find_all("script", {"src": True}), "src", base_url)
        styles = self._collect_urls(
            soup.find_all("link", {"href": True}),
            "href",
            base_url,
            predicate=lambda tag: tag.get("rel") and "stylesheet" in tag.get("rel"),
        )
        anchors = self._collect_links(soup, base_url)
        normalized_text = self._normalize_text(soup.get_text("\n", strip=True))

        return {
            "title": title,
            "text_hash": hashlib.md5(normalized_text.encode("utf-8")).hexdigest(),
            "normalized_text": normalized_text,
            "anchors": anchors,
            "signals": {
                "meta": metas,
                "scripts": scripts,
                "styles": styles,
                "anchors": anchors,
                "text_preview": [line for line in normalized_text.splitlines() if line.strip()][:20],
            },
        }

    def _parse_sitemap(self, xml_content: str) -> Dict[str, Any]:
        urls: List[str] = []
        try:
            root = ET.fromstring(xml_content.encode("utf-8"))
            urls = sorted(
                {loc.text.strip() for loc in root.findall(".//sm:loc", SITEMAP_NS) if loc.text}
            )
        except Exception:
            urls = sorted(set(re.findall(r"<loc>(.*?)</loc>", xml_content)))

        normalized_text = "\n".join(urls)
        return {
            "title": "Sitemap",
            "text_hash": hashlib.md5(normalized_text.encode("utf-8")).hexdigest(),
            "normalized_text": normalized_text,
            "signals": {
                "urls": urls,
                "url_count": len(urls),
                "text_preview": urls[:20],
            },
        }

    def _collect_urls(self, tags, attr: str, base_url: str, predicate=None) -> List[str]:
        urls = []
        for tag in tags:
            if predicate and not predicate(tag):
                continue
            raw = tag.get(attr)
            if raw:
                urls.append(urljoin(base_url, raw))
        return sorted(set(urls))

    def _collect_links(self, soup: BeautifulSoup, base_url: str) -> List[Dict[str, str]]:
        items = []
        for anchor in soup.find_all("a", href=True):
            items.append(
                {
                    "href": urljoin(base_url, anchor["href"]),
                    "text": " ".join(anchor.get_text(" ", strip=True).split())[:120],
                }
            )
        dedup = {}
        for item in items:
            dedup[item["href"]] = item
        return [dedup[key] for key in sorted(dedup.keys())]

    def _normalize_text(self, text: str) -> str:
        lines = []
        for line in text.splitlines():
            compact = re.sub(r"\s+", " ", line).strip()
            if compact:
                lines.append(compact)
        return "\n".join(lines)

    def _name_from_url(self, url: str) -> str:
        parsed = urlparse(url)
        path = parsed.path.strip("/") or "home"
        return f"{parsed.netloc}/{path}"

    async def cleanup(self):
        if self.session and not self.session.closed:
            await self.session.close()


def render_surface_recon_markdown(title: str, surfaces: List[Dict], generated_at: str) -> str:
    sections = [
        f"# {title}",
        "",
        f"- Generated At: {generated_at}",
        f"- Surface Count: {len(surfaces)}",
        "",
    ]

    for surface in surfaces:
        signals = surface.get("signals", {})
        sections.extend(
            [
                f"## {surface.get('name')}",
                "",
                f"- URL: {surface.get('url')}",
                f"- Final URL: {surface.get('final_url')}",
                f"- Title: {surface.get('title') or '---'}",
                f"- Extractor: {surface.get('extractor')}",
                f"- Parser: {surface.get('parser')}",
                f"- Status Code: {surface.get('status_code')}",
                f"- Content Type: {surface.get('content_type') or '---'}",
                f"- Official Time: {surface.get('source_time') or '---'}",
                f"- Official Time Type: {surface.get('source_time_type')}",
                f"- Observed At: {surface.get('observed_at')}",
            ]
        )
        if surface.get("discovered_from"):
            sections.append(f"- Discovered From: {surface.get('discovered_from')}")

        for label, key, limit in [
            ("Models", "models", 12),
            ("Coding Signals", "coding_signals", 12),
            ("Commercial Actions", "commercial_actions", 10),
            ("Offerings", "offerings", 12),
            ("Prices", "prices", 12),
            ("Agent IDs", "agent_ids", 10),
            ("Route Patterns", "route_patterns", 10),
            ("API Families", "api_families", 12),
            ("Hidden Capabilities", "hidden_capabilities", 10),
            ("Pricing Paths", "pricing_paths", 10),
            ("Discovered Links", "discovered_links", 10),
            ("Plan Signals", "plan_signals", 6),
            ("Pricing Lines", "pricing_lines", 6),
            ("Coder Signals", "coder_signals", 6),
            ("Vision Signals", "vision_signals", 6),
            ("Agent Signals", "agent_signals", 6),
            ("Pricing Signals", "pricing_signals", 6),
            ("Headlines", "headline_lines", 8),
            ("Versions", "resource_versions", 8),
            ("Article Dates", "article_dates", 8),
            ("Dates", "dates", 8),
            ("URLs", "urls", 12),
        ]:
            values = [item for item in signals.get(key, []) if item][:limit]
            if values:
                sections.append(f"- {label}: " + " | ".join(values))

        probe = signals.get("script_probe") or {}
        if probe.get("probed_urls"):
            sections.append("- Script Probe: " + " | ".join(probe.get("probed_urls", [])[:6]))

        preview = signals.get("text_preview", [])[:5]
        if preview:
            sections.append("- Text Preview: " + " | ".join(preview))

        sections.append("")

    return "\n".join(sections).strip() + "\n"
