import unittest

from core.competitor_monitor import CompetitorMonitor


class CompetitorMonitorLogicTests(unittest.TestCase):
    def test_added_commercial_actions_are_significant(self):
        monitor = CompetitorMonitor({"competitor_surfaces": {"enabled": True}}, storage=None)
        previous = {
            "signals": {
                "models": ["GLM-5-Turbo"],
                "commercial_actions": [],
            }
        }
        current = {
            "final_url": "https://www.zhipuai.cn/zh/research/156",
            "signals": {
                "models": ["GLM-5-Turbo"],
                "commercial_actions": ["GLM-5V-Turbo 已出现纳入 Coding Plan 的申请/预告文案"],
                "headline_lines": ["GLM-5V-Turbo发布：多模态Coding基座模型"],
            },
            "last_modified": "",
        }
        page = {
            "vendor": "zhipu",
            "name": "智谱 GLM-5V-Turbo 研究页",
            "url": "https://www.zhipuai.cn/zh/research/156",
        }
        change = monitor._build_change(page, previous, current)
        self.assertIsNotNone(change)
        self.assertEqual(change["summary"], "智谱 GLM-5V-Turbo 研究页 出现新的商业化动作")
        self.assertEqual(change["source_time_type"], "scraped_signal")

    def test_article_date_is_used_when_http_last_modified_missing(self):
        monitor = CompetitorMonitor({"competitor_surfaces": {"enabled": True}}, storage=None)
        previous = {"signals": {"models": []}}
        current = {
            "final_url": "https://www.minimax.io/news/minimax-mcp",
            "signals": {
                "models": [],
                "commercial_actions": ["MCP Tools 已上线并兼容多家 Agent 客户端"],
                "article_dates": ["2026-04-19T09:57:06.216Z"],
            },
            "last_modified": "",
        }
        page = {
            "vendor": "minimax",
            "name": "MiniMax MCP News",
            "url": "https://www.minimax.io/news/minimax-mcp",
        }
        change = monitor._build_change(page, previous, current)
        self.assertEqual(change["source_time"], "2026-04-19T09:57:06.216Z")
        self.assertEqual(change["source_time_type"], "page_date_signal")


if __name__ == "__main__":
    unittest.main()
