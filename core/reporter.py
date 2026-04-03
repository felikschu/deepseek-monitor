"""
报告生成模块

生成监控报告
"""

from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List
from loguru import logger


class Reporter:
    """报告生成器"""

    def __init__(self, config: Dict, storage):
        """初始化报告生成器

        Args:
            config: 配置字典
            storage: 存储管理器
        """
        self.config = config
        self.storage = storage
        self.report_config = config.get("reporting", {})

    async def generate(self, days: int = 7) -> Dict:
        """生成监控报告

        Args:
            days: 报告覆盖天数

        Returns:
            报告字典
        """
        logger.info(f"生成 {days} 天监控报告...")

        report = {
            "period_days": days,
            "generated_at": datetime.now().isoformat(),
            "summary": {},
            "changes": {},
            "metrics": {},
            "recommendations": []
        }

        # 获取变化历史
        changes_history = await self.storage.get_changes_history(days=days)

        # 生成摘要
        report["summary"] = self._generate_summary(changes_history)

        # 按类型分组变化
        report["changes"] = self._group_changes(changes_history)

        # 生成指标统计
        report["metrics"] = await self._generate_metrics(days)

        # 生成建议
        report["recommendations"] = self._generate_recommendations(report)

        # 保存报告
        output_path = await self._save_report(report)

        report["output_path"] = str(output_path)

        return report

    def _generate_summary(self, changes: List[Dict]) -> Dict:
        """生成摘要

        Args:
            changes: 变化列表

        Returns:
            摘要字典
        """
        summary = {
            "total_changes": len(changes),
            "by_type": {},
            "timeline": {}
        }

        # 按类型统计
        for change in changes:
            change_type = change.get("type", "unknown")
            summary["by_type"][change_type] = summary["by_type"].get(change_type, 0) + 1

        # 按日期统计
        for change in changes:
            timestamp = change.get("timestamp", "")
            date = timestamp.split(" ")[0] if timestamp else "unknown"

            if date not in summary["timeline"]:
                summary["timeline"][date] = 0

            summary["timeline"][date] += 1

        return summary

    def _group_changes(self, changes: List[Dict]) -> Dict:
        """按类型分组变化

        Args:
            changes: 变化列表

        Returns:
            分组后的变化字典
        """
        grouped = {
            "frontend": [],
            "config": [],
            "behavior": [],
            "api": [],
            "features": [],
            "other": []
        }

        for change in changes:
            change_type = change.get("type", "")
            data = change.get("data", change)

            if change_type in ["resource_change", "new_resource", "pattern_change"]:
                grouped["frontend"].append(data)
            elif change_type == "config_change":
                grouped["config"].append(data)
            elif change_type == "behavior_change":
                grouped["behavior"].append(data)
            elif change_type == "api_endpoints_change":
                grouped["api"].append(data)
            elif change_type == "new_feature":
                grouped["features"].append(data)
            else:
                grouped["other"].append(data)

        return grouped

    async def _generate_metrics(self, days: int) -> Dict:
        """生成指标统计

        Args:
            days: 天数

        Returns:
            指标字典
        """
        metrics = {
            "check_frequency": {},
            "resource_changes": {},
            "test_results": {}
        }

        # 获取检查结果统计
        # 这里简化处理，实际应该查询数据库

        return metrics

    def _generate_recommendations(self, report: Dict) -> List[str]:
        """生成建议

        Args:
            report: 报告字典

        Returns:
            建议列表
        """
        recommendations = []

        # 基于变化频率给出建议
        frontend_changes = len(report["changes"].get("frontend", []))
        if frontend_changes > 10:
            recommendations.append(
                f"过去 {report['period_days']} 天内检测到 {frontend_changes} 次前端变化，"
                "说明 DeepSeek 正在积极开发新功能，建议关注更新日志。"
            )

        # 基于功能变化给出建议
        features = report["changes"].get("features", [])
        if features:
            recommendations.append(
                f"检测到 {len(features)} 个新功能，建议测试这些新功能并评估其影响。"
            )

        # 基于配置变化给出建议
        config_changes = report["changes"].get("config", [])
        if config_changes:
            recommendations.append(
                f"检测到 {len(config_changes)} 次配置变化，"
                "建议检查是否影响现有功能的可用性。"
            )

        if not recommendations:
            recommendations.append("系统运行正常，未检测到需要特别关注的变化。")

        return recommendations

    async def _save_report(self, report: Dict) -> Path:
        """保存报告

        Args:
            report: 报告字典

        Returns:
            报告文件路径
        """
        # 生成文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_dir = Path(self.report_config.get("output_path", "reports"))
        report_dir.mkdir(parents=True, exist_ok=True)

        # 保存 Markdown 报告
        if "markdown" in self.report_config.get("formats", ["markdown"]):
            md_path = report_dir / f"report_{timestamp}.md"
            await self._save_markdown_report(md_path, report)
            logger.info(f"Markdown 报告已保存: {md_path}")

        # 保存 JSON 报告
        if "json" in self.report_config.get("formats", ["json"]):
            json_path = report_dir / f"report_{timestamp}.json"
            await self.storage.save_report(report)
            return json_path

        return report_dir / f"report_{timestamp}.json"

    async def _save_markdown_report(self, path: Path, report: Dict):
        """保存 Markdown 格式报告

        Args:
            path: 文件路径
            report: 报告字典
        """
        with open(path, 'w', encoding='utf-8') as f:
            # 标题
            f.write("# DeepSeek 网页端变化监控报告\n\n")
            f.write(f"**生成时间**: {report['generated_at']}\n\n")
            f.write(f"**监控周期**: {report['period_days']} 天\n\n")

            # 摘要
            f.write("## 📊 变化摘要\n\n")
            summary = report["summary"]

            f.write(f"- **总变化数**: {summary['total_changes']}\n\n")

            if summary.get("by_type"):
                f.write("### 按类型统计\n\n")
                for change_type, count in summary["by_type"].items():
                    f.write(f"- **{change_type}**: {count}\n")
                f.write("\n")

            if summary.get("timeline"):
                f.write("### 时间线\n\n")
                for date, count in summary["timeline"].items():
                    f.write(f"- **{date}**: {count} 个变化\n")
                f.write("\n")

            # 详细变化
            f.write("## 📝 详细变化\n\n")

            changes = report["changes"]

            # 前端变化
            if changes.get("frontend"):
                f.write("### 前端变化\n\n")
                for change in changes["frontend"][:10]:
                    f.write(f"- {self._format_change_markdown(change)}\n")
                f.write("\n")

            # 配置变化
            if changes.get("config"):
                f.write("### 配置变化\n\n")
                for change in changes["config"][:5]:
                    f.write(f"- {self._format_change_markdown(change)}\n")
                f.write("\n")

            # API 变化
            if changes.get("api"):
                f.write("### API 变化\n\n")
                for change in changes["api"]:
                    f.write(f"- {self._format_change_markdown(change)}\n")
                f.write("\n")

            # 新功能
            if changes.get("features"):
                f.write("### ✨ 新功能\n\n")
                for change in changes["features"]:
                    f.write(f"- **{change.get('feature_name')}**: {change.get('description', '')}\n")
                f.write("\n")

            # 行为变化
            if changes.get("behavior"):
                f.write("### 行为变化\n\n")
                for change in changes["behavior"][:5]:
                    f.write(f"- {self._format_change_markdown(change)}\n")
                f.write("\n")

            # 建议
            f.write("## 💡 建议\n\n")
            for i, recommendation in enumerate(report.get("recommendations", []), 1):
                f.write(f"{i}. {recommendation}\n")
            f.write("\n")

            # 页脚
            f.write("---\n\n")
            f.write("*本报告由 DeepSeek 监控系统自动生成*\n")

    def _format_change_markdown(self, change: Dict) -> str:
        """格式化变化为 Markdown

        Args:
            change: 变化字典

        Returns:
            Markdown 格式的字符串
        """
        change_type = change.get("type", "")

        if change_type == "resource_change":
            return f"文件 `{change['filename']}` hash 变化"

        elif change_type == "new_resource":
            return f"新增文件 `{change['filename']}`"

        elif change_type == "pattern_change":
            return f"代码模式变化: {len(change.get('changes', []))} 处"

        elif change_type == "config_change":
            return f"配置变化: {len(change.get('diff', []))} 处差异"

        elif change_type == "api_endpoints_change":
            parts = []
            if change.get("new_endpoints"):
                parts.append(f"新增 {len(change['new_endpoints'])} 个端点")
            if change.get("removed_endpoints"):
                parts.append(f"移除 {len(change['removed_endpoints'])} 个端点")
            return ", ".join(parts) if parts else "API 端点变化"

        elif change_type == "behavior_change":
            return f"`{change.get('prompt', '')[:30]}...` - {len(change.get('anomalies', []))} 个异常"

        else:
            return str(change)
