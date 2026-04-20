#!/usr/bin/env python3
"""
源码关键词侦察脚本

默认关键词：
- coder
- vision
- agent
- pricing
- api
"""

import argparse
import asyncio
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

import aiohttp
from bs4 import BeautifulSoup

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from utils.config import load_config
from utils.deepseek_bundle_semantics import extract_deepseek_bundle_semantics
from utils.keyword_recon import (
    DEFAULT_KEYWORDS,
    extract_api_paths,
    extract_keyword_contexts,
    extract_keyword_strings,
    prioritize_script_urls,
)


def _render_report(title: str, generated_at: str, items):
    lines = [
        f"# {title}",
        "",
        f"- Generated At: {generated_at}",
        f"- File Count: {len(items)}",
        "",
    ]
    for item in items:
        lines.extend(
            [
                f"## {item['name']}",
                "",
                f"- Source URL: {item['source_url']}",
                f"- Content Type: {item['content_type'] or '---'}",
                f"- Content Length: {item['content_length']}",
                "",
            ]
        )
        for keyword, contexts in item["keyword_contexts"].items():
            lines.append(f"### {keyword}")
            lines.append("")
            for snippet in contexts:
                lines.append(f"- {snippet}")
            lines.append("")
        if item["keyword_strings"]:
            lines.append("### Strings")
            lines.append("")
            for value in item["keyword_strings"][:40]:
                lines.append(f"- {value}")
            lines.append("")
        if item["api_paths"]:
            lines.append("### API Paths")
            lines.append("")
            for value in item["api_paths"][:60]:
                lines.append(f"- {value}")
            lines.append("")
        semantics = item.get("semantics") or {}
        for label, key in [
            ("Route Patterns", "route_patterns"),
            ("API Families", "api_families"),
            ("Hidden Capabilities", "hidden_capabilities"),
        ]:
            values = semantics.get(key) or []
            if values:
                lines.append(f"### {label}")
                lines.append("")
                for value in values[:20]:
                    lines.append(f"- {value}")
                lines.append("")
    return "\n".join(lines).strip() + "\n"


async def _fetch_text(session, url: str):
    async with session.get(url, allow_redirects=True) as response:
        text = await response.text(errors="ignore")
        return text, response.headers.get("Content-Type", "")


async def main():
    parser = argparse.ArgumentParser(description="Keyword-level source recon")
    parser.add_argument("--page", action="append", required=True, help="HTML page URL to inspect; can be repeated")
    parser.add_argument("--keyword", action="append", help="Keyword to search; repeatable")
    parser.add_argument("--script-limit", type=int, default=6, help="How many script files to inspect per page")
    parser.add_argument("--output", help="Output markdown path")
    args = parser.parse_args()

    config = load_config(ROOT_DIR / "config.yaml")
    timeout = aiohttp.ClientTimeout(total=config.get("monitoring", {}).get("timeout_seconds", 30))
    user_agent = config.get("browser", {}).get(
        "user_agent",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    )
    keywords = args.keyword or DEFAULT_KEYWORDS

    items = []
    async with aiohttp.ClientSession(timeout=timeout, headers={"User-Agent": user_agent}) as session:
        for page_url in args.page:
            html, _ = await _fetch_text(session, page_url)
            soup = BeautifulSoup(html, "html.parser")
            script_urls = []
            for tag in soup.find_all("script", src=True):
                script_urls.append(urljoin(page_url, tag["src"]))
            for script_url in prioritize_script_urls(sorted(set(script_urls)))[: args.script_limit]:
                try:
                    text, content_type = await _fetch_text(session, script_url)
                except Exception:
                    continue
                keyword_contexts = extract_keyword_contexts(text, keywords)
                keyword_strings = extract_keyword_strings(text, keywords)
                api_paths = extract_api_paths(text)
                if not keyword_contexts and not keyword_strings and not api_paths:
                    continue
                items.append(
                    {
                        "name": script_url.split("/")[-1],
                        "source_url": script_url,
                        "content_type": content_type,
                        "content_length": len(text),
                        "keyword_contexts": keyword_contexts,
                        "keyword_strings": keyword_strings,
                        "api_paths": api_paths,
                        "semantics": extract_deepseek_bundle_semantics(text),
                    }
                )

    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    title = "Keyword Source Recon Report"
    report = _render_report(title, generated_at, items)

    if args.output:
        output_path = Path(args.output)
    else:
        reports_dir = ROOT_DIR / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        output_path = reports_dir / f"keyword_recon_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"

    output_path.write_text(report, encoding="utf-8")
    print(output_path)


if __name__ == "__main__":
    asyncio.run(main())
