"""
Status Page 监控模块

监控 status.deepseek.com 官方状态页面：
1. 获取实时服务状态
2. 追踪宕机事件（包含详细时间）
3. 统计可用性数据
4. 检测新的故障事件

API Endpoint: https://status.deepseek.com/history.atom
"""

import re
from datetime import datetime
from typing import Dict, List, Any, Optional
from xml.etree import ElementTree as ET

import aiohttp
from loguru import logger


STATUS_PAGE_URL = "https://status.deepseek.com"
STATUS_FEED_URL = "https://status.deepseek.com/history.atom"

# 命名空间
ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}


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
        }

    async def _get_session(self) -> aiohttp.ClientSession:
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=30)
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                "Accept": "application/atom+xml",
            }
            self.session = aiohttp.ClientSession(timeout=timeout, headers=headers)
        return self.session

    async def check(self) -> Dict[str, Any]:
        """执行状态页面检查"""
        logger.info("开始检查 status.deepseek.com...")
        self.results["timestamp"] = datetime.utcnow().isoformat()

        try:
            session = await self._get_session()

            # 获取 Atom Feed
            feed_data = await self._fetch_feed(session)
            if not feed_data:
                logger.warning("无法获取状态页面数据")
                return self.results

            # 解析事件
            await self._parse_incidents(feed_data)

            # 获取组件状态（从页面 HTML）
            await self._fetch_components(session)

            # 保存快照
            await self._save_snapshot()

            # 检测变化
            await self._detect_changes()

        except Exception as e:
            logger.error(f"状态页面检查失败: {e}", exc_info=True)
            self.results["error"] = str(e)

        return self.results

    async def _fetch_feed(self, session: aiohttp.ClientSession) -> Optional[str]:
        """获取 Atom Feed"""
        try:
            async with session.get(STATUS_FEED_URL) as resp:
                if resp.status != 200:
                    logger.warning(f"Status Feed 返回 {resp.status}")
                    return None
                return await resp.text()
        except Exception as e:
            logger.error(f"获取 Feed 失败: {e}")
            return None

    async def _fetch_components(self, session: aiohttp.ClientSession):
        """获取组件状态"""
        try:
            async with session.get(STATUS_PAGE_URL) as resp:
                if resp.status == 200:
                    html = await resp.text()
                    
                    # 从 HTML 中提取组件信息
                    # 格式: <div data-component-id="..." data-component-status="...">
                    #       <span class="name">组件名称</span>
                    components = []
                    
                    # 查找所有组件块
                    comp_pattern = r'<div data-component-id="([^"]+)"[^>]*data-component-status="([^"]+)"[^>]*>.*?<span class="name">\s*([^<]+)\s*</span>'
                    matches = re.findall(comp_pattern, html, re.DOTALL)
                    
                    for comp_id, status, name in matches:
                        name = name.strip()
                        if name and not any(c["id"] == comp_id for c in components):
                            components.append({
                                "id": comp_id,
                                "name": name,
                                "status": status,
                            })
                    
                    if components:
                        self.results["components"] = components
                        logger.info(f"检测到 {len(components)} 个组件")
                    else:
                        # 备用方案：从页面状态文本提取
                        if "All Systems Operational" in html:
                            self.results["components"] = [
                                {"id": "api", "name": "API 服务", "status": "operational"},
                                {"id": "web", "name": "网页对话服务", "status": "operational"},
                            ]
                            logger.info("使用备用方案：所有系统正常")
        except Exception as e:
            logger.warning(f"获取组件状态失败: {e}")

    async def _parse_incidents(self, feed_xml: str):
        """解析 Atom Feed 中的事件"""
        logger.info("解析事件历史...")

        try:
            root = ET.fromstring(feed_xml.encode("utf-8"))
            entries = root.findall("atom:entry", ATOM_NS)

            incidents = []
            for entry in entries:
                # 提取基本信息
                title_elem = entry.find("atom:title", ATOM_NS)
                title = title_elem.text if title_elem is not None else ""

                published_elem = entry.find("atom:published", ATOM_NS)
                published = published_elem.text if published_elem is not None else ""

                updated_elem = entry.find("atom:updated", ATOM_NS)
                updated = updated_elem.text if updated_elem is not None else ""

                link_elem = entry.find("atom:link", ATOM_NS)
                link = link_elem.get("href", "") if link_elem is not None else ""

                content_elem = entry.find("atom:content", ATOM_NS)
                content = content_elem.text if content_elem is not None else ""

                # 从内容中提取时间线
                timeline = self._parse_timeline(content)

                # 判断影响级别
                impact = self._determine_impact(title, content)

                # 提取组件
                components = self._extract_components(title, content)

                incident = {
                    "id": link.split("/")[-1] if "/" in link else "",
                    "name": title,
                    "impact": impact,
                    "published": published,
                    "updated": updated,
                    "link": link,
                    "timeline": timeline,
                    "components": components,
                }
                incidents.append(incident)

            self.results["incidents"] = incidents
            logger.info(f"发现 {len(incidents)} 个事件")

        except Exception as e:
            logger.error(f"解析 Feed 失败: {e}")

    def _parse_timeline(self, content: str) -> List[Dict]:
        """从 HTML 内容中提取时间线"""
        timeline = []
        
        if not content:
            return timeline

        # 首先移除 <var> 标签，保留内容
        # 格式: <var data-var='date'> 3</var> -> 3
        content_cleaned = re.sub(r'<var[^>]*>([^<]*)</var>', r'\1', content)

        # 解析 <p><small>...</small><br><strong>...</strong>...</p> 格式
        # 例如: <p><small>Apr  3, 16:50 CST</small><br><strong>Resolved</strong> - This incident...</p>
        pattern = r'<small>([^<]+)</small>\s*<br\s*/?>\s*<strong>([^<]+)</strong>\s*-?\s*([^<]*)'
        matches = re.findall(pattern, content_cleaned)

        for time_str, status, description in matches:
            timeline.append({
                "time": time_str.strip(),
                "status": status.strip(),
                "description": description.strip() if description else "",
            })

        return timeline

    def _determine_impact(self, title: str, content: str) -> str:
        """判断事件影响级别"""
        title_lower = title.lower()
        content_lower = content.lower() if content else ""

        if "不可用" in title or "not available" in title_lower:
            return "critical"
        elif "严重" in title or "critical" in content_lower:
            return "critical"
        elif "重大" in title or "major" in content_lower:
            return "major"
        elif "性能异常" in title or "degraded" in title_lower:
            return "minor"
        elif "轻微" in title or "minor" in content_lower:
            return "minor"
        else:
            return "minor"

    def _extract_components(self, title: str, content: str) -> List[str]:
        """提取受影响的组件"""
        components = []
        
        if "网页" in title or "Web" in title:
            components.append("网页对话服务")
        if "API" in title:
            components.append("API服务")
        if "APP" in title or "App" in title:
            components.append("移动应用")

        return components if components else ["未知"]

    async def _save_snapshot(self):
        """保存状态快照"""
        await self.storage.save_status_snapshot({
            "components": self.results["components"],
            "incidents": self.results["incidents"],
            "timestamp": self.results["timestamp"],
        })

    async def _detect_changes(self):
        """检测状态变化"""
        logger.info("检测状态变化...")

        last_snapshot = await self.storage.get_last_status_snapshot()
        if not last_snapshot:
            logger.info("首次运行，跳过变化检测")
            return

        # 检测组件状态变化
        last_components = {c.get("id"): c for c in last_snapshot.get("components", [])}
        current_components = {c.get("id"): c for c in self.results["components"]}

        for comp_id, comp_info in current_components.items():
            last_comp = last_components.get(comp_id)
            if last_comp:
                if last_comp.get("status") != comp_info.get("status"):
                    change = {
                        "type": "status_change",
                        "component_id": comp_id,
                        "component_name": comp_info.get("name"),
                        "old_status": last_comp.get("status"),
                        "new_status": comp_info.get("status"),
                        "detected_at": datetime.utcnow().isoformat(),
                    }
                    self.results["changes"].append(change)
                    logger.warning(
                        f"服务状态变化: {comp_info.get('name')} {last_comp.get('status')} -> {comp_info.get('status')}"
                    )

        # 检测新事件
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
                    "detected_at": datetime.utcnow().isoformat(),
                }
                self.results["changes"].append(change)
                logger.warning(f"新事件: {inc.get('name')}")

    async def cleanup(self):
        """清理资源"""
        if self.session and not self.session.closed:
            await self.session.close()
            logger.debug("StatusMonitor HTTP session 已关闭")
