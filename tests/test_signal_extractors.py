import unittest

from utils.deepseek_signal_extractor import extract_deepseek_signals
from utils.model_signal_extractor import extract_model_signals
from utils.source_probe import merge_signal_maps, pick_interesting_links


class SignalExtractorTests(unittest.TestCase):
    def test_zhipu_pricing_and_offerings_are_extracted(self):
        sample = """
        placard:{title:"邀你体验",subTitle:"智谱GLM-5.1新旗舰",tips:"注册即享卓越模型体验",
        liTxt2:"新用户注册得",liTxt2Num:"2000万 Tokens",liTxt3:"，新模型免费玩到爽！"}
        {name:"GLM-5.1",inPrice:["6元"],outPrice:["24元"],storage:"限时免费"}
        {label:"Code Interpreter",privatePrice:"限时免费"}
        {label:"Web_search_pro",privatePrice:"限时免费"}
        """
        signals = extract_model_signals(sample, "zhipu")
        self.assertIn("GLM-5.1", signals["models"])
        self.assertIn("6元", signals["prices"])
        self.assertTrue(any("GLM-5.1" in line for line in signals["pricing_lines"]))
        self.assertIn("Code Interpreter", signals["offerings"])
        self.assertTrue(any("2000万 Tokens" in action for action in signals["commercial_actions"]))

    def test_minimax_business_keywords_extract_cleanly(self):
        sample = """
        Pricing Overview
        Token Plan
        Audio Subscription
        Video Packages
        Pay as You Go
        MiniMax M2.7
        MiniMax Speech 2.8
        Price | $10 /month | $20 /month | $50 /month
        """
        signals = extract_model_signals(sample, "minimax")
        self.assertIn("Token Plan", signals["offerings"])
        self.assertIn("Audio Subscription", signals["offerings"])
        self.assertIn("MiniMax M2.7", signals["models"])
        self.assertIn("$10", signals["prices"])
        self.assertTrue(any("Token Plan 月付档位" in action for action in signals["commercial_actions"]))

    def test_deepseek_headlines_are_human_readable(self):
        html = """
        <html><body>
        <div>🎉 Launching DeepSeek-V3.2 — Reasoning-first models built for agents. Now available on web, app & API.</div>
        <div>Chat Prefix Completion</div>
        <div>FIM Completion</div>
        </body></html>
        """
        signals = extract_deepseek_signals(
            html,
            "Launching DeepSeek-V3.2 — Reasoning-first models built for agents.\nChat Prefix Completion\nFIM Completion",
        )
        self.assertIn("DeepSeek-V3.2", signals["models"])
        self.assertTrue(any("Reasoning-first models built for agents" in line for line in signals["headline_lines"]))
        self.assertIn("Chat Prefix Completion", signals["coding_signals"])

    def test_merge_signal_maps_dedupes_lists(self):
        merged = merge_signal_maps(
            {"models": ["GLM-5.1"], "meta": {"a": 1}},
            {"models": ["GLM-5.1", "GLM-5-Turbo"], "meta": {"b": 2}},
        )
        self.assertEqual(merged["models"], ["GLM-5.1", "GLM-5-Turbo"])
        self.assertEqual(merged["meta"], {"a": 1, "b": 2})

    def test_price_filter_skips_benchmark_like_dollar_amounts(self):
        noisy = "Vending Bench leaderboard shows $4432 score equivalent."
        priced = '{name:"GLM-5.1",inPrice:["6元"],outPrice:["24元"]}'
        noisy_signals = extract_model_signals(noisy, "zhipu")
        priced_signals = extract_model_signals(priced, "zhipu")
        self.assertNotIn("$4432", noisy_signals["prices"])
        self.assertIn("6元", priced_signals["prices"])

    def test_pick_interesting_links_filters_to_relevant_paths(self):
        links = [
            "https://platform.minimax.io/docs/guides/pricing-token-plan",
            "https://platform.minimax.io/docs/token-plan/promotion",
            "https://platform.minimax.io/docs/faq/history-modelinfo",
            "https://www.example.com/unrelated",
        ]
        picked = pick_interesting_links(
            "https://www.minimax.io/",
            links,
            allowed_site_keys=["minimax.io"],
            limit=10,
        )
        self.assertIn("https://platform.minimax.io/docs/guides/pricing-token-plan", picked)
        self.assertIn("https://platform.minimax.io/docs/token-plan/promotion", picked)
        self.assertNotIn("https://platform.minimax.io/docs/faq/history-modelinfo", picked)


if __name__ == "__main__":
    unittest.main()
