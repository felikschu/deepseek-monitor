#!/usr/bin/env python3
"""DeepSeek Monitor Web Dashboard Server"""

import asyncio
import json
import sqlite3
import sys
import webbrowser
from pathlib import Path
from datetime import datetime, timedelta

from aiohttp import web
from loguru import logger

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from utils.config import load_config

CONFIG = load_config(ROOT_DIR / "config.yaml")
DB_PATH = Path(CONFIG.get("storage", {}).get("sqlite_path", "data/deepseek_monitor.db"))
STATIC_DIR = Path(__file__).parent / "static"
PORT = 8765


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def row_to_dict(row):
    if row is None:
        return None
    return dict(row)


def rows_to_list(rows):
    return [dict(r) for r in rows]


# ── API Handlers ──


async def api_status(request):
    """当前状态概览"""
    conn = get_db()
    try:
        cur = conn.cursor()

        # 最近 commit
        cur.execute("SELECT * FROM commit_history ORDER BY timestamp DESC LIMIT 1")
        commit = row_to_dict(cur.fetchone())

        # 最近检查
        cur.execute("SELECT * FROM check_results ORDER BY timestamp DESC LIMIT 1")
        last_check = row_to_dict(cur.fetchone())

        # 统计
        cur.execute("SELECT COUNT(*) as cnt FROM changes_history")
        total_changes = cur.fetchone()["cnt"]
        cur.execute("SELECT COUNT(DISTINCT filename) as cnt FROM resource_hashes")
        tracked_resources = cur.fetchone()["cnt"]

        # 最近变化
        cur.execute("""
            SELECT change_type, COUNT(*) as cnt
            FROM changes_history
            WHERE timestamp >= datetime('now', '-7 days')
            GROUP BY change_type
        """)
        recent_by_type = rows_to_list(cur.fetchall())

        return web.json_response({
            "commit": commit,
            "last_check": last_check,
            "stats": {
                "total_changes": total_changes,
                "tracked_resources": tracked_resources,
                "recent_changes_7d": sum(r["cnt"] for r in recent_by_type),
                "recent_by_type": recent_by_type,
            },
            "db_path": str(DB_PATH),
            "server_time": datetime.now().isoformat(),
        })
    finally:
        conn.close()


async def api_timeline(request):
    """事件时间线（按天聚合）"""
    days = int(request.query.get("days", 30))
    conn = get_db()
    try:
        cur = conn.cursor()

        # 按天统计变化（北京时间 UTC+8）
        cur.execute("""
            SELECT DATE(timestamp, '+8 hours') as date, change_type, COUNT(*) as cnt
            FROM changes_history
            WHERE timestamp >= datetime('now', ?)
            GROUP BY DATE(timestamp, '+8 hours'), change_type
            ORDER BY date
        """, (f"-{days} days",))
        raw = rows_to_list(cur.fetchall())

        # 按天聚合
        by_date = {}
        for r in raw:
            d = r["date"]
            if d not in by_date:
                by_date[d] = {"date": d, "total": 0, "types": {}}
            by_date[d]["total"] += r["cnt"]
            by_date[d]["types"][r["change_type"]] = r["cnt"]

        return web.json_response({
            "days": days,
            "timeline": list(by_date.values()),
        })
    finally:
        conn.close()


async def api_changes(request):
    """变更历史"""
    days = int(request.query.get("days", 30))
    change_type = request.query.get("type")
    limit = int(request.query.get("limit", 100))

    conn = get_db()
    try:
        cur = conn.cursor()

        query = """
            SELECT id, change_type, change_data, timestamp
            FROM changes_history
            WHERE timestamp >= datetime('now', ?)
        """
        params = [f"-{days} days"]

        if change_type:
            query += " AND change_type = ?"
            params.append(change_type)

        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        cur.execute(query, params)
        rows = rows_to_list(cur.fetchall())

        # 解析 change_data JSON
        for r in rows:
            try:
                r["change_data"] = json.loads(r["change_data"])
            except (json.JSONDecodeError, TypeError):
                pass

        return web.json_response({"changes": rows, "count": len(rows)})
    finally:
        conn.close()


async def api_commits(request):
    """commit 历史"""
    limit = int(request.query.get("limit", 20))
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT * FROM commit_history ORDER BY timestamp DESC LIMIT ?
        """, (limit,))
        return web.json_response({"commits": rows_to_list(cur.fetchall())})
    finally:
        conn.close()


async def api_flags(request):
    """Feature flags 历史"""
    limit = int(request.query.get("limit", 20))
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT * FROM feature_flags ORDER BY timestamp DESC LIMIT ?
        """, (limit,))
        rows = rows_to_list(cur.fetchall())

        for r in rows:
            try:
                r["flags"] = json.loads(r["flags"])
            except (json.JSONDecodeError, TypeError):
                pass

        return web.json_response({"snapshots": rows})
    finally:
        conn.close()


