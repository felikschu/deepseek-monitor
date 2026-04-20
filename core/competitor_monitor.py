"""
竞品官网侦察模块

重点关注：
1. 新模型型号
2. 前端版本信号
3. 新闻/研究页新增 slug 与日期
"""

import asyncio
import hashlib
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import aiohttp
from bs4 import BeautifulSoup
from loguru import logger

from utils.model_signal_extractor import extract_model_signals
from utils.source_probe import merge_signal_maps, pick_interesting_links, probe_script_assets


RELATED_SITE_KEYS = {
    "zhipu": ["zhipuai.cn", "bigmodel.cn", "z.ai"],
    "minimax": ["minimax.io", "minimaxi.com", "minimax.chat"],
}


class CompetitorMonitor:
    def __init__(self, config: Dict, storage):
        self.config = config
        self.storage = storage
        self.monitor_config = config.get("competitor_surfaces", {})
        self.session = None
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
        session = await self._get_session()
        page_timeout = self.config.get("monitoring", {}).get("timeout_seconds", 30) + 5

        for page in pages:
            try:
                snapshot = await asyncio.wait_for(
                    self._fetch_snapshot(session, page),
                    timeout=page_timeout,
                )
                self.results["surfaces"].append({
                    "vendor": page["vendor"],
                    "name": page["name"],
                    "url": page["url"],
                    "title": snapshot.get("title"),
                    "last_modified": snapshot.get("last_modified"),
                    "signals": snapshot.get("signals", {}),
                    "observed_at": datetime.now().isoformat(),
                })
                previous = await self.storage.get_last_competitor_snapshot(page["url"])
                change = self._build_change(page, previous, snapshot)
                if change:
                    self.results["changes"].append(change)
                await self.storage.save_competitor_snapshot(
                    page["vendor"], page["name"], page["url"], page["category"], snapshot
                )
            except Exception as exc:
                detail = str(exc) or exc.__class__.__name__
                logger.warning(f"竞品侦察失败 {page.get('url')}: {detail}")

        return self.results

    async def _fetch_snapshot(self, session: aiohttp.ClientSession, page: Dict) -> Dict[str, Any]:
        async with session.get(page["url"], allow_redirects=True) as response:
            html = await response.text()
            soup = BeautifulSoup(html, "html.parser")
            page_text = soup.get_text(" ", strip=True)
            title = ""
            if soup.title and soup.title.string:
                title = " ".join(soup.title.string.split())
            scripts = []
            for tag in soup.find_all("script", src=True):
                scripts.append(urljoin(str(response.url), tag.get("src")))
            hrefs = []
            for tag in soup.find_all("a", href=True):
                hrefs.append(urljoin(str(response.url), tag.get("href")))
            signals = merge_signal_maps(
                extract_model_signals(page_text, page["vendor"]),
                extract_model_signals(html, page["vendor"]),
            )
            signals["discovered_links"] = pick_interesting_links(
                str(response.url),
                hrefs,
                allowed_site_keys=RELATED_SITE_KEYS.get(page["vendor"], []),
                limit=20,
            )
            script_probe = await probe_script_assets(
                session,
                str(response.url),
                scripts,
                lambda script_text: extract_model_signals(script_text, page["vendor"]),
                limit=page.get("script_probe_limit", 4),
            )
            signals = merge_signal_maps(signals, script_probe.get("signals", {}))
            signals["script_probe"] = script_probe.get("probe", {})
            return {
                "final_url": str(response.url),
                "title": title,
                "last_modified": response.headers.get("Last-Modified", ""),
                "etag": response.headers.get("ETag", ""),
                "content_type": response.headers.get("Content-Type", ""),
                "status_code": response.status,
                "html_hash": hashlib.md5(html.encode("utf-8")).hexdigest(),
                "signals": signals,
            }

    def _build_change(self, page: Dict, previous: Optional[Dict], current: Dict) -> Optional[Dict]:
        if not previous:
            return None

        prev_signals = previous.get("signals", {})
        curr_signals = current.get("signals", {})
        prev_models = set(prev_signals.get("models", []))
        curr_models = set(curr_signals.get("models", []))
        added_models = sorted(curr_models - prev_models)
        removed_models = sorted(prev_models - curr_models)

        prev_versions = set(prev_signals.get("resource_versions", []))
        curr_versions = set(curr_signals.get("resource_versions", []))
        added_versions = sorted(curr_versions - prev_versions)

        prev_dates = set(prev_signals.get("dates", []))
        curr_dates = set(curr_signals.get("dates", []))
        added_dates = sorted(curr_dates - prev_dates)

        prev_news = set(prev_signals.get("news_slugs", []))
        curr_news = set(curr_signals.get("news_slugs", []))
        added_news = sorted(curr_news - prev_news)

        prev_prices = set(prev_signals.get("prices", []))
        curr_prices = set(curr_signals.get("prices", []))
        added_prices = sorted(curr_prices - prev_prices)

        prev_pricing_lines = set(prev_signals.get("pricing_lines", []))
        curr_pricing_lines = set(curr_signals.get("pricing_lines", []))
        added_pricing_lines = sorted(curr_pricing_lines - prev_pricing_lines)

        prev_plan_signals = set(prev_signals.get("plan_signals", []))
        curr_plan_signals = set(curr_signals.get("plan_signals", []))
        added_plan_signals = sorted(curr_plan_signals - prev_plan_signals)

        prev_offerings = set(prev_signals.get("offerings", []))
        curr_offerings = set(curr_signals.get("offerings", []))
        added_offerings = sorted(curr_offerings - prev_offerings)

        prev_pricing_paths = set(prev_signals.get("pricing_paths", []))
        curr_pricing_paths = set(curr_signals.get("pricing_paths", []))
        added_pricing_paths = sorted(curr_pricing_paths - prev_pricing_paths)

        prev_actions = set(prev_signals.get("commercial_actions", []))
        curr_actions = set(curr_signals.get("commercial_actions", []))
        added_actions = sorted(curr_actions - prev_actions)

        prev_headlines = set(prev_signals.get("headline_lines", []))
        curr_headlines = set(curr_signals.get("headline_lines", []))
        added_headlines = sorted(curr_headlines - prev_headlines)

        prev_links = set(prev_signals.get("discovered_links", []))
        curr_links = set(curr_signals.get("discovered_links", []))
        added_links = sorted(curr_links - prev_links)

        significant_change = any(
            [
                added_models,
                removed_models,
                added_versions,
                added_prices,
                added_pricing_lines,
                added_offerings,
                added_pricing_paths,
                added_actions,
                added_headlines,
                added_links,
                added_dates,
                added_news,
            ]
        )

        evidence: List[str] = []
        if added_models:
            evidence.append("新增模型型号: " + ", ".join(added_models[:8]))
        if removed_models:
            evidence.append("移除模型型号: " + ", ".join(removed_models[:8]))
        if added_versions:
            evidence.append("新增官网版本信号: " + ", ".join(added_versions[:5]))
        if added_prices:
            evidence.append("新增价格信号: " + ", ".join(added_prices[:8]))
        if added_pricing_lines:
            evidence.append("新增定价明细: " + " | ".join(added_pricing_lines[:2]))
        if added_offerings:
            evidence.append("新增商业化入口: " + ", ".join(added_offerings[:6]))
        if added_pricing_paths:
            evidence.append("新增定价/套餐路径: " + ", ".join(added_pricing_paths[:4]))
        if added_actions:
            evidence.append("新增商业动作解读: " + " | ".join(added_actions[:3]))
        if added_headlines:
            evidence.append("新增标题线索: " + " | ".join(added_headlines[:2]))
        if added_links:
            evidence.append("新增可疑链接: " + ", ".join(added_links[:4]))
        if added_plan_signals and significant_change:
            evidence.append("新增套餐/活动线索: " + " | ".join(added_plan_signals[:2]))
        if added_dates:
            evidence.append("新增日期信号: " + ", ".join(added_dates[:6]))
        if added_news:
            evidence.append("新增新闻 slug: " + ", ".join(added_news[:5]))

        if not significant_change:
            return None

        observed_at = datetime.now().isoformat()
        summary = f"{page['name']} 侦察到新信号"
        if added_models:
            summary = f"{page['name']} 出现新模型型号: {', '.join(added_models[:3])}"
        elif added_actions:
            summary = f"{page['name']} 出现新的商业化动作"
        elif added_pricing_lines or added_prices:
            summary = f"{page['name']} 出现价格/套餐信号"
        elif added_offerings or added_pricing_paths:
            summary = f"{page['name']} 出现新的商业化入口"

        article_dates = curr_signals.get("article_dates", [])
        source_time = current.get("last_modified", "") or (article_dates[0] if article_dates else "")
        source_time_type = "http_last_modified" if current.get("last_modified") else ("page_date_signal" if article_dates else "scraped_signal")

        return {
            "type": "competitor_model_change",
            "vendor": page["vendor"],
            "surface_name": page["name"],
            "url": page["url"],
            "final_url": current.get("final_url"),
            "summary": summary,
            "added_models": added_models,
            "removed_models": removed_models,
            "added_versions": added_versions,
            "added_prices": added_prices,
            "added_pricing_lines": added_pricing_lines,
            "added_plan_signals": added_plan_signals,
            "added_offerings": added_offerings,
            "added_pricing_paths": added_pricing_paths,
            "added_actions": added_actions,
            "added_headlines": added_headlines,
            "added_links": added_links,
            "added_dates": added_dates,
            "added_news": added_news,
            "evidence": evidence,
            "source_time": source_time,
            "source_time_type": source_time_type,
            "observed_at": observed_at,
            "detected_at": observed_at,
        }

    async def cleanup(self):
        if self.session and not self.session.closed:
            await self.session.close()
