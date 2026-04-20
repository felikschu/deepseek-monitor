"""
Status Page 监控模块

监控 status.deepseek.com 官方状态页面：
1. Atom/RSS feed 优先抓取历史事件
2. HTML 页面补充当前组件状态
3. 检测新增事件与状态变化
"""

import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Dict, List, Any, Optional
from xml.etree import ElementTree as ET

import aiohttp
from loguru import logger


STATUS_PAGE_URL = "https://status.deepseek.com"
STATUS_HISTORY_URL = "https://status.deepseek.com/history"
STATUS_ATOM_URL = "https://status.deepseek.com/history.atom"
STATUS_RSS_URL = "https://status.deepseek.com/history.rss"

ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}
RSS_NS = {"dc": "http://purl.org/dc/elements/1.1/"}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class StatusMonitor:
    """DeepSeek 官方状态页面监控器"""

    def __init__(self, config: Dict, storage):
        self.config = config
        self.storage = storage
        self.session = None
        self.results = {
            "timestamp": None,
            "components": [],
            "incidents": [],
            "changes": [],
        }

    async def _get_session(self) -> aiohttp.ClientSession:
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=30)
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                "Accept": "application/atom+xml,application/rss+xml,text/html;q=0.9,*/*;q=0.8",
            }
            self.session = aiohttp.ClientSession(timeout=timeout, headers=headers)
        return self.session

    async def check(self) -> Dict[str, Any]:
        logger.info("开始检查 status.deepseek.com...")
        self.results["timestamp"] = utc_now_iso()

        try:
            session = await self._get_session()

            incidents = await self._fetch_incidents(session)
            self.results["incidents"] = incidents

            await self._fetch_components(session)
            await self._detect_changes()
            await self._save_snapshot()
        except Exception as e:
            logger.error(f"状态页面检查失败: {e}", exc_info=True)
            self.results["error"] = str(e)

        return self.results

    async def _fetch_text(self, session: aiohttp.ClientSession, url: str) -> str:
        async with session.get(url) as resp:
            resp.raise_for_status()
            return await resp.text()

    async def _fetch_incidents(self, session: aiohttp.ClientSession) -> List[Dict]:
        logger.info("抓取事件历史（Atom/RSS 优先）...")

        atom_text = ""
        rss_text = ""
        atom_incidents: List[Dict] = []
        rss_incidents: List[Dict] = []

        try:
            atom_text = await self._fetch_text(session, STATUS_ATOM_URL)
            atom_incidents = self._parse_atom(atom_text)
            logger.info(f"Atom feed 解析到 {len(atom_incidents)} 个事件")
        except Exception as e:
            logger.warning(f"Atom feed 获取/解析失败: {e}")

        try:
            rss_text = await self._fetch_text(session, STATUS_RSS_URL)
            rss_incidents = self._parse_rss(rss_text)
            logger.info(f"RSS feed 解析到 {len(rss_incidents)} 个事件")
        except Exception as e:
            logger.warning(f"RSS feed 获取/解析失败: {e}")

        incidents_by_id: Dict[str, Dict] = {}
        for incident in atom_incidents + rss_incidents:
            incident_id = incident.get("id")
            if not incident_id:
                continue
            if incident_id not in incidents_by_id:
                incidents_by_id[incident_id] = incident
                continue

            current = incidents_by_id[incident_id]
            merged = {**current, **incident}
            if not merged.get("timeline"):
                merged["timeline"] = current.get("timeline") or incident.get("timeline") or []
            if not merged.get("components"):
                merged["components"] = current.get("components") or incident.get("components") or []
            if not merged.get("name"):
                merged["name"] = current.get("name") or incident.get("name") or ""
            if not merged.get("published"):
                merged["published"] = current.get("published") or incident.get("published") or ""
            if not merged.get("updated"):
                merged["updated"] = current.get("updated") or incident.get("updated") or ""
            incidents_by_id[incident_id] = merged

        incidents = list(incidents_by_id.values())
        incidents.sort(key=lambda x: x.get("published") or x.get("updated") or "", reverse=True)
        return incidents

    async def _fetch_components(self, session: aiohttp.ClientSession):
        try:
            html = await self._fetch_text(session, STATUS_PAGE_URL)

            components = []
            comp_pattern = (
                r'<div data-component-id="([^"]+)"[^>]*data-component-status="([^"]+)"[^>]*>.*?'
                r'<span class="name">\s*([^<]+)\s*</span>'
            )
            matches = re.findall(comp_pattern, html, re.DOTALL)
            for comp_id, status, name in matches:
                name = name.strip()
                if name and not any(c["id"] == comp_id for c in components):
                    components.append({"id": comp_id, "name": name, "status": status})

            if components:
                self.results["components"] = components
                logger.info(f"检测到 {len(components)} 个组件")
                return

            if "All Systems Operational" in html:
                self.results["components"] = [
                    {"id": "api", "name": "API 服务", "status": "operational"},
                    {"id": "web_app", "name": "网页/APP 服务", "status": "operational"},
                ]
                logger.info("使用备用方案：所有系统正常")
        except Exception as e:
            logger.warning(f"获取组件状态失败: {e}")

    def _parse_atom(self, feed_xml: str) -> List[Dict]:
        root = ET.fromstring(feed_xml.encode("utf-8"))
        entries = root.findall("atom:entry", ATOM_NS)
        incidents = []

        for entry in entries:
            title = self._xml_text(entry, "atom:title", ATOM_NS)
            published = self._xml_text(entry, "atom:published", ATOM_NS)
            updated = self._xml_text(entry, "atom:updated", ATOM_NS)
            link_elem = entry.find("atom:link", ATOM_NS)
            link = link_elem.get("href", "") if link_elem is not None else ""
            content = self._xml_text(entry, "atom:content", ATOM_NS)
            incident_id = self._incident_id_from_link(link)
            timeline = self._parse_timeline(content)
            incidents.append({
                "id": incident_id,
                "name": title,
                "title": title,
                "impact": self._determine_impact(title, content),
                "published": published,
                "updated": updated,
                "link": link,
                "timeline": timeline,
                "components": self._extract_components(title, content),
            })

        return incidents

    def _parse_rss(self, feed_xml: str) -> List[Dict]:
        root = ET.fromstring(feed_xml.encode("utf-8"))
        items = root.findall("./channel/item")
        incidents = []

        for item in items:
            title = self._xml_text(item, "title")
            link = self._xml_text(item, "link")
            published = self._xml_text(item, "pubDate")
            description = self._xml_text(item, "description")
            guid = self._xml_text(item, "guid")
            incident_id = self._incident_id_from_link(link or guid)
            timeline = self._parse_timeline(description)
            incidents.append({
                "id": incident_id,
                "name": title,
                "title": title,
                "impact": self._determine_impact(title, description),
                "published": self._normalize_feed_time(published),
                "updated": self._normalize_feed_time(published),
                "link": link,
                "timeline": timeline,
                "components": self._extract_components(title, description),
            })

        return incidents

    def _xml_text(self, node, path: str, ns: Optional[Dict] = None) -> str:
        elem = node.find(path, ns or {})
        if elem is None or elem.text is None:
            return ""
        return elem.text.strip()

    def _normalize_feed_time(self, value: str) -> str:
        if not value:
            return ""
        try:
            return parsedate_to_datetime(value).isoformat()
        except Exception:
            return value

    def _incident_id_from_link(self, link: str) -> str:
        if not link:
            return ""
        return link.rstrip("/").split("/")[-1]

    def _parse_timeline(self, content: str) -> List[Dict]:
        timeline = []
        if not content:
            return timeline

        content_cleaned = re.sub(r"<var[^>]*>([^<]*)</var>", r"\1", content)
        pattern = r"<small>([^<]+)</small>\s*<br\s*/?>\s*<strong>([^<]+)</strong>\s*-?\s*([^<]*)"
        matches = re.findall(pattern, content_cleaned)

        for time_str, status, description in matches:
            timeline.append({
                "time": time_str.strip(),
                "status": status.strip(),
                "description": description.strip() if description else "",
            })

        return timeline

    def _determine_impact(self, title: str, content: str) -> str:
        text = f"{title} {content}".lower()
        if any(key in text for key in ["不可用", "outage", "major outage", "严重"]):
            return "critical"
        if "major" in text or "重大" in text:
            return "major"
        if any(key in text for key in ["abnormal", "degraded", "minor", "异常", "恢复"]):
            return "minor"
        return "minor"

    def _extract_components(self, title: str, content: str) -> List[str]:
        text = f"{title} {content}"
        components = []
        if any(key in text for key in ["网页", "Web"]):
            components.append("网页对话服务")
        if any(key in text for key in ["APP", "App"]):
            components.append("移动应用")
        if "API" in text:
            components.append("API 服务")
        return components or ["未知"]

    async def _save_snapshot(self):
        await self.storage.save_status_snapshot({
            "components": self.results["components"],
            "incidents": self.results["incidents"],
            "timestamp": self.results["timestamp"],
        })

    async def _detect_changes(self):
        logger.info("检测状态变化...")
        last_snapshot = await self.storage.get_last_status_snapshot()
        if not last_snapshot:
            logger.info("首次运行，跳过变化检测")
            return

        last_components = {c.get("id"): c for c in last_snapshot.get("components", [])}
        current_components = {c.get("id"): c for c in self.results["components"]}
        observed_at = utc_now_iso()

        for comp_id, comp_info in current_components.items():
            last_comp = last_components.get(comp_id)
            if last_comp and last_comp.get("status") != comp_info.get("status"):
                change = {
                    "type": "status_change",
                    "component_id": comp_id,
                    "component_name": comp_info.get("name"),
                    "old_status": last_comp.get("status"),
                    "new_status": comp_info.get("status"),
                    "source_time": self.results.get("timestamp"),
                    "source_time_type": "status_snapshot_time",
                    "observed_at": observed_at,
                    "detected_at": observed_at,
                }
                self.results["changes"].append(change)
                logger.warning(
                    f"服务状态变化: {comp_info.get('name')} {last_comp.get('status')} -> {comp_info.get('status')}"
                )

        last_incident_ids = {inc.get("id") for inc in last_snapshot.get("incidents", [])}
        for inc in self.results["incidents"]:
            inc_id = inc.get("id")
            if inc_id and inc_id not in last_incident_ids:
                change = {
                    "type": "new_incident",
                    "incident_id": inc_id,
                    "title": inc.get("name"),
                    "impact": inc.get("impact"),
                    "components": inc.get("components", []),
                    "published": inc.get("published"),
                    "source_time": inc.get("published") or inc.get("updated") or "",
                    "source_time_type": "incident_feed_time",
                    "observed_at": observed_at,
                    "detected_at": observed_at,
                }
                self.results["changes"].append(change)
                logger.warning(f"新事件: {inc.get('name')}")

    async def cleanup(self):
        if self.session and not self.session.closed:
            await self.session.close()
            logger.debug("StatusMonitor HTTP session 已关闭")
