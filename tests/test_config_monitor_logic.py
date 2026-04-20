import unittest
import sys
import types

if "playwright.async_api" not in sys.modules:
    playwright_module = types.ModuleType("playwright")
    async_api_module = types.ModuleType("playwright.async_api")
    async_api_module.async_playwright = None
    async_api_module.Browser = object
    sys.modules["playwright"] = playwright_module
    sys.modules["playwright.async_api"] = async_api_module

from core.config_monitor import ConfigMonitor


class ConfigMonitorLogicTests(unittest.TestCase):
    def test_normalize_config_for_diff_strips_random_did(self):
        monitor = ConfigMonitor({}, storage=None)
        config = {
            "api_config": {
                "https://chat.deepseek.com/api/v0/client/settings?did=abc&scope=model": {
                    "status": 200,
                }
            }
        }
        normalized = monitor._normalize_config_for_diff(config)
        self.assertIn(
            "https://chat.deepseek.com/api/v0/client/settings?scope=model",
            normalized["api_config"],
        )
        self.assertNotIn(
            "https://chat.deepseek.com/api/v0/client/settings?did=abc&scope=model",
            normalized["api_config"],
        )

    def test_normalize_config_for_diff_strips_volatile_headers(self):
        monitor = ConfigMonitor({}, storage=None)
        config = {
            "api_config": {
                "https://chat.deepseek.com/api/v0/client/settings?scope=model": {
                    "status": 200,
                    "headers": {
                        "content-type": "application/json",
                        "date": "Sun, 19 Apr 2026 16:10:29 GMT",
                        "x-ds-trace-id": "afcaffb98b034e14eb3241fb0ea5b2b0",
                        "x-fetch-after-sec": "300",
                    },
                }
            }
        }

        normalized = monitor._normalize_config_for_diff(config)
        headers = normalized["api_config"][
            "https://chat.deepseek.com/api/v0/client/settings?scope=model"
        ]["headers"]

        self.assertEqual(headers["content-type"], "application/json")
        self.assertEqual(headers["x-fetch-after-sec"], "300")
        self.assertNotIn("date", headers)
        self.assertNotIn("x-ds-trace-id", headers)


if __name__ == "__main__":
    unittest.main()
