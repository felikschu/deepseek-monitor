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

        # 同时执行 GitHub 检查
        gh_changes = []
        try:
            from core.github_monitor import GitHubMonitor
            gh = GitHubMonitor(CONFIG, storage)
            gh_results = await gh.check()
            gh_changes = gh_results.get("changes", [])
            # 保存 GitHub 变化到 changes_history
            for change in gh_changes:
                await storage.save_change(
                    change.get("type", "github"),
                    change
                )
            await gh.cleanup()
        except Exception as e:
            logger.warning(f"GitHub 检查失败（非致命）: {e}")

        # 同时执行 Status Page 检查
        status_changes = []
        try:
            from core.status_monitor import StatusMonitor
            sm = StatusMonitor(CONFIG, storage)
            status_results = await sm.check()
            status_changes = status_results.get("changes", [])
            # 保存 Status 变化到 changes_history
            for change in status_changes:
                await storage.save_change(
                    change.get("type", "status"),
                    change
                )
            # 保存事件
            for inc in status_results.get("incidents", []):
                await storage.save_status_incident(inc)
            await sm.cleanup()
        except Exception as e:
            logger.warning(f"Status 检查失败（非致命）: {e}")

        await storage.close()

        changes = results.get("changes", [])
        total = len(changes) + len(gh_changes) + len(status_changes)
        commit_info = results.get("commit", {})
        return web.json_response({
            "status": "ok",
            "changes_detected": total,
            "frontend_changes": len(changes),
            "github_changes": len(gh_changes),
            "status_changes": len(status_changes),
            "commit": commit_info,
            "timestamp": results.get("timestamp"),
        })
    except Exception as e:
        logger.error(f"检查失败: {e}")
        return web.json_response({"status": "error", "message": str(e)}, status=500)


async def api_github_repos(request):
    """GitHub 仓库快照"""
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT repos, repo_count, timestamp
            FROM github_snapshots
            ORDER BY timestamp DESC LIMIT 1
        """)
        row = cur.fetchone()
        if not row:
            return web.json_response({"repos": [], "count": 0})

        repos = json.loads(row["repos"])
        # 按星数排序
        repos.sort(key=lambda r: r.get("stars", 0), reverse=True)

        return web.json_response({
            "repos": repos,
            "count": row["repo_count"],
            "timestamp": row["timestamp"],
        })
    finally:
        conn.close()


async def api_github_releases(request):
    """GitHub Release 历史"""
    limit = int(request.query.get("limit", 20))
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT repo_name, tag_name, published_at, release_data, timestamp
            FROM github_releases
            ORDER BY published_at DESC LIMIT ?
        """, (limit,))
        rows = rows_to_list(cur.fetchall())
        for r in rows:
            try:
                r["release_data"] = json.loads(r["release_data"])
            except (json.JSONDecodeError, TypeError):
                pass
        return web.json_response({"releases": rows})
    finally:
        conn.close()


async def api_status_page(request):
    """Status Page 状态"""
    conn = get_db()
    try:
        cur = conn.cursor()
        # 获取最新快照
        cur.execute("""
            SELECT components, incidents, timestamp
            FROM status_snapshots
            ORDER BY timestamp DESC LIMIT 1
        """)
        row = cur.fetchone()

        if not row:
            return web.json_response({
                "current": None,
                "incidents": [],
            })

        # 解析数据
        components = json.loads(row["components"]) if row["components"] else []
        incidents = json.loads(row["incidents"]) if row["incidents"] else []

        return web.json_response({
            "current": {
                "components": components,
                "timestamp": row["timestamp"],
            },
            "incidents": incidents,
        })
    finally:
        conn.close()


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


async def _auto_check_task(app):
    """后台自动检查任务"""
    interval = CONFIG.get("monitoring", {}).get("check_interval_hours", 3)
    interval_sec = interval * 3600
    logger.info(f"自动检查已启动，间隔 {interval} 小时")

    # 启动后延迟30秒再执行首次检查，等服务器就绪
    await asyncio.sleep(30)
    while True:
        try:
            logger.info("执行定时自动检查...")
            await _run_check()
            logger.info("定时自动检查完成")
        except Exception as e:
            logger.error(f"自动检查失败: {e}")
        await asyncio.sleep(interval_sec)