async def api_endpoints(request):
    """API 端点历史"""
    limit = int(request.query.get("limit", 10))
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT * FROM api_endpoints ORDER BY timestamp DESC LIMIT ?
        """, (limit,))
        rows = rows_to_list(cur.fetchall())

        for r in rows:
            try:
                r["endpoints"] = json.loads(r["endpoints"])
            except (json.JSONDecodeError, TypeError):
                pass

        return web.json_response({"snapshots": rows})
    finally:
        conn.close()


async def api_resources(request):
    """资源 hash 历史"""
    limit = int(request.query.get("limit", 50))
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT * FROM resource_hashes ORDER BY timestamp DESC LIMIT ?
        """, (limit,))
        return web.json_response({"resources": rows_to_list(cur.fetchall())})
    finally:
        conn.close()


async def api_legal(request):
    """法律文档更新记录"""
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM legal_docs ORDER BY timestamp DESC")
        return web.json_response({"docs": rows_to_list(cur.fetchall())})
    finally:
        conn.close()


async def api_cdn(request):
    """CDN 资源追踪"""
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM cdn_resources ORDER BY timestamp DESC")
        return web.json_response({"resources": rows_to_list(cur.fetchall())})
    finally:
        conn.close()


async def api_check(request):
    """触发一次前端检查"""
    try:
        from core.frontend_monitor import FrontendMonitor
        from core.storage import StorageManager

        storage = StorageManager(CONFIG)
        await storage.initialize()
        monitor = FrontendMonitor(CONFIG, storage)
        results = await monitor.check()

        await storage.save_check_results(results)
        await monitor.cleanup()
        await storage.close()

        changes = results.get("changes", [])
        commit_info = results.get("commit", {})
        return web.json_response({
            "status": "ok",
            "changes_detected": len(changes),
            "commit": commit_info,
            "timestamp": results.get("timestamp"),
        })
    except Exception as e:
        logger.error(f"检查失败: {e}")
        return web.json_response({"status": "error", "message": str(e)}, status=500)


async def index(request):
    """返回 dashboard HTML"""
    return web.FileResponse(STATIC_DIR / "index.html")


async def export_report(request):
    """导出 JSON 报告"""
    days = int(request.query.get("days", 7))
    conn = get_db()
    try:
        cur = conn.cursor()

        report = {
            "generated_at": datetime.now().isoformat(),
            "period_days": days,
        }

        # commits
        cur.execute("""
            SELECT * FROM commit_history
            WHERE timestamp >= datetime('now', ?) ORDER BY timestamp
        """, (f"-{days} days",))
        report["commits"] = rows_to_list(cur.fetchall())

        # changes
        cur.execute("""
            SELECT * FROM changes_history
            WHERE timestamp >= datetime('now', ?) ORDER BY timestamp
        """, (f"-{days} days",))
        report["changes"] = rows_to_list(cur.fetchall())

        # flags
        cur.execute("SELECT * FROM feature_flags ORDER BY timestamp DESC LIMIT 1")
        flags_row = row_to_dict(cur.fetchone())
        if flags_row:
            try:
                flags_row["flags"] = json.loads(flags_row["flags"])
            except (json.JSONDecodeError, TypeError):
                pass
        report["current_flags"] = flags_row

        # endpoints
        cur.execute("SELECT * FROM api_endpoints ORDER BY timestamp DESC LIMIT 1")
        ep_row = row_to_dict(cur.fetchone())
        if ep_row:
            try:
                ep_row["endpoints"] = json.loads(ep_row["endpoints"])
            except (json.JSONDecodeError, TypeError):
                pass
        report["current_endpoints"] = ep_row

        # legal docs
        cur.execute("SELECT * FROM legal_docs ORDER BY timestamp DESC")
        report["legal_docs"] = rows_to_list(cur.fetchall())

        resp = web.Response(
            text=json.dumps(report, ensure_ascii=False, indent=2, default=str),
            content_type="application/json",
            headers={"Content-Disposition": f"attachment; filename=report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"},
        )
        return resp
    finally:
        conn.close()


def create_app():
    app = web.Application()

    # Routes
    app.router.add_get("/", index)
    app.router.add_get("/api/status", api_status)
    app.router.add_get("/api/timeline", api_timeline)
    app.router.add_get("/api/changes", api_changes)
    app.router.add_get("/api/commits", api_commits)
    app.router.add_get("/api/flags", api_flags)
    app.router.add_get("/api/endpoints", api_endpoints)
    app.router.add_get("/api/resources", api_resources)
    app.router.add_get("/api/legal", api_legal)
    app.router.add_get("/api/cdn", api_cdn)
    app.router.add_post("/api/check", api_check)
    app.router.add_get("/api/export", export_report)

    # Static files
    app.router.add_static("/static", STATIC_DIR)

    return app


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="DeepSeek Monitor Dashboard")
    parser.add_argument("--port", "-p", type=int, default=PORT)
    parser.add_argument("--no-open", action="store_true", help="Don't open browser")
    args = parser.parse_args()

    logger.info(f"Starting DeepSeek Monitor Dashboard on http://localhost:{args.port}")

    if not args.no_open:
        webbrowser.open(f"http://localhost:{args.port}")

    app = create_app()
    web.run_app(app, host="0.0.0.0", port=args.port, print=None)
