#!/usr/bin/env python3
"""DeepSeek Monitor Web Dashboard Server"""

import asyncio
import json
import sqlite3
import sys
import webbrowser
from pathlib import Path
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

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


def _parse_json_blob(value):
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return {}


def _dedupe_keep_order(values):
    seen = set()
    output = []
    for value in values or []:
        if value in (None, "", [], {}):
            continue
        if isinstance(value, str):
            key = value.strip()
            if not key:
                continue
        else:
            key = json.dumps(value, ensure_ascii=False, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        output.append(value)
    return output


def _merge_signal_lists(target, source, keys):
    for key in keys:
        target[key] = _dedupe_keep_order((target.get(key) or []) + (source.get(key) or []))
    return target


def build_deepseek_web_summary(commit, bundle_item, surfaces, highlights):
    bundle_insights = (bundle_item or {}).get("insights") or {}
    merged_surface_signals = {}
    for item in surfaces:
        merged_surface_signals = _merge_signal_lists(
            merged_surface_signals,
            item.get("signals") or {},
            [
                "models",
                "coding_signals",
                "prices",
                "pricing_lines",
                "headline_lines",
                "hidden_capabilities",
                "route_patterns",
                "api_families",
                "pricing_signals",
                "coder_signals",
                "vision_signals",
                "agent_signals",
            ],
        )

    public_signals = {
        "models": merged_surface_signals.get("models", [])[:12],
        "coding_signals": merged_surface_signals.get("coding_signals", [])[:10],
        "prices": merged_surface_signals.get("prices", [])[:10],
        "pricing_lines": merged_surface_signals.get("pricing_lines", [])[:6],
        "headline_lines": merged_surface_signals.get("headline_lines", [])[:6],
    }
    source_signals = {
        "hidden_capabilities": bundle_insights.get("hidden_capabilities", [])[:10],
        "route_patterns": bundle_insights.get("route_patterns", [])[:10],
        "api_families": bundle_insights.get("api_families", [])[:12],
        "coder_signals": bundle_insights.get("coder_signals", [])[:4],
        "vision_signals": bundle_insights.get("vision_signals", [])[:4],
        "agent_signals": bundle_insights.get("agent_signals", [])[:4],
        "pricing_signals": _dedupe_keep_order(
            (bundle_insights.get("pricing_signals", []) or []) + (merged_surface_signals.get("pricing_signals", []) or [])
        )[:6],
    }

    narrative = []
    commit_time = commit.get("commit_datetime") if isinstance(commit, dict) else None
    if commit_time:
        narrative.append(f"当前 chat 主 bundle 对应 commit 时间为 {commit_time}")
    if source_signals["hidden_capabilities"]:
        narrative.extend(source_signals["hidden_capabilities"][:4])
    if public_signals["headline_lines"]:
        narrative.append(f"官网公开强调: {public_signals['headline_lines'][0]}")
    if public_signals["pricing_lines"]:
        narrative.append(f"公开定价线索: {public_signals['pricing_lines'][0]}")

    recent = []
    for item in highlights[:6]:
        recent.append({
            "change_type": item.get("change_type"),
            "summary": item.get("summary"),
            "event_time": item.get("event_time"),
        })

    return {
        "commit": commit or {},
        "bundle": {
            "filename": (bundle_item or {}).get("filename"),
            "timestamp": (bundle_item or {}).get("timestamp"),
            "insights": bundle_insights,
        },
        "surfaces": surfaces,
        "public_signals": public_signals,
        "source_signals": source_signals,
        "narrative": narrative[:8],
        "recent_highlights": recent,
        "generated_at": datetime.now().isoformat(),
    }


def parse_event_time(change_row):
    """优先使用变化自身携带的 source_time，否则回退到入库时间。"""
    def normalize(dt):
        if dt is None:
            return None
        if dt.tzinfo is not None:
            return dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt

    change_data = change_row.get("change_data")
    if isinstance(change_data, str):
        try:
            change_data = json.loads(change_data)
        except json.JSONDecodeError:
            change_data = {}
    elif change_data is None:
        change_data = {}

    source_time = change_data.get("source_time")
    if source_time:
        try:
            if "GMT" in source_time or "," in source_time:
                return normalize(parsedate_to_datetime(source_time))
            normalized = source_time.replace("Z", "+00:00")
            return normalize(datetime.fromisoformat(normalized))
        except Exception:
            pass

    raw_ts = change_row.get("timestamp")
    if raw_ts:
        try:
            return normalize(datetime.fromisoformat(raw_ts.replace("Z", "+00:00")))
        except Exception:
            pass
    return None


def parse_incident_time(incident):
    if not incident:
        return None
    for key in ["created_at", "published", "updated", "resolved_at"]:
        value = incident.get(key)
        if not value:
            continue
        try:
            if "GMT" in value or "," in value:
                dt = parsedate_to_datetime(value)
            else:
                dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if dt.tzinfo is not None:
                return dt.astimezone(timezone.utc).replace(tzinfo=None)
            return dt
        except Exception:
            continue
    return None


def is_high_signal_change(change_type, change_data):
    low_signal = {"cdn_update"}
    if change_type in low_signal:
        return False
    if change_type == "model_configs_change":
        old_payload = change_data.get("old") or {}
        new_payload = change_data.get("new") or {}

        def has_real_model_configs(payload):
            if not isinstance(payload, dict):
                return False
            biz_data = payload.get("biz_data")
            if isinstance(biz_data, dict) and biz_data.get("model_configs"):
                return True
            if payload.get("model_configs"):
                return True
            return False

        return has_real_model_configs(old_payload) or has_real_model_configs(new_payload)
    if change_type == "resource_change":
        return True
    if change_type == "bundle_insights_change":
        return change_data.get("bundle_role") != "vendor_runtime"
    if change_type == "api_endpoints_change":
        new_endpoints = change_data.get("new_endpoints") or []
        removed_endpoints = change_data.get("removed_endpoints") or []
        if not new_endpoints:
            return False
        if len(removed_endpoints) > max(10, len(new_endpoints) * 3):
            return False
        return True
    if change_type in {
        "commit_change",
        "competitor_model_change",
        "feature_flags_change",
        "huggingface_model_change",
        "legal_doc_update",
        "surface_change",
        "new_repo",
        "repo_push",
        "new_release",
        "stars_change",
        "new_incident",
        "status_change",
    }:
        return True
    return False


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
        cur.execute("SELECT change_type, change_data, timestamp FROM changes_history ORDER BY timestamp DESC")
        raw_changes = rows_to_list(cur.fetchall())
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=7)
        recent_by_type_map = {}
        for row in raw_changes:
            event_time = parse_event_time(row)
            if not event_time or event_time < cutoff:
                continue
            recent_by_type_map[row["change_type"]] = recent_by_type_map.get(row["change_type"], 0) + 1
        recent_by_type = [
            {"change_type": change_type, "cnt": cnt}
            for change_type, cnt in sorted(recent_by_type_map.items())
        ]

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
        cur.execute("""
            SELECT change_type, change_data, timestamp
            FROM changes_history
            ORDER BY timestamp DESC
        """)
        raw_rows = rows_to_list(cur.fetchall())
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
        raw = []
        for row in raw_rows:
            event_time = parse_event_time(row)
            if not event_time or event_time < cutoff:
                continue
            row["event_time"] = event_time
            raw.append(row)

        # 按天聚合
        by_date = {}
        for r in raw:
            d = (r["event_time"] + timedelta(hours=8)).date().isoformat()
            if d not in by_date:
                by_date[d] = {"date": d, "total": 0, "types": {}}
            by_date[d]["total"] += 1
            by_date[d]["types"][r["change_type"]] = by_date[d]["types"].get(r["change_type"], 0) + 1

        return web.json_response({
            "days": days,
            "timeline": [by_date[key] for key in sorted(by_date.keys())],
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


async def api_surfaces(request):
    """官方页面/文档快照"""
    limit = int(request.query.get("limit", 50))
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT s1.*
            FROM surface_snapshots s1
            JOIN (
                SELECT url, MAX(id) AS max_id
                FROM surface_snapshots
                GROUP BY url
            ) s2 ON s1.id = s2.max_id
            ORDER BY s1.timestamp DESC
            LIMIT ?
        """, (limit,))
        rows = rows_to_list(cur.fetchall())
        for row in rows:
            try:
                row["signals"] = json.loads(row.pop("signals_json") or "{}")
            except (json.JSONDecodeError, TypeError):
                row["signals"] = {}
            row.pop("normalized_text", None)
        return web.json_response({"surfaces": rows})
    finally:
        conn.close()


async def api_bundles(request):
    """关键 bundle 的最新语义分析结果"""
    limit = int(request.query.get("limit", 20))
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT b1.filename, b1.bundle_type, b1.insights, b1.timestamp
            FROM bundle_insights b1
            JOIN (
                SELECT filename, MAX(id) AS max_id
                FROM bundle_insights
                GROUP BY filename
            ) b2 ON b1.id = b2.max_id
            ORDER BY b1.timestamp DESC
            LIMIT ?
        """, (limit,))
        rows = []
        for row in cur.fetchall():
            item = dict(row)
            try:
                item["insights"] = json.loads(item["insights"])
            except (json.JSONDecodeError, TypeError):
                item["insights"] = {}
            rows.append(item)
        return web.json_response({"bundles": rows})
    finally:
        conn.close()


async def api_deepseek_web(request):
    """DeepSeek 网页态势摘要：公开官网信号 + 源码隐藏能力"""
    conn = get_db()
    try:
        cur = conn.cursor()

        cur.execute("SELECT * FROM commit_history ORDER BY timestamp DESC LIMIT 1")
        commit = row_to_dict(cur.fetchone()) or {}

        cur.execute("""
            SELECT b1.filename, b1.bundle_type, b1.insights, b1.timestamp
            FROM bundle_insights b1
            JOIN (
                SELECT filename, MAX(id) AS max_id
                FROM bundle_insights
                WHERE bundle_type = 'application_bundle'
                GROUP BY filename
            ) b2 ON b1.id = b2.max_id
            ORDER BY b1.timestamp DESC
            LIMIT 1
        """)
        bundle_row = row_to_dict(cur.fetchone()) or {}
        if bundle_row:
            bundle_row["insights"] = _parse_json_blob(bundle_row.get("insights"))

        cur.execute("""
            SELECT s1.*
            FROM surface_snapshots s1
            JOIN (
                SELECT url, MAX(id) AS max_id
                FROM surface_snapshots
                GROUP BY url
            ) s2 ON s1.id = s2.max_id
            ORDER BY s1.timestamp DESC
            LIMIT 12
        """)
        surfaces = []
        for row in rows_to_list(cur.fetchall()):
            row["signals"] = _parse_json_blob(row.pop("signals_json", None))
            row.pop("normalized_text", None)
            surfaces.append(row)

        cur.execute("""
            SELECT id, change_type, change_data, timestamp
            FROM changes_history
            WHERE change_type IN ('commit_change', 'surface_change', 'bundle_insights_change')
            ORDER BY timestamp DESC
            LIMIT 40
        """)
        raw_highlights = rows_to_list(cur.fetchall())
        highlights = []
        for row in raw_highlights:
            row["change_data"] = _parse_json_blob(row.get("change_data"))
            if not is_high_signal_change(row["change_type"], row["change_data"]):
                continue
            event_time = parse_event_time(row)
            change_data = row["change_data"]
            highlights.append({
                "change_type": row["change_type"],
                "summary": change_data.get("summary") or change_data.get("filename") or row["change_type"],
                "event_time": event_time.isoformat() if event_time else row["timestamp"],
            })

        return web.json_response(build_deepseek_web_summary(commit, bundle_row, surfaces, highlights))
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

        # 官方页面/文档检查
        official_changes = []
        try:
            from core.official_monitor import OfficialMonitor
            official = OfficialMonitor(CONFIG, storage)
            official_results = await official.check()
            official_changes = official_results.get("changes", [])
            for change in official_changes:
                await storage.save_change(change.get("type", "surface_change"), change)
            await official.cleanup()
        except Exception as e:
            logger.warning(f"官方页面检查失败（非致命）: {e}")

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

        competitor_changes = []
        try:
            from core.competitor_monitor import CompetitorMonitor
            cm = CompetitorMonitor(CONFIG, storage)
            competitor_results = await cm.check()
            competitor_changes = competitor_results.get("changes", [])
            for change in competitor_changes:
                await storage.save_change(change.get("type", "competitor_model_change"), change)
            await cm.cleanup()
        except Exception as e:
            logger.warning(f"竞品侦察失败（非致命）: {e}")

        huggingface_changes = []
        try:
            from core.huggingface_monitor import HuggingFaceMonitor
            hf = HuggingFaceMonitor(CONFIG, storage)
            huggingface_results = await hf.check()
            huggingface_changes = huggingface_results.get("changes", [])
            for change in huggingface_changes:
                await storage.save_change(change.get("type", "huggingface_model_change"), change)
            await hf.cleanup()
        except Exception as e:
            logger.warning(f"Hugging Face 检查失败（非致命）: {e}")

        await storage.close()

        changes = results.get("changes", [])
        total = (
            len(changes)
            + len(official_changes)
            + len(gh_changes)
            + len(status_changes)
            + len(competitor_changes)
            + len(huggingface_changes)
        )
        commit_info = results.get("commit", {})
        return web.json_response({
            "ok": True,
            "status": "ok",
            "changes_detected": total,
            "frontend_changes": len(changes),
            "official_changes": len(official_changes),
            "github_changes": len(gh_changes),
            "status_changes": len(status_changes),
            "competitor_changes": len(competitor_changes),
            "huggingface_changes": len(huggingface_changes),
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
        incidents.sort(key=lambda item: parse_incident_time(item) or datetime.min, reverse=True)

        return web.json_response({
            "current": {
                "components": components,
                "timestamp": row["timestamp"],
            },
            "incidents": incidents,
        })
    finally:
        conn.close()


async def api_highlights(request):
    """最近高信号更新摘要"""
    days = int(request.query.get("days", 7))
    limit = int(request.query.get("limit", 12))
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT id, change_type, change_data, timestamp
            FROM changes_history
            ORDER BY timestamp DESC
        """)
        rows = rows_to_list(cur.fetchall())
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
        highlights = []
        seen = set()

        for row in rows:
            try:
                row["change_data"] = json.loads(row["change_data"])
            except (json.JSONDecodeError, TypeError):
                row["change_data"] = {}
            event_time = parse_event_time(row)
            if not event_time or event_time < cutoff:
                continue
            if not is_high_signal_change(row["change_type"], row["change_data"]):
                continue

            change_data = row["change_data"]
            key = (
                row["change_type"],
                change_data.get("filename"),
                change_data.get("title"),
                change_data.get("surface_name"),
                change_data.get("org_name"),
                change_data.get("repo_name"),
                change_data.get("incident_id"),
                change_data.get("doc_name"),
            )
            if key in seen:
                continue
            seen.add(key)

            summary = (
                change_data.get("summary")
                or change_data.get("title")
                or change_data.get("feature_name")
                or change_data.get("filename")
                or change_data.get("surface_name")
                or change_data.get("repo_name")
                or row["change_type"]
            )
            highlights.append({
                "change_type": row["change_type"],
                "summary": summary,
                "event_time": event_time.isoformat(),
                "observed_at": change_data.get("observed_at", row["timestamp"]),
                "change_data": change_data,
            })
            if len(highlights) >= limit:
                break

        return web.json_response({"highlights": highlights, "count": len(highlights), "days": days})
    finally:
        conn.close()


async def api_competitors(request):
    """竞品官网侦察快照"""
    limit = int(request.query.get("limit", 20))
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT c1.*
            FROM competitor_snapshots c1
            JOIN (
                SELECT url, MAX(id) AS max_id
                FROM competitor_snapshots
                GROUP BY url
            ) c2 ON c1.id = c2.max_id
            ORDER BY c1.timestamp DESC
            LIMIT ?
        """, (limit,))
        rows = rows_to_list(cur.fetchall())
        for row in rows:
            try:
                row["signals"] = json.loads(row.pop("signals_json") or "{}")
            except (json.JSONDecodeError, TypeError):
                row["signals"] = {}
        return web.json_response({"competitors": rows})
    finally:
        conn.close()


async def api_huggingface(request):
    """Hugging Face 官方组织快照"""
    limit = int(request.query.get("limit", 20))
    conn = get_db()
    try:
        cur = conn.cursor()
        try:
            cur.execute("""
                SELECT h1.*
                FROM huggingface_snapshots h1
                JOIN (
                    SELECT org_name, MAX(id) AS max_id
                    FROM huggingface_snapshots
                    GROUP BY org_name
                ) h2 ON h1.id = h2.max_id
                ORDER BY h1.timestamp DESC
                LIMIT ?
            """, (limit,))
        except sqlite3.OperationalError:
            return web.json_response({"organizations": []})
        rows = rows_to_list(cur.fetchall())
        for row in rows:
            row["org"] = _parse_json_blob(row.pop("overview_json", None))
            row["models"] = _parse_json_blob(row.pop("models_json", None)) or []
            row["signals"] = _parse_json_blob(row.pop("signals_json", None))
        return web.json_response({"organizations": rows})
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

        # official surfaces
        cur.execute("""
            SELECT s1.*
            FROM surface_snapshots s1
            JOIN (
                SELECT url, MAX(id) AS max_id
                FROM surface_snapshots
                GROUP BY url
            ) s2 ON s1.id = s2.max_id
            ORDER BY s1.timestamp DESC
        """)
        surfaces = rows_to_list(cur.fetchall())
        for row in surfaces:
            try:
                row["signals"] = json.loads(row.pop("signals_json") or "{}")
            except (json.JSONDecodeError, TypeError):
                row["signals"] = {}
        report["official_surfaces"] = surfaces

        cur.execute("""
            SELECT h1.*
            FROM huggingface_snapshots h1
            JOIN (
                SELECT org_name, MAX(id) AS max_id
                FROM huggingface_snapshots
                GROUP BY org_name
            ) h2 ON h1.id = h2.max_id
            ORDER BY h1.timestamp DESC
        """)
        huggingface_rows = rows_to_list(cur.fetchall())
        for row in huggingface_rows:
            row["org"] = _parse_json_blob(row.pop("overview_json", None))
            row["models"] = _parse_json_blob(row.pop("models_json", None)) or []
            row["signals"] = _parse_json_blob(row.pop("signals_json", None))
        report["huggingface_orgs"] = huggingface_rows

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

        # 官方页面/文档检查
        try:
            from core.official_monitor import OfficialMonitor
            official = OfficialMonitor(CONFIG, storage)
            official_results = await official.check()
            for change in official_results.get("changes", []):
                await storage.save_change(change.get("type", "surface_change"), change)
            await official.cleanup()
        except Exception as e:
            logger.warning(f"官方页面检查失败（非致命）: {e}")

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

        try:
            from core.competitor_monitor import CompetitorMonitor
            cm = CompetitorMonitor(CONFIG, storage)
            competitor_results = await cm.check()
            for change in competitor_results.get("changes", []):
                await storage.save_change(change.get("type", "competitor_model_change"), change)
            await cm.cleanup()
        except Exception as e:
            logger.warning(f"竞品侦察失败（非致命）: {e}")

        try:
            from core.huggingface_monitor import HuggingFaceMonitor
            hf = HuggingFaceMonitor(CONFIG, storage)
            huggingface_results = await hf.check()
            for change in huggingface_results.get("changes", []):
                await storage.save_change(change.get("type", "huggingface_model_change"), change)
            await hf.cleanup()
        except Exception as e:
            logger.warning(f"Hugging Face 检查失败（非致命）: {e}")

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
    app.router.add_get("/api/surfaces", api_surfaces)
    app.router.add_get("/api/bundles", api_bundles)
    app.router.add_get("/api/deepseek_web", api_deepseek_web)
    app.router.add_post("/api/check", api_check)
    app.router.add_get("/api/export", export_report)
    app.router.add_get("/api/github/repos", api_github_repos)
    app.router.add_get("/api/github/releases", api_github_releases)
    app.router.add_get("/api/status_page", api_status_page)
    app.router.add_get("/api/highlights", api_highlights)
    app.router.add_get("/api/competitors", api_competitors)
    app.router.add_get("/api/huggingface", api_huggingface)
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
