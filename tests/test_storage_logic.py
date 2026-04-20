import tempfile
import unittest
from pathlib import Path

from core.storage import StorageManager


class StorageLogicTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        base = Path(self.temp_dir.name)
        self.storage = StorageManager(
            {
                "storage": {
                    "sqlite_path": str(base / "test.db"),
                    "json_path": str(base / "snapshots"),
                }
            }
        )
        await self.storage.initialize()

    async def asyncTearDown(self):
        await self.storage.close()
        self.temp_dir.cleanup()

    async def test_get_last_surface_snapshot_prefers_latest_id_when_timestamps_match(self):
        cursor = self.storage.conn.cursor()
        cursor.execute(
            """
            INSERT INTO surface_snapshots (
                url, name, category, final_url, title, last_modified, etag,
                content_type, status_code, html_hash, text_hash, signals_json, normalized_text, timestamp
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "https://example.com",
                "Example",
                "docs",
                "https://example.com",
                "old-title",
                "",
                "",
                "text/html",
                200,
                "old-html",
                "old-text",
                "{}",
                "old",
                "2026-04-20 00:00:00",
            ),
        )
        cursor.execute(
            """
            INSERT INTO surface_snapshots (
                url, name, category, final_url, title, last_modified, etag,
                content_type, status_code, html_hash, text_hash, signals_json, normalized_text, timestamp
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "https://example.com",
                "Example",
                "docs",
                "https://example.com",
                "new-title",
                "",
                "",
                "text/html",
                200,
                "new-html",
                "new-text",
                "{}",
                "new",
                "2026-04-20 00:00:00",
            ),
        )
        self.storage.conn.commit()

        snapshot = await self.storage.get_last_surface_snapshot("https://example.com")
        self.assertEqual(snapshot["title"], "new-title")
        self.assertEqual(snapshot["html_hash"], "new-html")

    async def test_get_last_model_config_prefers_latest_id_when_timestamps_match(self):
        cursor = self.storage.conn.cursor()
        cursor.execute(
            """
            INSERT INTO model_configs (config, timestamp)
            VALUES (?, ?)
            """,
            ('{"version": 1}', "2026-04-20 00:00:00"),
        )
        cursor.execute(
            """
            INSERT INTO model_configs (config, timestamp)
            VALUES (?, ?)
            """,
            ('{"version": 2}', "2026-04-20 00:00:00"),
        )
        self.storage.conn.commit()

        config = await self.storage.get_last_model_config()
        self.assertEqual(config["config"]["version"], 2)

    async def test_get_last_huggingface_snapshot_prefers_latest_id_when_timestamps_match(self):
        cursor = self.storage.conn.cursor()
        cursor.execute(
            """
            INSERT INTO huggingface_snapshots (org_name, overview_json, models_json, signals_json, model_count, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "deepseek-ai",
                '{"numModels": 1}',
                '[{"id":"deepseek-ai/DeepSeek-V3.1","name":"DeepSeek-V3.1"}]',
                "{}",
                1,
                "2026-04-20 00:00:00",
            ),
        )
        cursor.execute(
            """
            INSERT INTO huggingface_snapshots (org_name, overview_json, models_json, signals_json, model_count, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "deepseek-ai",
                '{"numModels": 2}',
                '[{"id":"deepseek-ai/DeepSeek-OCR-2","name":"DeepSeek-OCR-2"}]',
                "{}",
                2,
                "2026-04-20 00:00:00",
            ),
        )
        self.storage.conn.commit()

        snapshot = await self.storage.get_last_huggingface_snapshot("deepseek-ai")
        self.assertEqual(snapshot["org"]["numModels"], 2)
        self.assertEqual(snapshot["models"][0]["name"], "DeepSeek-OCR-2")


if __name__ == "__main__":
    unittest.main()
