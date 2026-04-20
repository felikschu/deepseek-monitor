import unittest

from core.huggingface_monitor import HuggingFaceMonitor


class HuggingFaceMonitorLogicTests(unittest.TestCase):
    def test_added_model_is_significant(self):
        monitor = HuggingFaceMonitor({"huggingface": {"enabled": True}}, storage=None)
        previous = {
            "org": {"numModels": 1},
            "models": [
                {
                    "id": "deepseek-ai/DeepSeek-V3.1",
                    "name": "DeepSeek-V3.1",
                    "lastModified": "2025-09-05T11:30:15.000Z",
                }
            ],
        }
        current = {
            "org": {"numModels": 2, "org_url": "https://huggingface.co/deepseek-ai"},
            "models": [
                {
                    "id": "deepseek-ai/DeepSeek-OCR-2",
                    "name": "DeepSeek-OCR-2",
                    "url": "https://huggingface.co/deepseek-ai/DeepSeek-OCR-2",
                    "lastModified": "2026-02-03T00:33:19.000Z",
                },
                {
                    "id": "deepseek-ai/DeepSeek-V3.1",
                    "name": "DeepSeek-V3.1",
                    "lastModified": "2025-09-05T11:30:15.000Z",
                },
            ],
        }

        change = monitor._build_change("deepseek-ai", previous, current)
        self.assertIsNotNone(change)
        self.assertEqual(change["type"], "huggingface_model_change")
        self.assertIn("DeepSeek-OCR-2", change["summary"])
        self.assertEqual(change["source_time"], "2026-02-03T00:33:19.000Z")
        self.assertEqual(change["source_time_type"], "huggingface_last_modified")

    def test_last_modified_update_is_significant(self):
        monitor = HuggingFaceMonitor({"huggingface": {"enabled": True}}, storage=None)
        previous = {
            "org": {"numModels": 1},
            "models": [
                {
                    "id": "deepseek-ai/DeepSeek-V3.2",
                    "name": "DeepSeek-V3.2",
                    "lastModified": "2025-12-01T02:34:49.000Z",
                }
            ],
        }
        current = {
            "org": {"numModels": 1},
            "models": [
                {
                    "id": "deepseek-ai/DeepSeek-V3.2",
                    "name": "DeepSeek-V3.2",
                    "url": "https://huggingface.co/deepseek-ai/DeepSeek-V3.2",
                    "lastModified": "2025-12-01T11:04:59.000Z",
                }
            ],
        }

        change = monitor._build_change("deepseek-ai", previous, current)
        self.assertIsNotNone(change)
        self.assertEqual(change["updated_models"][0]["name"], "DeepSeek-V3.2")
        self.assertIn("最近更新时间变化", change["summary"])


if __name__ == "__main__":
    unittest.main()
