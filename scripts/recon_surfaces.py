#!/usr/bin/env python3
"""
通用网页侦察脚本

示例：
1. 复用已有官方监控面：
   python3 scripts/recon_surfaces.py --profile official
2. 复用已有竞品监控面：
   python3 scripts/recon_surfaces.py --profile competitor --vendor zhipu
3. 临时侦察任意页面：
   python3 scripts/recon_surfaces.py --url https://www.deepseek.com/en/ --extractor deepseek
4. 侦察并自动展开首层可疑链接：
   python3 scripts/recon_surfaces.py --url https://open.bigmodel.cn/ --extractor zhipu --expand-discovered 4
"""

import argparse
import asyncio
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from core.surface_recon import SurfaceRecon, render_surface_recon_markdown
from utils.config import load_config
from utils.recon_registry import get_allowed_site_keys, infer_extractor_name


def _build_profile_surfaces(config: Dict, profile: str, vendor: str = "") -> List[Dict]:
    surfaces = []
    if profile == "official":
        for page in config.get("official_surfaces", {}).get("pages", []):
            surfaces.append(
                {
                    "name": page.get("name"),
                    "url": page.get("url"),
                    "parser": page.get("parser", "html"),
                    "extractor": "deepseek",
                    "script_probe_limit": page.get("script_probe_limit", 4),
                }
            )
    elif profile == "competitor":
        for page in config.get("competitor_surfaces", {}).get("pages", []):
            if vendor and page.get("vendor") != vendor:
                continue
            extractor = page.get("vendor") or infer_extractor_name(page.get("url", ""))
            surfaces.append(
                {
                    "name": page.get("name"),
                    "url": page.get("url"),
                    "parser": page.get("parser", "html"),
                    "extractor": extractor,
                    "allowed_site_keys": get_allowed_site_keys(extractor),
                    "script_probe_limit": page.get("script_probe_limit", 4),
                }
            )
    return surfaces


def _build_ad_hoc_surfaces(args) -> List[Dict]:
    surfaces = []
    for index, url in enumerate(args.url or [], start=1):
        extractor = args.extractor or infer_extractor_name(url)
        name = args.name if len(args.url) == 1 and args.name else f"Ad Hoc #{index}"
        surfaces.append(
            {
                "name": name,
                "url": url,
                "parser": args.parser,
                "extractor": extractor,
                "allowed_site_keys": args.allowed_site_key or get_allowed_site_keys(extractor),
                "script_probe_limit": args.script_probe_limit,
            }
        )
    return surfaces


async def main():
    parser = argparse.ArgumentParser(description="Generic website recon")
    parser.add_argument("--profile", choices=["official", "competitor"], help="Use configured surfaces")
    parser.add_argument("--vendor", choices=["zhipu", "minimax"], help="Filter competitor profile by vendor")
    parser.add_argument("--url", action="append", help="Ad hoc URL to inspect; can be repeated")
    parser.add_argument("--name", help="Display name for a single ad hoc URL")
    parser.add_argument("--extractor", choices=["deepseek", "zhipu", "minimax", "generic"], help="Force extractor")
    parser.add_argument("--parser", choices=["html", "sitemap"], default="html", help="Parser for ad hoc URL")
    parser.add_argument("--allowed-site-key", action="append", help="Allowed site keys for discovered links")
    parser.add_argument("--script-probe-limit", type=int, default=4, help="How many same-site JS bundles to probe")
    parser.add_argument("--expand-discovered", type=int, default=0, help="Fetch N discovered first-hop links")
    parser.add_argument("--output", help="Markdown output path")
    args = parser.parse_args()

    if not args.profile and not args.url:
        parser.error("需要至少提供 --profile 或 --url")

    config = load_config(ROOT_DIR / "config.yaml")
    surfaces = []
    if args.profile:
        surfaces.extend(_build_profile_surfaces(config, args.profile, vendor=args.vendor or ""))
    if args.url:
        surfaces.extend(_build_ad_hoc_surfaces(args))

    recon = SurfaceRecon(config)
    result = await recon.run(surfaces, expand_discovered=args.expand_discovered)
    await recon.cleanup()

    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    title = "Surface Recon Report"
    if args.profile == "official":
        title = "Official Surface Recon Report"
    elif args.profile == "competitor":
        title = f"Competitor Surface Recon Report ({args.vendor or 'all'})"
    elif args.url and len(args.url) == 1:
        title = f"Surface Recon Report: {args.url[0]}"

    markdown = render_surface_recon_markdown(title, result.get("surfaces", []), generated_at)

    if args.output:
        output_path = Path(args.output)
    else:
        reports_dir = ROOT_DIR / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        suffix = args.profile or "adhoc"
        if args.vendor:
            suffix = f"{suffix}_{args.vendor}"
        output_path = reports_dir / f"surface_recon_{suffix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"

    output_path.write_text(markdown, encoding="utf-8")
    print(output_path)


if __name__ == "__main__":
    asyncio.run(main())
