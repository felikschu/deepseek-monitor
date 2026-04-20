#!/usr/bin/env python3
"""
DeepSeek 网页端变化追踪系统 - 主监控脚本

监控内容：
1. 前端资源变化（JS/CSS 文件 hash）
2. 模型配置变化（通过 Feature Flag）
3. 行为特征变化（通过测试用例）
4. API 端点变化
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime
from loguru import logger

# 添加项目根目录到 Python 路径
ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from core.storage import StorageManager
from core.alerter import Alerter
from core.reporter import Reporter
from utils.config import load_config


class DeepSeekMonitor:
    """DeepSeek 网页端变化追踪主控制器"""

    def __init__(self, config_path: str = None):
        """初始化监控系统

        Args:
            config_path: 配置文件路径
        """
        # 加载配置
        self.config = load_config(config_path or ROOT_DIR / "config.yaml")

        # 配置日志
        self._setup_logging()

        # 初始化组件
        self.storage = StorageManager(self.config)
        self.alerter = Alerter(self.config, self.storage)
        self.reporter = Reporter(self.config, self.storage)

        # 监控器实例
        self.frontend_monitor = None
        self.official_monitor = None
        self.config_monitor = None
        self.behavior_monitor = None
        self.github_monitor = None
        self.status_monitor = None
        self.competitor_monitor = None
        self.huggingface_monitor = None

        logger.info("DeepSeek 监控系统初始化完成")

    def _setup_logging(self):
        """配置日志系统"""
        log_config = self.config.get("logging", {})

        # 移除默认处理器
        logger.remove()

        # 添加控制台处理器
        if log_config.get("console", True):
            logger.add(
                sys.stderr,
                level=log_config.get("level", "INFO"),
                format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>"
            )

        # 添加文件处理器
        if log_config.get("file_path"):
            log_file = ROOT_DIR / log_config["file_path"]
            log_file.parent.mkdir(parents=True, exist_ok=True)
            rotation_cfg = log_config.get("rotation", {})
            rotation = None
            if isinstance(rotation_cfg, dict):
                max_size_mb = rotation_cfg.get("max_size_mb")
                if max_size_mb:
                    rotation = f"{max_size_mb} MB"
            elif rotation_cfg:
                rotation = rotation_cfg

            logger.add(
                log_file,
                level=log_config.get("level", "INFO"),
                rotation=rotation,
                retention="30 days",
                format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}"
            )

    async def initialize(self):
        """初始化所有监控器"""
        logger.info("正在初始化监控器...")

        from core.frontend_monitor import FrontendMonitor

        self.frontend_monitor = FrontendMonitor(self.config, self.storage)

        # 初始化数据库
        await self.storage.initialize()

        logger.info("所有监控器初始化完成")

    async def run_full_check(self):
        """执行完整监控检查

        Returns:
            dict: 检查结果摘要
        """
        logger.info("=" * 60)
        logger.info("开始执行完整监控检查")
        logger.info("=" * 60)

        results = {
            "timestamp": datetime.now().isoformat(),
            "checks": {}
        }

        try:
            # 1. 前端资源监控
            logger.info("\n[1/7] 检查前端资源变化...")
            frontend_results = await self.frontend_monitor.check()
            results["checks"]["frontend"] = frontend_results
            logger.info(f"前端资源检查完成: {len(frontend_results.get('changes', []))} 个变化")

            # 2. 配置监控
            logger.info("\n[2/7] 检查模型配置变化...")
            if self.config_monitor is None:
                from core.config_monitor import ConfigMonitor
                self.config_monitor = ConfigMonitor(self.config, self.storage)
            config_results = await self.config_monitor.check()
            results["checks"]["config"] = config_results
            logger.info(f"配置检查完成: {len(config_results.get('changes', []))} 个变化")

            # 3. 行为监控（这个比较慢，可选）
            behavior_enabled = self.config.get("behavior", {}).get("enabled", True)
            if behavior_enabled:
                logger.info("\n[3/7] 检查行为特征变化...")
                if self.behavior_monitor is None:
                    from core.behavior_monitor import BehaviorMonitor
                    self.behavior_monitor = BehaviorMonitor(self.config, self.storage)
                behavior_results = await self.behavior_monitor.check()
                results["checks"]["behavior"] = behavior_results
                logger.info(f"行为检查完成: {len(behavior_results.get('changes', []))} 个变化")
            else:
                logger.info("\n[3/7] 跳过行为特征检查（已禁用）")
                results["checks"]["behavior"] = {"status": "disabled"}

            # 4. 官方页面/文档监控
            logger.info("\n[4/7] 检查官网与文档页变化...")
            if self.official_monitor is None:
                from core.official_monitor import OfficialMonitor
                self.official_monitor = OfficialMonitor(self.config, self.storage)
            official_results = await self.official_monitor.check()
            results["checks"]["official"] = official_results
            logger.info(f"官方页面检查完成: {len(official_results.get('changes', []))} 个变化")

            # 5. GitHub / Status
            logger.info("\n[5/7] 检查 GitHub 与 Status Page...")
            if self.github_monitor is None:
                from core.github_monitor import GitHubMonitor
                self.github_monitor = GitHubMonitor(self.config, self.storage)
            if self.status_monitor is None:
                from core.status_monitor import StatusMonitor
                self.status_monitor = StatusMonitor(self.config, self.storage)
            results["checks"]["github"] = await self.github_monitor.check()
            results["checks"]["status"] = await self.status_monitor.check()
            logger.info(
                f"GitHub 变化: {len(results['checks']['github'].get('changes', []))}，"
                f"Status 变化: {len(results['checks']['status'].get('changes', []))}"
            )

            # 6. 竞品侦察
            logger.info("\n[6/7] 检查竞品型号与价格信号...")
            if self.competitor_monitor is None:
                from core.competitor_monitor import CompetitorMonitor
                self.competitor_monitor = CompetitorMonitor(self.config, self.storage)
            competitor_results = await self.competitor_monitor.check()
            results["checks"]["competitor"] = competitor_results
            logger.info(f"竞品侦察完成: {len(competitor_results.get('changes', []))} 个变化")

            # 7. Hugging Face 官方组织
            logger.info("\n[7/7] 检查 Hugging Face 官方组织动向...")
            if self.huggingface_monitor is None:
                from core.huggingface_monitor import HuggingFaceMonitor
                self.huggingface_monitor = HuggingFaceMonitor(self.config, self.storage)
            huggingface_results = await self.huggingface_monitor.check()
            results["checks"]["huggingface"] = huggingface_results
            logger.info(f"Hugging Face 检查完成: {len(huggingface_results.get('changes', []))} 个变化")

        except Exception as e:
            logger.error(f"监控检查失败: {e}", exc_info=True)
            results["error"] = str(e)

        # 保存结果
        await self.storage.save_check_results(results)

        # 生成告警
        await self.alerter.process_and_alert(results)

        logger.info("\n" + "=" * 60)
        logger.info("监控检查完成")
        logger.info("=" * 60)

        return results

    async def run_frontend_check_only(self):
        """只运行前端资源检查（快速检查）"""
        logger.info("执行前端资源快速检查...")

        results = await self.frontend_monitor.check()
        await self.storage.save_check_results(results)

        return results

    async def generate_report(self, days: int = 7):
        """生成监控报告

        Args:
            days: 报告覆盖的天数
        """
        logger.info(f"生成过去 {days} 天的监控报告...")

        report = await self.reporter.generate(days=days)
        await self.storage.save_report(report)

        logger.info(f"报告已生成: {report.get('output_path')}")

        return report

    async def run_continuous_monitoring(self):
        """运行持续监控（按配置的间隔定期检查）"""
        interval_hours = self.config.get("monitoring", {}).get("check_interval_hours", 3)

        logger.info(f"启动持续监控模式，检查间隔: {interval_hours} 小时")
        logger.info("按 Ctrl+C 停止监控")

        try:
            while True:
                await self.run_full_check()

                logger.info(f"\n下一次检查将在 {interval_hours} 小时后执行...")
                await asyncio.sleep(interval_hours * 3600)

        except KeyboardInterrupt:
            logger.info("\n监控已手动停止")

    async def cleanup(self):
        """清理资源"""
        logger.info("清理资源...")

        if self.frontend_monitor:
            await self.frontend_monitor.cleanup()
        if self.official_monitor:
            await self.official_monitor.cleanup()
        if self.config_monitor:
            await self.config_monitor.cleanup()
        if self.behavior_monitor:
            await self.behavior_monitor.cleanup()
        if self.github_monitor:
            await self.github_monitor.cleanup()
        if self.status_monitor:
            await self.status_monitor.cleanup()
        if self.competitor_monitor:
            await self.competitor_monitor.cleanup()
        if self.huggingface_monitor:
            await self.huggingface_monitor.cleanup()

        await self.storage.close()

        logger.info("资源清理完成")


async def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="DeepSeek 网页端变化追踪系统")
    parser.add_argument("--config", "-c", help="配置文件路径", default=None)
    parser.add_argument("--mode", "-m", choices=["full", "frontend", "report", "continuous"],
                       default="full", help="运行模式")
    parser.add_argument("--report-days", type=int, default=7, help="报告覆盖天数")

    args = parser.parse_args()

    # 创建监控器
    monitor = DeepSeekMonitor(args.config)
    await monitor.initialize()

    try:
        if args.mode == "full":
            # 完整检查
            results = await monitor.run_full_check()

            # 打印摘要
            print("\n" + "=" * 60)
            print("检查结果摘要")
            print("=" * 60)
            for check_name, check_result in results.get("checks", {}).items():
                changes = check_result.get("changes", [])
                print(f"{check_name}: {len(changes)} 个变化")
            print("=" * 60)

        elif args.mode == "frontend":
            # 仅前端检查
            results = await monitor.run_frontend_check_only()
            print(f"前端检查完成: {len(results.get('changes', []))} 个变化")

        elif args.mode == "report":
            # 生成报告
            report = await monitor.generate_report(days=args.report_days)
            print(f"报告已生成: {report.get('output_path')}")

        elif args.mode == "continuous":
            # 持续监控
            await monitor.run_continuous_monitoring()

    finally:
        await monitor.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
