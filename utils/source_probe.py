"""
页面脚本资源探针

把页面 HTML 里的同站点 JS bundle 也纳入侦察，避免漏掉只存在于源码中的型号、
价格、套餐、版本号等信号。
"""

from typing import Any, Callable, Dict, List
from urllib.parse import urlparse

from loguru import logger

DISCOVERY_KEYWORDS = [
    "pricing",
    "price",
    "token-plan",
    "promotion",
    "referral",
    "subscribe",
    "subscription",
    "paygo",
    "coding",
    "plan",
    "package",
    "research",
    "news",
    "models",
    "model",
    "agent",
    "mcp",
    "api",
    "docs",
    "audio",
    "video",
    "speech",
    "music",
    "hailuo",
    "glm",
    "autoglm",
    "claw",
    "m27",
    "m2",
]


def _site_key(url: str) -> str:
    host = urlparse(url).netloc.lower().split(":")[0]
    parts = [part for part in host.split(".") if part]
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return host


def _dedupe(items: List[str], limit: int = 100) -> List[str]:
    seen = set()
    output = []
    for item in items:
        if not item:
            continue
        key = item.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        output.append(item.strip())
        if len(output) >= limit:
            break
    return output


def merge_signal_maps(base: Dict[str, Any], extra: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(base)
    for key, value in extra.items():
        if isinstance(value, list):
            merged[key] = _dedupe((merged.get(key) or []) + value)
        elif isinstance(value, dict):
            current = merged.get(key) or {}
            if isinstance(current, dict):
                merged[key] = {**current, **value}
            else:
                merged[key] = value
        elif value not in (None, "", [], {}):
            merged[key] = value
    return merged


def pick_interesting_links(
    page_url: str,
    candidate_links: List[str],
    allowed_site_keys: List[str] = None,
    keywords: List[str] = None,
    limit: int = 20,
) -> List[str]:
    allowed = set(allowed_site_keys or [_site_key(page_url)])
    terms = [term.lower() for term in (keywords or DISCOVERY_KEYWORDS)]
    ignore_terms = ["/faq/", "history-modelinfo"]
    picked = []

    for raw_link in candidate_links:
        if not raw_link:
            continue
        parsed = urlparse(raw_link)
        if parsed.scheme not in ("http", "https"):
            continue
        if _site_key(raw_link) not in allowed:
            continue

        lowered = f"{parsed.netloc}{parsed.path}".lower()
        if any(term in lowered for term in ignore_terms):
            continue
        if not any(term in lowered for term in terms):
            continue

        normalized = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        if parsed.query and any(term in parsed.query.lower() for term in terms):
            normalized = f"{normalized}?{parsed.query}"
        picked.append(normalized)

    return _dedupe(picked, limit=limit)


def _script_priority(url: str) -> tuple:
    lowered = url.lower()
    if any(token in lowered for token in ["app.", "main.", "page-", "/app", "/main"]):
        return (0, lowered)
    if any(token in lowered for token in ["runtime", "polyfill", "vendors", "chunk-libs", "chunk-vue", "elementui"]):
        return (2, lowered)
    return (1, lowered)


async def probe_script_assets(
    session,
    page_url: str,
    script_urls: List[str],
    extractor: Callable[[str], Dict[str, Any]],
    limit: int = 6,
    max_chars: int = 1_500_000,
) -> Dict[str, Any]:
    page_key = _site_key(page_url)
    candidates = []
    for url in script_urls:
        if _site_key(url) == page_key:
            candidates.append(url)
    candidates = sorted(_dedupe(candidates, limit=200), key=_script_priority)

    aggregated: Dict[str, Any] = {}
    probed = []

    for script_url in candidates[:limit]:
        try:
            async with session.get(script_url, allow_redirects=True) as response:
                if response.status >= 400:
                    continue
                content_type = response.headers.get("Content-Type", "")
                if "javascript" not in content_type and "text/plain" not in content_type:
                    continue
                text = await response.text(errors="ignore")
                if max_chars and len(text) > max_chars:
                    text = text[:max_chars]
                signals = extractor(text) or {}
                aggregated = merge_signal_maps(aggregated, signals)
                probed.append(
                    {
                        "url": script_url,
                        "status_code": response.status,
                        "content_type": content_type,
                        "last_modified": response.headers.get("Last-Modified", ""),
                    }
                )
        except Exception as exc:
            logger.debug(f"脚本探针失败 {script_url}: {exc}")

    return {
        "signals": aggregated,
        "probe": {
            "candidate_count": len(candidates),
            "probed_count": len(probed),
            "probed_urls": [item["url"] for item in probed],
            "last_modified_values": _dedupe(
                [item.get("last_modified", "") for item in probed if item.get("last_modified")]
            ),
        },
    }
