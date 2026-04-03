"""
Status Page 监控模块

监控 status.deepseek.com 官方状态页面：
1. 获取实时服务状态
2. 追踪宕机事件
3. 统计可用性数据
4. 检测新的故障事件

API Endpoint: https://status.deepseek.com/history.json
"""

import json
import re
from datetime import datetime
from typing import Dict, List, Any, Optional

import aiohttp
from loguru import logger


STATUS_PAGE_URL = "https://status.deepseek.com"
STATUS_API_URL = "https://status.deepseek.com/history.json"


class StatusMonitor:
    """DeepSeek 官方状态页面监控器"""

    def __init__(self, config: Dict, storage):
        self.config = config
        self.storage = storage
        self.session = None
        self.results = {
            "timestamp": None,
            "changes": [],
            "components": [],
            "incidents": [],
        }

    async def _get_session(self) -> aiohttp.ClientSession:
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=30)
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                "Accept": "application/json",
            }
            self.session = aiohttp.ClientSession(timeout=timeout, headers=headers)
        return self.session

    async def check(self) -> Dict[str, Any]:
        """执行状态页面检查"""
        logger.info("开始检查 status.deepseek.com...")
        self.results["timestamp"] = datetime.utcnow().isoformat()

        try:
            session = await self._get_session()

            # 获取状态页面数据
            status_data = await self._fetch_status_data(session)
            if not status_data:
                logger.warning("无法获取状态页面数据")
                return self.results

            # 1. 解析组件状态
            await self._parse_components(status_data)

            # 2. 解析事件历史
            await self._parse_incidents(status_data)

            # 3. 保存快照
            await self._save_snapshot()

            # 4. 检测变化
            await self._detect_changes()

        except Exception as e:
            logger.error(f"状态页面检查失败: {e}", exc_info=True)
            self.results["error"] = str(e)

        return self.results

    async def _fetch_status_data(self, session: aiohttp.ClientSession) -> Optional[Dict]:
        """获取状态页面数据"""
        try:
            async with session.get(STATUS_API_URL) as resp:
                if resp.status != 200:
                    logger.warning(f"Status API 返回 {resp.status}")
                    return None
                return await resp.json()
        except Exception as e:
            logger.error(f"获取状态数据失败: {e}")
            return None

    async def _parse_components(self, data: Dict):
        """解析组件状态"""
        logger.info("解析组件状态...")

        components = data.get("components", [])
        parsed_components = []

        for comp in components:
            parsed = {
                "id": comp.get("id"),
                "name": comp.get("name"),
                "status": comp.get("status"),  # operational, degraded_performance, partial_outage, major_outage
                "description": comp.get("description"),
            }
            parsed_components.append(parsed)

        self.results["components"] = parsed_components
        logger.info(f"  检测到 {len(parsed_components)} 个组件")

    async def _parse_incidents(self, data: Dict):
        """解析事件历史"""
        logger.info("解析事件历史...")

        # 从 months 中提取事件
        months = data.get("months", [])
        all_incidents = []

        for month_data in months:
            month_name = month_data.get("name")
            year = month_data.get("year")
            incidents = month_data.get("incidents", [])

            for inc in incidents:
                parsed = {
                    "id": inc.get("id"),
                    "name": inc.get("name"),
                    "status": inc.get("status"),
                    "impact": inc.get("impact"),  # minor, major, critical
                    "date": inc.get("date"),
                    "year": year,
                    "month": month_name,
                    "created_at": inc.get("created_at"),
                    "resolved_at": inc.get("resolved_at"),
                    "components": [c.get("name") for c in inc.get("components", [])],
                }
                all_incidents.append(parsed)

        # 按日期排序（最新的在前）
        all_incidents.sort(key=lambda x: x.get("date") or "", reverse=True)

        self.results["incidents"] = all_incidents
        logger.info(f"  发现 {len(all_incidents)} 个事件")

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
                    "date": inc.get("date"),
                    "detected_at": datetime.utcnow().isoformat(),
                }
                self.results["changes"].append(change)
                logger.warning(f"新事件: {inc.get('name')}")

    async def cleanup(self):
        """清理资源"""
        if self.session and not self.session.closed:
            await self.session.close()
            logger.debug("StatusMonitor HTTP session 已关闭")
