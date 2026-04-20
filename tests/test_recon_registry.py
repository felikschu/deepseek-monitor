import unittest

from utils.generic_signal_extractor import extract_generic_signals
from utils.recon_registry import build_signal_extractor, infer_extractor_name


class ReconRegistryTests(unittest.TestCase):
    def test_infer_extractor_name_from_known_hosts(self):
        self.assertEqual(infer_extractor_name("https://www.deepseek.com/en/"), "deepseek")
        self.assertEqual(infer_extractor_name("https://open.bigmodel.cn/"), "zhipu")
        self.assertEqual(infer_extractor_name("https://www.minimax.io/news"), "minimax")

    def test_infer_extractor_name_falls_back_to_generic(self):
        self.assertEqual(infer_extractor_name("https://example.com/"), "generic")

    def test_generic_signal_extractor_keeps_dates_prices_and_versions(self):
        signals = extract_generic_signals(
            "",
            "\n".join(
                [
                    "Pricing updated on 2026-04-20 with Starter $10 /month and Pro $50 /month",
                    "Version v1.2.3 is now available",
                ]
            ),
        )
        self.assertIn("2026-04-20", signals["dates"])
        self.assertIn("$10", signals["prices"])
        self.assertIn("v1.2.3", signals["resource_versions"])

    def test_build_signal_extractor_returns_callable_for_vendor(self):
        extractor = build_signal_extractor("zhipu")
        signals = extractor("GLM-5.1 与 GLM-5V-Turbo", "")
        self.assertIn("GLM-5.1", signals["models"])


if __name__ == "__main__":
    unittest.main()