async def _run_check():
    """执行一次检查（复用 api_check 逻辑）"""
    try:
        from core.frontend_monitor import FrontendMonitor
        from core.storage import StorageManager

        storage = StorageManager(CONFIG)
        await storage.initialize()
        monitor = FrontendMonitor(CONFIG, storage)
        results = await monitor.check()
        await storage.save_check_results(results)
        await monitor.cleanup()

        # GitHub 检查
        try:
            from core.github_monitor import GitHubMonitor
            gh = GitHubMonitor(CONFIG, storage)
            gh_results = await gh.check()
            for change in gh_results.get("changes", []):
                await storage.save_change(
                    change.get("type", "github"),
                    change
                )
            await gh.cleanup()
        except Exception as e:
            logger.warning(f"GitHub 检查失败（非致命）: {e}")

        # Status Page 检查
        try:
            from core.status_monitor import StatusMonitor
            sm = StatusMonitor(CONFIG, storage)
            status_results = await sm.check()
            for change in status_results.get("changes", []):
                await storage.save_change(
                    change.get("type", "status"),
                    change
                )
            for inc in status_results.get("incidents", []):
                await storage.save_status_incident(inc)
            await sm.cleanup()
        except Exception as e:
            logger.warning(f"Status 检查失败（非致命）: {e}")

        await storage.close()
    except Exception as e:
        logger.error(f"自动检查失败: {e}")


# 全局变量存储当前检查间隔（分钟）
_current_interval_minutes = CONFIG.get("monitoring", {}).get("check_interval_hours", 3) * 60


async def on_startup(app):
    """服务器启动时开启后台检查"""
    app["auto_check"] = asyncio.create_task(_auto_check_task(app))


async def _auto_check_task(app):
    """后台自动检查任务"""
    global _current_interval_minutes
    logger.info(f"自动检查已启动，间隔 {_current_interval_minutes} 分钟")

    # 启动后延迟30秒再执行首次检查，等服务器就绪
    await asyncio.sleep(30)
    while True:
        try:
            logger.info("执行定时自动检查...")
            await _run_check()
            logger.info("定时自动检查完成")
        except Exception as e:
            logger.error(f"自动检查失败: {e}")
        
        # 使用当前的间隔设置
        await asyncio.sleep(_current_interval_minutes * 60)


async def on_cleanup(app):
    """服务器关闭时取消后台任务"""
    task = app.get("auto_check")
    if task:
        task.cancel()


async def api_settings(request):
    """获取当前设置"""
    global _current_interval_minutes
    return web.json_response({
        "check_interval_minutes": _current_interval_minutes,
        "check_interval_options": [
            {"value": 3, "label": "3分钟"},
            {"value": 10, "label": "10分钟"},
            {"value": 60, "label": "1小时"},
            {"value": 180, "label": "3小时"},
        ],
    })


async def api_update_settings(request):
    """更新设置"""
    global _current_interval_minutes
    try:
        data = await request.json()
        new_interval = data.get("check_interval_minutes")
        
        # 验证允许的选项
        allowed_options = [3, 10, 60, 180]
        if new_interval not in allowed_options:
            return web.json_response({
                "status": "error",
                "message": f"Invalid interval. Allowed: {allowed_options}"
            }, status=400)
        
        _current_interval_minutes = new_interval
        logger.info(f"检查间隔已更新为 {new_interval} 分钟")
        
        return web.json_response({
            "status": "ok",
            "check_interval_minutes": _current_interval_minutes,
        })
    except Exception as e:
        return web.json_response({
            "status": "error",
            "message": str(e)
        }, status=500)


def create_app():
    app = web.Application()

    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)

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
    app.router.add_get("/api/github/repos", api_github_repos)
    app.router.add_get("/api/github/releases", api_github_releases)
    app.router.add_get("/api/status_page", api_status_page)
    app.router.add_get("/api/settings", api_settings)
    app.router.add_post("/api/settings", api_update_settings)

    # Static files
    app.router.add_static("/static", STATIC_DIR)

    return app


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="DeepSeek Monitor Dashboard")
    parser.add_argument("--port", "-p", type=int, default=PORT)
    parser.add_argument("--no-open", action="store_true", help="Don't open browser")
    parser.add_argument("--no-auto", action="store_true", help="Disable auto-check background task")
    args = parser.parse_args()

    logger.info(f"Starting DeepSeek Monitor Dashboard on http://localhost:{args.port}")

    if not args.no_open:
        webbrowser.open(f"http://localhost:{args.port}")

    app = create_app()

    if args.no_auto:
        # 取消自动检查
        app.on_startup.clear()

    web.run_app(app, host="0.0.0.0", port=args.port, print=None)
