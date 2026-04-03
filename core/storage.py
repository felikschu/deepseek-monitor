"""
存储管理模块

负责所有数据的存储和检索：
1. SQLite 数据库管理
2. 历史数据查询
3. 报告生成
"""

import sqlite3
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from loguru import logger


class StorageManager:
    """存储管理器"""

    def __init__(self, config: Dict):
        """初始化存储管理器

        Args:
            config: 配置字典
        """
        self.config = config
        storage_config = config.get("storage", {})

        # 数据库路径
        self.db_path = Path(storage_config.get("sqlite_path", "data/deepseek_monitor.db"))
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # JSON 存储路径
        self.json_path = Path(storage_config.get("json_path", "data/snapshots"))
        self.json_path.mkdir(parents=True, exist_ok=True)

        self.conn = None

    async def initialize(self):
        """初始化数据库（创建表）"""
        logger.info("初始化数据库...")

        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row  # 返回字典格式

        self._create_tables()

        logger.info(f"数据库已初始化: {self.db_path}")

    def _create_tables(self):
        """创建所有表"""
        cursor = self.conn.cursor()

        # 资源 hash 表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS resource_hashes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL,
                hash TEXT NOT NULL,
                url TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(filename, timestamp)
            )
        """)

        # 代码模式表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS code_patterns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL,
                patterns TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 模型配置表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS model_configs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                config TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # API 端点表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS api_endpoints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                endpoints TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 测试结果表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS test_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                prompt TEXT NOT NULL,
                category TEXT,
                response TEXT,
                metrics TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 检查结果表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS check_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                check_type TEXT NOT NULL,
                results TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 功能检测表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS detected_features (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                feature_name TEXT NOT NULL UNIQUE,
                first_detected DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_seen DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 变化历史表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS changes_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                change_type TEXT NOT NULL,
                change_data TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # commit 历史表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS commit_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                commit_id TEXT NOT NULL,
                commit_datetime TEXT,
                package_version TEXT,
                api_version TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # feature flags 快照表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS feature_flags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                flags TEXT NOT NULL,
                flag_count INTEGER,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 法律文档更新记录表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS legal_docs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                doc_name TEXT NOT NULL,
                last_modified TEXT NOT NULL,
                url TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # CDN 资源修改时间表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cdn_resources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL,
                last_modified TEXT NOT NULL,
                etag TEXT,
                content_length INTEGER,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 创建索引
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_resource_hashes_filename ON resource_hashes(filename)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_test_results_prompt ON test_results(prompt)")
        # GitHub 监控相关表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS github_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                repos TEXT NOT NULL,
                repo_count INTEGER,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS github_releases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                repo_name TEXT NOT NULL,
                tag_name TEXT NOT NULL,
                published_at TEXT,
                release_data TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(repo_name, tag_name)
            )
        """)

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_changes_history_type ON changes_history(change_type)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_commit_history_id ON commit_history(commit_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_legal_docs_name ON legal_docs(doc_name)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_github_releases_repo ON github_releases(repo_name)")

        self.conn.commit()

    async def save_resource_hash(self, filename: str, file_hash: str, url: str):
        """保存资源 hash

        Args:
            filename: 文件名
            file_hash: 文件 hash
            url: 文件 URL
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO resource_hashes (filename, hash, url)
            VALUES (?, ?, ?)
        """, (filename, file_hash, url))
        self.conn.commit()

    async def get_last_resource_hash(self, filename: str) -> Optional[Dict]:
        """获取最近的资源 hash

        Args:
            filename: 文件名

        Returns:
            hash 字典或 None
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT filename, hash, url, timestamp
            FROM resource_hashes
            WHERE filename = ?
            ORDER BY timestamp DESC
            LIMIT 1
        """, (filename,))

        row = cursor.fetchone()
        if row:
            return dict(row)
        return None

    async def save_code_patterns(self, filename: str, patterns: Dict):
        """保存代码模式

        Args:
            filename: 文件名
            patterns: 模式字典
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO code_patterns (filename, patterns)
            VALUES (?, ?)
        """, (filename, json.dumps(patterns, ensure_ascii=False)))
        self.conn.commit()

    async def get_last_code_patterns(self, filename: str) -> Optional[Dict]:
        """获取最近的代码模式

        Args:
            filename: 文件名

        Returns:
            模式字典或 None
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT filename, patterns, timestamp
            FROM code_patterns
            WHERE filename = ?
            ORDER BY timestamp DESC
            LIMIT 1
        """, (filename,))

        row = cursor.fetchone()
        if row:
            return {
                "filename": row["filename"],
                "patterns": json.loads(row["patterns"]),
                "timestamp": row["timestamp"]
            }
        return None

    async def save_model_config(self, config: Dict):
        """保存模型配置

        Args:
            config: 配置字典
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO model_configs (config)
            VALUES (?)
        """, (json.dumps(config, ensure_ascii=False, default=str),))
        self.conn.commit()

    async def get_last_model_config(self) -> Optional[Dict]:
        """获取最近的模型配置

        Returns:
            配置字典或 None
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT config, timestamp
            FROM model_configs
            ORDER BY timestamp DESC
            LIMIT 1
        """)

        row = cursor.fetchone()
        if row:
            return {
                "config": json.loads(row["config"]),
                "timestamp": row["timestamp"]
            }
        return None

    async def save_api_endpoints(self, endpoints: List[str]):
        """保存 API 端点

        Args:
            endpoints: 端点列表
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO api_endpoints (endpoints)
            VALUES (?)
        """, (json.dumps(endpoints),))
        self.conn.commit()

    async def get_last_api_endpoints(self) -> Optional[Dict]:
        """获取最近的 API 端点

        Returns:
            端点字典或 None
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT endpoints, timestamp
            FROM api_endpoints
            ORDER BY timestamp DESC
            LIMIT 1
        """)

        row = cursor.fetchone()
        if row:
            return {
                "endpoints": json.loads(row["endpoints"]),
                "timestamp": row["timestamp"]
            }
        return None

    async def save_test_result(self, test_case: Dict, result: Dict):
        """保存测试结果

        Args:
            test_case: 测试用例
            result: 测试结果
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO test_results (prompt, category, response, metrics)
            VALUES (?, ?, ?, ?)
        """, (
            result.get("prompt", ""),
            result.get("category", ""),
            result.get("response", ""),
            json.dumps(result.get("metrics", {}), default=str)
        ))
        self.conn.commit()

    async def get_historical_test_results(self, days: int = 7) -> List[Dict]:
        """获取历史测试结果

        Args:
            days: 天数

        Returns:
            测试结果列表
        """
        cursor = self.conn.cursor()
        cutoff_date = datetime.now() - timedelta(days=days)

        cursor.execute("""
            SELECT prompt, category, response, metrics, timestamp
            FROM test_results
            WHERE timestamp >= ?
            ORDER BY timestamp DESC
        """, (cutoff_date,))

        results = []
        for row in cursor.fetchall():
            results.append({
                "prompt": row["prompt"],
                "category": row["category"],
                "response": row["response"],
                "metrics": json.loads(row["metrics"]),
                "timestamp": row["timestamp"]
            })

        return results

    async def save_change(self, change_type: str, change_data: Dict):
        """保存单条变化记录

        Args:
            change_type: 变化类型
            change_data: 变化数据
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO changes_history (change_type, change_data)
            VALUES (?, ?)
        """, (change_type, json.dumps(change_data, ensure_ascii=False, default=str)))
        self.conn.commit()

    async def save_check_results(self, results: Dict):
        """保存检查结果

        Args:
            results: 结果字典
        """
        cursor = self.conn.cursor()

        # 保存完整结果
        cursor.execute("""
            INSERT INTO check_results (check_type, results)
            VALUES (?, ?)
        """, ("full", json.dumps(results, ensure_ascii=False, default=str)))

        # 保存变化记录
        changes = results.get("checks", {}).get("frontend", {}).get("changes", [])
        changes.extend(results.get("checks", {}).get("config", {}).get("changes", []))
        changes.extend(results.get("checks", {}).get("behavior", {}).get("changes", []))

        for change in changes:
            cursor.execute("""
                INSERT INTO changes_history (change_type, change_data)
                VALUES (?, ?)
            """, (change.get("type", "unknown"), json.dumps(change, ensure_ascii=False, default=str)))

        self.conn.commit()

    async def was_feature_detected(self, feature_name: str) -> bool:
        """检查功能是否已被检测到

        Args:
            feature_name: 功能名称

        Returns:
            是否已检测到
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT id FROM detected_features
            WHERE feature_name = ?
        """, (feature_name,))

        return cursor.fetchone() is not None

    async def mark_feature_detected(self, feature_name: str):
        """标记功能为已检测

        Args:
            feature_name: 功能名称
        """
        cursor = self.conn.cursor()

        # 检查是否已存在
        if await self.was_feature_detected(feature_name):
            # 更新 last_seen
            cursor.execute("""
                UPDATE detected_features
                SET last_seen = CURRENT_TIMESTAMP
                WHERE feature_name = ?
            """, (feature_name,))
        else:
            # 插入新记录
            cursor.execute("""
                INSERT INTO detected_features (feature_name)
                VALUES (?)
            """, (feature_name,))

        self.conn.commit()

    async def save_report(self, report: Dict):
        """保存报告

        Args:
            report: 报告字典
        """
        # 保存为 JSON
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = self.json_path / f"report_{timestamp}.json"

        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        logger.info(f"报告已保存: {report_path}")

    async def get_changes_history(self, days: int = 30) -> List[Dict]:
        """获取变化历史

        Args:
            days: 天数

        Returns:
            变化列表
        """
        cursor = self.conn.cursor()
        cutoff_date = datetime.now() - timedelta(days=days)

        cursor.execute("""
            SELECT change_type, change_data, timestamp
            FROM changes_history
            WHERE timestamp >= ?
            ORDER BY timestamp DESC
        """, (cutoff_date,))

        changes = []
        for row in cursor.fetchall():
            changes.append({
                "type": row["change_type"],
                "data": json.loads(row["change_data"]),
                "timestamp": row["timestamp"]
            })

        return changes

    async def save_commit(self, commit_id: str, commit_datetime: str = None,
                         package_version: str = None, api_version: str = None):
        """保存 commit 信息

        Args:
            commit_id: commit hash
            commit_datetime: commit 时间
            package_version: 前端包版本
            api_version: API 版本
        """
        cursor = self.conn.cursor()

        # 检查是否与上次相同
        last = await self.get_last_commit()
        if last and last["commit_id"] == commit_id:
            return False  # 无变化

        cursor.execute("""
            INSERT INTO commit_history (commit_id, commit_datetime, package_version, api_version)
            VALUES (?, ?, ?, ?)
        """, (commit_id, commit_datetime, package_version, api_version))
        self.conn.commit()
        return True  # 新 commit

    async def get_last_commit(self) -> Optional[Dict]:
        """获取最近的 commit 信息"""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT commit_id, commit_datetime, package_version, api_version, timestamp
            FROM commit_history
            ORDER BY timestamp DESC
            LIMIT 1
        """)
        row = cursor.fetchone()
        return dict(row) if row else None

    async def save_feature_flags(self, flags: Dict):
        """保存 feature flags 快照

        Args:
            flags: {flag_name: default_value} 字典
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO feature_flags (flags, flag_count)
            VALUES (?, ?)
        """, (json.dumps(flags, ensure_ascii=False), len(flags)))
        self.conn.commit()

    async def get_last_feature_flags(self) -> Optional[Dict]:
        """获取最近的 feature flags 快照"""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT flags, flag_count, timestamp
            FROM feature_flags
            ORDER BY timestamp DESC
            LIMIT 1
        """)
        row = cursor.fetchone()
        if row:
            return {
                "flags": json.loads(row["flags"]),
                "count": row["flag_count"],
                "timestamp": row["timestamp"]
            }
        return None

    async def save_legal_doc(self, doc_name: str, last_modified: str, url: str):
        """保存法律文档修改时间

        Args:
            doc_name: 文档名称
            last_modified: Last-Modified 头的值
            url: 文档 URL
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO legal_docs (doc_name, last_modified, url)
            VALUES (?, ?, ?)
        """, (doc_name, last_modified, url))
        self.conn.commit()

    async def get_last_legal_doc(self, doc_name: str) -> Optional[Dict]:
        """获取法律文档最近一次记录"""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT doc_name, last_modified, url, timestamp
            FROM legal_docs
            WHERE doc_name = ?
            ORDER BY timestamp DESC
            LIMIT 1
        """, (doc_name,))
        row = cursor.fetchone()
        return dict(row) if row else None

    async def save_cdn_resource(self, filename: str, last_modified: str,
                                etag: str = None, content_length: int = None):
        """保存 CDN 资源修改信息

        Args:
            filename: 文件名
            last_modified: Last-Modified 头的值
            etag: ETag 头的值
            content_length: 内容长度
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO cdn_resources (filename, last_modified, etag, content_length)
            VALUES (?, ?, ?, ?)
        """, (filename, last_modified, etag, content_length))
        self.conn.commit()

    async def get_last_cdn_resource(self, filename: str) -> Optional[Dict]:
        """获取 CDN 资源最近一次记录"""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT filename, last_modified, etag, content_length, timestamp
            FROM cdn_resources
            WHERE filename = ?
            ORDER BY timestamp DESC
            LIMIT 1
        """, (filename,))
        row = cursor.fetchone()
        return dict(row) if row else None

    # ── GitHub 监控方法 ──

    async def save_github_snapshot(self, repos: List[Dict]):
        """保存 GitHub 仓库快照"""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO github_snapshots (repos, repo_count)
            VALUES (?, ?)
        """, (json.dumps(repos, ensure_ascii=False), len(repos)))
        self.conn.commit()

    async def get_last_github_snapshot(self) -> Optional[Dict]:
        """获取最近的 GitHub 快照"""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT repos, repo_count, timestamp
            FROM github_snapshots
            ORDER BY timestamp DESC LIMIT 1
        """)
        row = cursor.fetchone()
        if not row:
            return None
        return {
            "repos": json.loads(row["repos"]),
            "count": row["repo_count"],
            "timestamp": row["timestamp"],
        }

    async def save_github_release(self, repo_name: str, tag_name: str,
                                  published_at: str, release_data: Dict):
        """保存 GitHub Release 记录"""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT OR IGNORE INTO github_releases (repo_name, tag_name, published_at, release_data)
            VALUES (?, ?, ?, ?)
        """, (repo_name, tag_name, published_at,
              json.dumps(release_data, ensure_ascii=False)))
        self.conn.commit()

    async def is_github_release_known(self, repo_name: str, tag_name: str) -> bool:
        """检查 Release 是否已知"""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT id FROM github_releases
            WHERE repo_name = ? AND tag_name = ?
        """, (repo_name, tag_name))
        return cursor.fetchone() is not None

    async def get_github_releases(self, limit: int = 20) -> List[Dict]:
        """获取 GitHub Release 历史"""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT repo_name, tag_name, published_at, release_data, timestamp
            FROM github_releases
            ORDER BY published_at DESC LIMIT ?
        """, (limit,))
        rows = []
        for row in cursor.fetchall():
            r = dict(row)
            try:
                r["release_data"] = json.loads(r["release_data"])
            except (json.JSONDecodeError, TypeError):
                pass
            rows.append(r)
        return rows

    async def cleanup_old_data(self, retention_days: int = 90):
        """清理旧数据

        Args:
            retention_days: 保留天数
        """
        logger.info(f"清理 {retention_days} 天之前的数据...")

        cursor = self.conn.cursor()
        cutoff_date = datetime.now() - timedelta(days=retention_days)

        # 清理各个表的旧数据
        tables = [
            "resource_hashes",
            "code_patterns",
            "model_configs",
            "api_endpoints",
            "test_results",
            "check_results",
            "commit_history",
            "feature_flags",
            "legal_docs",
            "cdn_resources",
            "github_snapshots",
        ]

        for table in tables:
            cursor.execute(f"""
                DELETE FROM {table}
                WHERE timestamp < ?
            """, (cutoff_date,))

            deleted = cursor.rowcount
            if deleted > 0:
                logger.info(f"  {table}: 删除 {deleted} 条记录")

        self.conn.commit()

    async def close(self):
        """关闭数据库连接"""
        if self.conn:
            self.conn.close()
            logger.debug("数据库连接已关闭")
