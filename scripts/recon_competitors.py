#!/usr/bin/env python3
"""
竞品站点侦察脚本

用途：
1. 复用 monitor 的页面 + 同源脚本探针能力
2. 汇总新模型、价格、套餐、商业化入口
3. 输出一份可读的 markdown 侦察报告
"""

import argparse
import asyncio
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from core.competitor_monitor import CompetitorMonitor
from core.storage import StorageManager
from utils.config import load_config


def _pick(items: List[str], limit: int = 8) -> List[str]:
    return [item for item in items if item][:limit]


def _render_surface(surface: Dict) -> str:
    signals = surface.get("signals", {})
    lines = [
        f"## {surface.get('name')} ({surface.get('vendor')})",
        "",
        f"- URL: {surface.get('url')}",
        f"- Final URL: {surface.get('final_url') or surface.get('url')}",
        f"- Title: {surface.get('title') or '---'}",
        f"- Observed At: {surface.get('observed_at')}",
    ]

    for label, key, limit in [
        ("Models", "models", 12),
        ("Commercial Actions", "commercial_actions", 10),
        ("Headlines", "headline_lines", 8),
        ("Offerings", "offerings", 12),
        ("Prices", "prices", 12),
        ("Pricing Paths", "pricing_paths", 8),
        ("Discovered Links", "discovered_links", 8),
        ("Plan Signals", "plan_signals", 4),
        ("Pricing Lines", "pricing_lines", 4),
        ("Versions", "resource_versions", 8),
        ("Article Dates", "article_dates", 8),
        ("Dates", "dates", 8),
    ]:
        values = _pick(signals.get(key, []), limit)
        if values:
            lines.append(f"- {label}: " + " | ".join(values))

    probe = signals.get("script_probe") or {}
    if probe.get("probed_urls"):
        lines.append("- Script Probe: " + " | ".join(_pick(probe["probed_urls"], 4)))

    lines.append("")
    return "\n".join(lines)


def _render_changes(changes: List[Dict]) -> str:
    if not changes:
        return "## Changes\n\n- No new changes detected in this run.\n"

    lines = ["## Changes", ""]
    for change in changes:
        lines.append(f"- {change.get('summary')}")
        for key, label in [
            ("added_models", "New Models"),
            ("added_actions", "New Commercial Actions"),
            ("added_headlines", "New Headlines"),
            ("added_offerings", "New Offerings"),
            ("added_prices", "New Prices"),
            ("added_pricing_paths", "New Pricing Paths"),
            ("added_links", "New Interesting Links"),
            ("added_plan_signals", "New Plan Signals"),
            ("added_dates", "New Dates"),
            ("added_news", "New News Slugs"),
        ]:
            values = _pick(change.get(key, []), 8)
            if values:
                lines.append(f"  {label}: " + " | ".join(values))
        lines.append(f"  Source Time: {change.get('source_time') or '---'}")
    lines.append("")
    return "\n".join(lines)


async def main():
    parser = argparse.ArgumentParser(description="Recon competitor model and commercial signals")
    parser.add_argument("--vendor", choices=["zhipu", "minimax"], help="Only inspect one vendor")
    parser.add_argument("--output", help="Optional output markdown path")
    args = parser.parse_args()

    config = load_config(ROOT_DIR / "config.yaml")
    if args.vendor:
        pages = config.get("competitor_surfaces", {}).get("pages", [])
        config["competitor_surfaces"]["pages"] = [page for page in pages if page.get("vendor") == args.vendor]

    storage = StorageManager(config)
    await storage.initialize()
    monitor = CompetitorMonitor(config, storage)
    result = await monitor.check()
    await monitor.cleanup()
    await storage.close()

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    body = [
        f"# Competitor Recon Report",
        "",
        f"- Generated At: {timestamp}",
        f"- Vendor Filter: {args.vendor or 'all'}",
        "",
        _render_changes(result.get("changes", [])),
        "## Surfaces",
        "",
    ]
    for surface in result.get("surfaces", []):
        body.append(_render_surface(surface))

    report = "\n".join(body).strip() + "\n"

    if args.output:
        output_path = Path(args.output)
    else:
        reports_dir = ROOT_DIR / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        suffix = args.vendor or "all"
        output_path = reports_dir / f"competitor_recon_{suffix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"

    output_path.write_text(report, encoding="utf-8")
    print(output_path)


if __name__ == "__main__":
    asyncio.run(main())
