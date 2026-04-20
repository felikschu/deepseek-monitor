import unittest

from web.server import build_deepseek_web_summary, is_high_signal_change


class WebLogicTests(unittest.TestCase):
    def test_fake_model_configs_change_is_not_high_signal(self):
        fake_change = {
            "old": {"biz_code": 1, "biz_data": None, "biz_msg": "SETTINGS_NOT_FOUND"},
            "new": {},
        }
        self.assertFalse(is_high_signal_change("model_configs_change", fake_change))

    def test_real_model_configs_change_is_high_signal(self):
        real_change = {
            "old": {"biz_data": {"model_configs": [{"model_type": "chat"}]}},
            "new": {"biz_data": {"model_configs": [{"model_type": "reasoner"}]}},
        }
        self.assertTrue(is_high_signal_change("model_configs_change", real_change))

    def test_bundle_insights_are_high_signal(self):
        self.assertTrue(is_high_signal_change("bundle_insights_change", {"summary": "coder route added"}))

    def test_vendor_runtime_bundle_insights_are_not_high_signal(self):
        self.assertFalse(
            is_high_signal_change(
                "bundle_insights_change",
                {"summary": "vendor noise", "bundle_role": "vendor_runtime"},
            )
        )

    def test_removed_only_api_endpoints_change_is_not_high_signal(self):
        self.assertFalse(
            is_high_signal_change(
                "api_endpoints_change",
                {"new_endpoints": [], "removed_endpoints": ["/api/v0/chat/completion"]},
            )
        )

    def test_build_deepseek_web_summary_merges_public_and_source_signals(self):
        summary = build_deepseek_web_summary(
            {"commit_id": "4b9671fa", "commit_datetime": "2026/04/16 13:01:46"},
            {
                "filename": "main.e0f8beaa34.js",
                "timestamp": "2026-04-20T10:00:00",
                "insights": {
                    "hidden_capabilities": ["CODER 已进入 Agent 路由体系，而不是纯文案占位"],
                    "route_patterns": ["/a/:agentId"],
                    "api_families": ["api/v0/chat"],
                    "coder_signals": ["AgentId.CODER"],
                },
            },
            [
                {
                    "signals": {
                        "models": ["DeepSeek-V3.2"],
                        "headline_lines": ["Launching DeepSeek-V3.2 — Reasoning-first models built for agents."],
                        "pricing_lines": ["DeepSeek API Pricing"],
                    }
                }
            ],
            [{"change_type": "bundle_insights_change", "summary": "main.e0f8beaa34.js 的语义分析结果发生变化", "event_time": "2026-04-20T10:00:00"}],
        )
        self.assertIn("DeepSeek-V3.2", summary["public_signals"]["models"])
        self.assertIn("api/v0/chat", summary["source_signals"]["api_families"])
        self.assertTrue(any("CODER" in item for item in summary["narrative"]))


if __name__ == "__main__":
    unittest.main()
