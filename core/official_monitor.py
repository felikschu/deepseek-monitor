"""
官方页面/文档监控模块

方法论：
1. 先抓 HTTP 响应头，记录 final_url / Last-Modified / ETag / Content-Type
2. 再抓页面源码，提取 title / meta / assets / anchors / 可见文本
3. 同时监控 sitemap 等结构化索引，扩大覆盖范围
4. 每次变化都区分 source_time（官方时间）与 observed_at（本地发现时间）
5. 为文本类变化生成可读的 diff 摘要，避免“只知道更新了，不知道改了什么”
"""

import hashlib
import json
import re
from datetime import datetime
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree as ET

import aiohttp
from bs4 import BeautifulSoup
from loguru import logger

from utils.deepseek_signal_extractor import extract_deepseek_signals
from utils.source_probe import merge_signal_maps, probe_script_assets


SITEMAP_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}


class OfficialMonitor:
    """监控 DeepSeek 官网与文档站的关键页面。"""

    def __init__(self, config: Dict, storage):
        self.config = config
        self.storage = storage
        self.session = None
        self.monitor_config = config.get("official_surfaces", {})
        self.results = {
            "timestamp": None,
            "changes": [],
            "surfaces": [],
        }

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

    async def check(self) -> Dict[str, Any]:
        if not self.monitor_config.get("enabled", True):
            return self.results

        self.results["timestamp"] = datetime.now().isoformat()
        pages = self.monitor_config.get("pages", [])
        if not pages:
            return self.results

        session = await self._get_session()

        for page in pages:
            try:
                snapshot = await self._fetch_surface(session, page)
                self.results["surfaces"].append(self._surface_summary(page, snapshot))

                previous = await self.storage.get_last_surface_snapshot(page["url"])
                change = self._build_change(page, previous, snapshot)
                if change:
                    self.results["changes"].append(change)

                await self.storage.save_surface_snapshot(
                    page["url"], page["name"], page["category"], snapshot
                )
            except Exception as exc:
                logger.warning(f"官方页面检查失败 {page.get('url')}: {exc}")

        return self.results

    async def _fetch_surface(self, session: aiohttp.ClientSession, page: Dict) -> Dict[str, Any]:
        url = page["url"]
        parser = page.get("parser", "html")

        async with session.get(url, allow_redirects=True) as response:
            content = await response.text()
            final_url = str(response.url)
            headers = response.headers

            base = {
                "url": url,
                "final_url": final_url,
                "status_code": response.status,
                "content_type": headers.get("Content-Type", ""),
                "last_modified": headers.get("Last-Modified", ""),
                "etag": headers.get("ETag", ""),
                "html_hash": hashlib.md5(content.encode("utf-8")).hexdigest(),
            }

            if parser == "sitemap" or "xml" in base["content_type"]:
                return {
                    **base,
                    **self._parse_sitemap(content),
                }

            parsed = self._parse_html(content, final_url)
            script_probe = await probe_script_assets(
                session,
                final_url,
                parsed.get("signals", {}).get("scripts", []),
                lambda script_text: extract_deepseek_signals(script_text),
            )
            parsed["signals"] = merge_signal_maps(parsed.get("signals", {}), script_probe.get("signals", {}))
            parsed["signals"]["script_probe"] = script_probe.get("probe", {})
            return {
                **base,
                **parsed,
            }

    def _parse_html(self, html: str, base_url: str) -> Dict[str, Any]:
        soup = BeautifulSoup(html, "html.parser")

        title = ""
        if soup.title and soup.title.string:
            title = " ".join(soup.title.string.split())

        metas = {}
        for meta in soup.find_all("meta"):
            key = meta.get("name") or meta.get("property")
            content = meta.get("content")
            if key and content:
                metas[key] = content.strip()

        scripts = self._collect_urls(soup.find_all("script", {"src": True}), "src", base_url)
        styles = self._collect_urls(
            soup.find_all("link", {"href": True}),
            "href",
            base_url,
            predicate=lambda tag: tag.get("rel") and "stylesheet" in tag.get("rel"),
        )
        anchors = self._collect_links(soup, base_url)

        normalized_text = self._normalize_text(soup.get_text("\n", strip=True))
        lines = [line for line in normalized_text.splitlines() if line.strip()]

        signals = {
            "meta": metas,
            "scripts": scripts,
            "styles": styles,
            "anchors": anchors,
            "text_preview": lines[:20],
        }
        deepseek_signals = extract_deepseek_signals(html, normalized_text)
        signals.update(deepseek_signals)

        return {
            "title": title,
            "text_hash": hashlib.md5(normalized_text.encode("utf-8")).hexdigest(),
            "normalized_text": normalized_text,
            "signals": signals,
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
            if not raw:
                continue
            urls.append(urljoin(base_url, raw))
        return sorted(set(urls))

    def _collect_links(self, soup: BeautifulSoup, base_url: str) -> List[Dict[str, str]]:
        items = []
        for anchor in soup.find_all("a", href=True):
            href = urljoin(base_url, anchor["href"])
            text = " ".join(anchor.get_text(" ", strip=True).split())
            items.append({"href": href, "text": text[:120]})

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

    def _surface_summary(self, page: Dict, snapshot: Dict) -> Dict[str, Any]:
        signals = snapshot.get("signals", {})
        return {
            "name": page["name"],
            "category": page["category"],
            "url": page["url"],
            "final_url": snapshot.get("final_url"),
            "title": snapshot.get("title"),
            "last_modified": snapshot.get("last_modified"),
            "observed_at": datetime.now().isoformat(),
            "signal_counts": {
                "scripts": len(signals.get("scripts", [])),
                "styles": len(signals.get("styles", [])),
                "anchors": len(signals.get("anchors", [])),
                "urls": len(signals.get("urls", [])),
                "script_probe": (signals.get("script_probe") or {}).get("probed_count", 0),
            },
            "text_preview": signals.get("text_preview", [])[:5],
        }

    def _build_change(self, page: Dict, previous: Optional[Dict], current: Dict) -> Optional[Dict]:
        if not previous:
            return None

        raw_signature_unchanged = (
            previous.get("final_url") == current.get("final_url")
            and previous.get("last_modified") == current.get("last_modified")
            and previous.get("etag") == current.get("etag")
            and previous.get("html_hash") == current.get("html_hash")
            and previous.get("text_hash") == current.get("text_hash")
        )
        if raw_signature_unchanged:
            return None

        signal_changes: List[str] = []
        evidence: List[str] = []
        previous_signals = previous.get("signals", {})
        current_signals = current.get("signals", {})

        if previous.get("final_url") != current.get("final_url"):
            signal_changes.append("redirect")
            evidence.append(f"跳转目标变化: {previous.get('final_url')} -> {current.get('final_url')}")

        if previous.get("title") != current.get("title"):
            signal_changes.append("title")
            evidence.append(f"标题变化: {previous.get('title')} -> {current.get('title')}")

        if previous.get("last_modified") != current.get("last_modified") and current.get("last_modified"):
            signal_changes.append("last_modified")
            evidence.append(
                f"HTTP Last-Modified 变化: {previous.get('last_modified')} -> {current.get('last_modified')}"
            )

        self._append_list_diff(
            signal_changes,
            evidence,
            "scripts",
            previous_signals.get("scripts", []),
            current_signals.get("scripts", []),
            "脚本资源",
        )
        self._append_list_diff(
            signal_changes,
            evidence,
            "styles",
            previous_signals.get("styles", []),
            current_signals.get("styles", []),
            "样式资源",
        )

        prev_anchor_urls = [item.get("href") for item in previous_signals.get("anchors", [])]
        curr_anchor_urls = [item.get("href") for item in current_signals.get("anchors", [])]
        self._append_list_diff(
            signal_changes,
            evidence,
            "anchors",
            prev_anchor_urls,
            curr_anchor_urls,
            "链接图谱",
        )

        prev_urls = previous_signals.get("urls", [])
        curr_urls = current_signals.get("urls", [])
        if prev_urls or curr_urls:
            self._append_list_diff(
                signal_changes,
                evidence,
                "sitemap",
                prev_urls,
                curr_urls,
                "Sitemap URL 列表",
            )

        self._append_list_diff(
            signal_changes,
            evidence,
            "models",
            previous_signals.get("models", []),
            current_signals.get("models", []),
            "模型型号",
        )
        self._append_list_diff(
            signal_changes,
            evidence,
            "pricing",
            previous_signals.get("prices", []),
            current_signals.get("prices", []),
            "价格信号",
        )
        self._append_list_diff(
            signal_changes,
            evidence,
            "coding",
            previous_signals.get("coding_signals", []),
            current_signals.get("coding_signals", []),
            "Coding/Agent 信号",
        )
        self._append_list_diff(
            signal_changes,
            evidence,
            "pricing_lines",
            previous_signals.get("pricing_lines", []),
            current_signals.get("pricing_lines", []),
            "定价明细行",
        )
        self._append_list_diff(
            signal_changes,
            evidence,
            "headline_lines",
            previous_signals.get("headline_lines", []),
            current_signals.get("headline_lines", []),
            "源码文案线索",
        )
        self._append_list_diff(
            signal_changes,
            evidence,
            "route_patterns",
            previous_signals.get("route_patterns", []),
            current_signals.get("route_patterns", []),
            "路由模式",
        )
        self._append_list_diff(
            signal_changes,
            evidence,
            "api_families",
            previous_signals.get("api_families", []),
            current_signals.get("api_families", []),
            "API 家族",
        )
        self._append_list_diff(
            signal_changes,
            evidence,
            "hidden_capabilities",
            previous_signals.get("hidden_capabilities", []),
            current_signals.get("hidden_capabilities", []),
            "隐藏能力",
        )
        self._append_list_diff(
            signal_changes,
            evidence,
            "coder_signals",
            previous_signals.get("coder_signals", []),
            current_signals.get("coder_signals", []),
            "Coder 线索",
        )
        self._append_list_diff(
            signal_changes,
            evidence,
            "vision_signals",
            previous_signals.get("vision_signals", []),
            current_signals.get("vision_signals", []),
            "Vision 线索",
        )
        self._append_list_diff(
            signal_changes,
            evidence,
            "agent_signals",
            previous_signals.get("agent_signals", []),
            current_signals.get("agent_signals", []),
            "Agent 线索",
        )

        if previous.get("text_hash") != current.get("text_hash"):
            signal_changes.append("text")
            diff_summary = self._summarize_text_diff(
                previous.get("normalized_text", ""),
                current.get("normalized_text", ""),
            )
            if diff_summary:
                evidence.extend(diff_summary)

        if not signal_changes:
            return None

        source_time = current.get("last_modified") or ""
        impact_guess = self._guess_impact(page["category"], signal_changes, evidence)
        summary = self._summarize_surface_change(page["name"], signal_changes, evidence)
        observed_at = datetime.now().isoformat()

        return {
            "type": "surface_change",
            "surface_name": page["name"],
            "category": page["category"],
            "url": page["url"],
            "final_url": current.get("final_url"),
            "title": current.get("title"),
            "changed_signals": signal_changes,
            "summary": summary,
            "evidence": evidence[:8],
            "impact_guess": impact_guess,
            "source_time": source_time,
            "source_time_type": "http_last_modified" if source_time else "unknown",
            "observed_at": observed_at,
            "detected_at": observed_at,
        }

    def _append_list_diff(
        self,
        signal_changes: List[str],
        evidence: List[str],
        key: str,
        previous_items: List[str],
        current_items: List[str],
        label: str,
    ) -> None:
        prev_set = set(previous_items)
        curr_set = set(current_items)
        added = sorted(curr_set - prev_set)
        removed = sorted(prev_set - curr_set)
        if not added and not removed:
            return

        signal_changes.append(key)
        if added:
            evidence.append(f"{label}新增 {len(added)} 项: {', '.join(added[:3])}")
        if removed:
            evidence.append(f"{label}移除 {len(removed)} 项: {', '.join(removed[:3])}")

    def _summarize_text_diff(self, previous_text: str, current_text: str) -> List[str]:
        prev_lines = [line for line in previous_text.splitlines() if line.strip()]
        curr_lines = [line for line in current_text.splitlines() if line.strip()]

        matcher = SequenceMatcher(None, prev_lines, curr_lines)
        evidence = []
        for opcode, i1, i2, j1, j2 in matcher.get_opcodes():
            if opcode == "equal":
                continue
            added = [line for line in curr_lines[j1:j2] if len(line) >= 10][:2]
            removed = [line for line in prev_lines[i1:i2] if len(line) >= 10][:2]
            if added:
                evidence.append("正文新增: " + " | ".join(added))
            if removed:
                evidence.append("正文移除: " + " | ".join(removed))
            if len(evidence) >= 4:
                break
        return evidence

    def _guess_impact(self, category: str, changed_signals: List[str], evidence: List[str]) -> str:
        joined = " ".join(evidence)
        if category == "docs" and ("/news/" in joined or "Sitemap URL 列表新增" in joined):
            return "文档/公告页发生扩展，可能有新发布说明或接口文档"
        if "models" in changed_signals:
            return "检测到官方页面出现新模型型号，优先人工复核"
        if "pricing" in changed_signals or "pricing_lines" in changed_signals:
            return "检测到价格或套餐信号变化，建议立即核对定价页"
        if "hidden_capabilities" in changed_signals:
            return "检测到源码隐藏能力变化，可能有未公开或灰度中的产品结构调整"
        if "route_patterns" in changed_signals or "api_families" in changed_signals:
            return "检测到前端路由或 API 家族变化，可能有新入口、新会话结构或能力面调整"
        if "headline_lines" in changed_signals:
            return "检测到页面源码中的模型/价格/Agent 文案变化，建议人工复核"
        if "coding" in changed_signals or "coder_signals" in changed_signals or "vision_signals" in changed_signals or "agent_signals" in changed_signals:
            return "检测到 coder/coding/agent 相关公开信号变化，可能有新入口或套餐调整"
        if "scripts" in changed_signals or "styles" in changed_signals:
            return "页面构建资源发生变化，可能是官网重新部署"
        if "sitemap" in changed_signals:
            return "站点索引变化，可能新增或下线了页面"
        if "text" in changed_signals:
            return "页面正文变化，建议查看 diff 证据确认是文案调整还是功能说明更新"
        return "页面结构或元数据发生变化，建议人工复核"

    def _summarize_surface_change(
        self, name: str, changed_signals: List[str], evidence: List[str]
    ) -> str:
        signal_names = {
            "redirect": "跳转",
            "title": "标题",
            "last_modified": "HTTP 时间",
            "scripts": "脚本",
            "styles": "样式",
            "anchors": "链接",
            "sitemap": "Sitemap",
            "models": "模型",
            "pricing": "价格",
            "pricing_lines": "定价行",
            "headline_lines": "源码文案",
            "route_patterns": "路由",
            "api_families": "API 家族",
            "hidden_capabilities": "隐藏能力",
            "coder_signals": "Coder 线索",
            "vision_signals": "Vision 线索",
            "agent_signals": "Agent 线索",
            "coding": "Coding/Agent",
            "text": "正文",
        }
        labels = [signal_names.get(item, item) for item in changed_signals]
        summary = f"{name} 发生变化: " + " / ".join(labels)
        if evidence:
            summary += f"。{evidence[0]}"
        return summary

    async def cleanup(self):
        if self.session and not self.session.closed:
            await self.session.close()
