"""
Status Page 监控模块

监控 status.deepseek.com 官方状态页面：
1. 获取实时服务状态
2. 追踪宕机事件
3. 统计可用性数据
4. 检测新的故障事件

status.deepseek.com 数据结构：
- uptimeData: 各服务的历史可用性数据
- incidents: 当前和历史事件
- outages: 中断统计（m=major完全中断, p=partial部分中断, mi=minor轻微）
"""

import json
import re
from datetime import datetime
from typing import Dict, List, Any, Optional

import aiohttp
from loguru import logger


STATUS_PAGE_URL = "https://status.deepseek.com"
STATUS_API_URL = "https://status.deepseek.com/api/status-page"

# 服务组件映射
COMPONENT_NAMES = {
    "webapp": "网页端 (Web App)",
    "api": "API 服务",
    "app": "移动应用 (Mobile App)",
}


class StatusMonitor:
    """DeepSeek 官方状态页面监控器"""

    def __init__(self, config: Dict, storage):
        self.config = config
        self.storage = storage
        self.session = None
        self.results = {
            "timestamp": None,
            "changes": [],
            "status": {},
            "incidents": [],
            "uptime": {},
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
        """执行状态页面检查

        Returns:
            检查结果字典
        """
        logger.info("开始检查 status.deepseek.com...")
        self.results["timestamp"] = datetime.utcnow().isoformat()

        try:
            session = await self._get_session()

            # 1. 获取状态页面数据
            status_data = await self._fetch_status_data(session)
            if not status_data:
                logger.warning("无法获取状态页面数据")
                return self.results

            # 2. 解析当前状态
            await self._parse_current_status(status_data)

            # 3. 解析事件历史
            await self._parse_incidents(status_data)

            # 4. 解析可用性统计
            await self._parse_uptime_stats(status_data)

            # 5. 保存快照
            await self._save_snapshot(status_data)

            # 6. 检测变化
            await self._detect_changes()

        except Exception as e:
            logger.error(f"状态页面检查失败: {e}", exc_info=True)
            self.results["error"] = str(e)

        return self.results

    async def _fetch_status_data(self, session: aiohttp.ClientSession) -> Optional[Dict]:
        """获取状态页面数据

        Args:
            session: HTTP session

        Returns:
            状态数据字典或 None
        """
        try:
            # 先尝试获取主页，从中提取状态数据
            async with session.get(STATUS_PAGE_URL) as resp:
                if resp.status != 200:
                    logger.warning(f"状态页面返回 {resp.status}")
                    return None
                html = await resp.text()

            # 从 HTML 中提取状态数据（通常在 script 标签中）
            # 查找 window.initialData 或类似的初始数据
            patterns = [
                r'window\.__INITIAL_STATE__\s*=\s*({.+?});',
                r'window\.__DATA__\s*=\s*({.+?});',
                r'"uptimeData":\s*({.+?"incidents".+?})',
            ]

            for pattern in patterns:
                match = re.search(pattern, html, re.DOTALL)
                if match:
                    try:
                        data = json.loads(match.group(1))
                        return data
                    except json.JSONDecodeError:
                        continue

            # 如果无法从 HTML 提取，尝试直接访问 API
            async with session.get(STATUS_API_URL) as resp:
                if resp.status == 200:
                    return await resp.json()

            logger.warning("无法从状态页面提取数据")
            return None

        except Exception as e:
            logger.error(f"获取状态数据失败: {e}")
            return None

    async def _parse_current_status(self, data: Dict):
        """解析当前服务状态"""
        logger.info("解析当前服务状态...")

        # 获取组件状态
        components = data.get("components", []) or data.get("uptimeData", {}).get("components", [])

        status_summary = {}
        for comp in components:
            comp_id = comp.get("id") or comp.get("name", "").lower().replace(" ", "")
            comp_name = comp.get("name", comp_id)
            comp_status = comp.get("status", "unknown")

            status_summary[comp_id] = {
                "name": comp_name,
                "status": comp_status,
                "status_text": self._translate_status(comp_status),
            }

        self.results["status"] = status_summary
        logger.info(f"  检测到 {len(status_summary)} 个服务组件")

    async def _parse_incidents(self, data: Dict):
        """解析事件历史"""
        logger.info("解析事件历史...")

        incidents = data.get("incidents", []) or data.get("uptimeData", {}).get("incidents", [])

        parsed_incidents = []
        for inc in incidents:
            parsed = {
                "id": inc.get("id") or inc.get("incident_id", ""),
                "title": inc.get("title", ""),
                "status": inc.get("status", ""),
                "impact": inc.get("impact", ""),
                "created_at": inc.get("created_at") or inc.get("date", ""),
                "resolved_at": inc.get("resolved_at") or inc.get("resolved", ""),
                "components": [c.get("name", "") for c in inc.get("components", [])],
            }
            parsed_incidents.append(parsed)

        self.results["incidents"] = parsed_incidents
        logger.info(f"  发现 {len(parsed_incidents)} 个事件")

    async def _parse_uptime_stats(self, data: Dict):
        """解析可用性统计"""
        logger.info("解析可用性统计...")

        uptime_data = data.get("uptimeData", {}) or data

        # 获取各服务的可用性百分比
        uptime_stats = {}
        for comp_id, comp_data in uptime_data.get("components", {}).items():
            if isinstance(comp_data, dict):
                uptime_stats[comp_id] = {
                    "daily": comp_data.get("daily", []),
                    "overall": comp_data.get("overall", {}),
                }

        # 获取中断统计
        outages = uptime_data.get("outages", {})
        if outages:
            self.results["outages"] = outages
            # 解析中断时长（分钟）
            for key, minutes in outages.items():
                outage_type = {"m": "完全中断", "p": "部分中断", "mi": "轻微中断"}.get(key, key)
                logger.info(f"  今日{outage_type}: {minutes} 分钟")

        self.results["uptime"] = uptime_stats

    async def _save_snapshot(self, data: Dict):
        """保存状态快照"""
        await self.storage.save_status_snapshot({
            "status": self.results["status"],
            "incidents": self.results["incidents"],
            "uptime": self.results["uptime"],
            "outages": self.results.get("outages", {}),
            "raw_data": data,
        })

    async def _detect_changes(self):
        """检测状态变化"""
        logger.info("检测状态变化...")

        last_snapshot = await self.storage.get_last_status_snapshot()
        if not last_snapshot:
            logger.info("首次运行，跳过变化检测")
            return

        last_status = last_snapshot.get("status", {})
        current_status = self.results["status"]

        # 检测服务状态变化
        for comp_id, comp_info in current_status.items():
            last_comp = last_status.get(comp_id)
            if last_comp:
                if last_comp.get("status") != comp_info.get("status"):
                    change = {
                        "type": "status_change",
                        "component": comp_id,
                        "component_name": comp_info.get("name", comp_id),
                        "old_status": last_comp.get("status"),
                        "new_status": comp_info.get("status"),
                        "detected_at": datetime.utcnow().isoformat(),
                    }
                    self.results["changes"].append(change)
                    logger.warning(
                        f"服务状态变化: {comp_id} {last_comp.get('status')} -> {comp_info.get('status')}"
                    )

        # 检测新事件
        last_incidents = {inc.get("id"): inc for inc in last_snapshot.get("incidents", [])}
        for inc in self.results["incidents"]:
            inc_id = inc.get("id")
            if inc_id and inc_id not in last_incidents:
                change = {
                    "type": "new_incident",
                    "incident_id": inc_id,
                    "title": inc.get("title", ""),
                    "impact": inc.get("impact", ""),
                    "components": inc.get("components", []),
                    "detected_at": datetime.utcnow().isoformat(),
                }
                self.results["changes"].append(change)
                logger.warning(f"新事件: {inc.get('title', '')}")

    def _translate_status(self, status: str) -> str:
        """将状态码翻译为中文"""
        status_map = {
            "operational": "正常运行",
            "degraded_performance": "性能下降",
            "partial_outage": "部分中断",
            "major_outage": "完全中断",
            "under_maintenance": "维护中",
            "unknown": "未知",
        }
        return status_map.get(status, status)

    async def cleanup(self):
        """清理资源"""
        if self.session and not self.session.closed:
            await self.session.close()
            logger.debug("StatusMonitor HTTP session 已关闭")
