import unittest

from core.official_monitor import OfficialMonitor


class OfficialMonitorLogicTests(unittest.TestCase):
    def test_same_raw_signature_does_not_emit_change_even_if_signals_differ(self):
        monitor = OfficialMonitor({}, storage=None)
        page = {"name": "DeepSeek 官网", "category": "official", "url": "https://www.deepseek.com/"}
        previous = {
            "final_url": "https://www.deepseek.com/",
            "last_modified": "Wed, 08 Apr 2026 03:26:06 GMT",
            "etag": '"etag-1"',
            "html_hash": "html-1",
            "text_hash": "text-1",
            "signals": {
                "models": ["DeepSeek-V3"],
                "anchors": [{"href": "https://www.deepseek.com/old"}],
            },
        }
        current = {
            "final_url": "https://www.deepseek.com/",
            "last_modified": "Wed, 08 Apr 2026 03:26:06 GMT",
            "etag": '"etag-1"',
            "html_hash": "html-1",
            "text_hash": "text-1",
            "signals": {
                "models": ["DeepSeek-V3", "DeepSeek-R1"],
                "anchors": [{"href": "https://www.deepseek.com/new"}],
            },
        }

        change = monitor._build_change(page, previous, current)
        self.assertIsNone(change)

    def test_html_change_still_emits_surface_change(self):
        monitor = OfficialMonitor({}, storage=None)
        page = {"name": "DeepSeek 官网", "category": "official", "url": "https://www.deepseek.com/"}
        previous = {
            "final_url": "https://www.deepseek.com/",
            "last_modified": "Wed, 08 Apr 2026 03:26:06 GMT",
            "etag": '"etag-1"',
            "html_hash": "html-1",
            "text_hash": "text-1",
            "signals": {
                "models": ["DeepSeek-V3"],
            },
            "normalized_text": "DeepSeek-V3",
        }
        current = {
            "final_url": "https://www.deepseek.com/",
            "last_modified": "Wed, 08 Apr 2026 03:26:06 GMT",
            "etag": '"etag-2"',
            "html_hash": "html-2",
            "text_hash": "text-2",
            "signals": {
                "models": ["DeepSeek-V3", "DeepSeek-R1"],
            },
            "title": "DeepSeek",
            "normalized_text": "DeepSeek-V3\nDeepSeek-R1",
        }

        change = monitor._build_change(page, previous, current)
        self.assertIsNotNone(change)
        self.assertIn("models", change["changed_signals"])


if __name__ == "__main__":
    unittest.main()
