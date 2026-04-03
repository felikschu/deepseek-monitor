"""
告警模块

负责检测变化并发送告警通知
"""

from typing import Dict, List
from loguru import logger


class Alerter:
    """告警器"""

    def __init__(self, config: Dict, storage):
        """初始化告警器

        Args:
            config: 配置字典
            storage: 存储管理器
        """
        self.config = config
        self.storage = storage
        self.alert_config = config.get("alerts", {})

    async def process_and_alert(self, results: Dict):
        """处理结果并发送告警

        Args:
            results: 检查结果字典
        """
        if not self.alert_config.get("enabled", True):
            logger.info("告警功能已禁用")
            return

        # 收集所有变化
        all_changes = self._collect_all_changes(results)

        if not all_changes:
            logger.info("没有检测到变化，无需告警")
            return

        logger.info(f"检测到 {len(all_changes)} 个变化，准备发送告警...")

        # 根据配置发送告警
        methods = self.alert_config.get("methods", ["console"])

        for method in methods:
            if method == "console":
                self._send_console_alert(all_changes)
            elif method == "email":
                await self._send_email_alert(all_changes)
            elif method == "webhook":
                await self._send_webhook_alert(all_changes)

    def _collect_all_changes(self, results: Dict) -> List[Dict]:
        """收集所有变化

        Args:
            results: 检查结果

        Returns:
            变化列表
        """
        all_changes = []

        checks = results.get("checks", {})

        # 前端变化
        frontend_changes = checks.get("frontend", {}).get("changes", [])
        all_changes.extend(frontend_changes)

        # 配置变化
        config_changes = checks.get("config", {}).get("changes", [])
        all_changes.extend(config_changes)

        # 行为变化
        behavior_changes = checks.get("behavior", {}).get("changes", [])
        all_changes.extend(behavior_changes)

        return all_changes

    def _send_console_alert(self, changes: List[Dict]):
        """发送控制台告警

        Args:
            changes: 变化列表
        """
        print("\n" + "!" * 60)
        print("🚨 检测到 DeepSeek 网页端变化！")
        print("!" * 60 + "\n")

        # 按类型分组
        changes_by_type = {}
        for change in changes:
            change_type = change.get("type", "unknown")
            if change_type not in changes_by_type:
                changes_by_type[change_type] = []
            changes_by_type[change_type].append(change)

        # 打印每种类型的变化
        for change_type, type_changes in changes_by_type.items():
            print(f"\n【{change_type.upper()}】({len(type_changes)} 个)")

            for i, change in enumerate(type_changes[:5], 1):  # 只显示前5个
                print(f"\n  {i}. {self._format_change(change)}")

            if len(type_changes) > 5:
                print(f"\n  ... 还有 {len(type_changes) - 5} 个变化")

        print("\n" + "=" * 60 + "\n")

    def _format_change(self, change: Dict) -> str:
        """格式化变化描述

        Args:
            change: 变化字典

        Returns:
            格式化的描述
        """
        change_type = change.get("type", "")

        if change_type == "resource_change":
            return f"文件变化: {change['filename']}\n     Hash: {change['old_hash'][:8]}... → {change['new_hash'][:8]}..."

        elif change_type == "new_resource":
            return f"新增文件: {change['filename']}"

        elif change_type == "pattern_change":
            return f"代码模式变化: {change['filename']}"

        elif change_type == "new_feature":
            return f"新功能: {change['feature_name']}\n    {change['description']}"

        elif change_type == "config_change":
            return f"配置变化: {len(change['diff'])} 处差异"

        elif change_type == "api_endpoints_change":
            desc = []
            if change.get("new_endpoints"):
                desc.append(f"新增 {len(change['new_endpoints'])} 个端点")
            if change.get("removed_endpoints"):
                desc.append(f"移除 {len(change['removed_endpoints'])} 个端点")
            return ", ".join(desc)

        elif change_type == "behavior_change":
            return f"行为变化: {change['prompt'][:30]}...\n    异常: {len(change['anomalies'])} 个"

        else:
            return str(change)

    async def _send_email_alert(self, changes: List[Dict]):
        """发送邮件告警

        Args:
            changes: 变化列表
        """
        # TODO: 实现邮件发送
        logger.warning("邮件告警功能尚未实现")
        pass

    async def _send_webhook_alert(self, changes: List[Dict]):
        """发送 Webhook 告警

        Args:
            changes: 变化列表
        """
        # TODO: 实现 Webhook 发送
        logger.warning("Webhook 告警功能尚未实现")
        pass
