import unittest

from utils.deepseek_signal_extractor import extract_deepseek_signals
from utils.model_signal_extractor import extract_model_signals


class ExtractorStabilityTests(unittest.TestCase):
    def test_extractors_survive_large_repeated_payloads(self):
        zhipu_blob = (
            'GLM-5.1 GLM-5-Turbo GLM Coding Plan 编码套餐：低至20元包月 Code Interpreter '
            'Web_search_pro 本地私有化解决方案 2000万 Tokens '
        ) * 200
        minimax_blob = (
            'Token Plan Audio Subscription Video Packages Pay as You Go '
            'MiniMax M2.7 MiniMax Speech 2.8 Price $10 /month '
        ) * 200
        deepseek_blob = (
            'Launching DeepSeek-V3.2 Reasoning-first models built for agents '
            'Chat Prefix Completion FIM Completion deepseek-chat deepseek-reasoner $0.14 $0.28 '
        ) * 200

        for _ in range(20):
            zhipu = extract_model_signals(zhipu_blob, "zhipu")
            minimax = extract_model_signals(minimax_blob, "minimax")
            deepseek = extract_deepseek_signals(deepseek_blob, deepseek_blob)

        self.assertIn("GLM-5.1", zhipu["models"])
        self.assertIn("Token Plan", minimax["offerings"])
        self.assertIn("DeepSeek-V3.2", deepseek["models"])
        self.assertTrue(zhipu["commercial_actions"])
        self.assertTrue(minimax["commercial_actions"])


if __name__ == "__main__":
    unittest.main()
