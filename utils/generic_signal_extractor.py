"""
通用网页信号提取器

用于没有专用 extractor 的页面，尽量保留一些普适的日期、价格、版本和文案线索。
"""

import re
from typing import Dict, List


DATE_PATTERNS = [
    r"\b20\d{2}/\d{2}/\d{2}(?:\s+\d{2}:\d{2})?\b",
    r"\b20\d{2}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z)?\b",
]

PRICE_PATTERN = r"(?:¥\s?\d+(?:\.\d+)?|\$\s?\d+(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?元)"
VERSION_PATTERNS = [
    r"\b(?:v|version)\s?\d+(?:\.\d+){1,3}\b",
    r"\b[a-z]+(?:-[a-z0-9]+){1,6}-[a-f0-9]{8,}\b",
]

HEADLINE_HINTS = [
    "pricing",
    "price",
    "token",
    "plan",
    "agent",
    "mcp",
    "model",
    "release",
    "launch",
    "coding",
    "research",
]


def _dedupe(items: List[str], limit: int = 30) -> List[str]:
    seen = set()
    output = []
    for item in items:
        normalized = item.strip().lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        output.append(item.strip())
        if len(output) >= limit:
            break
    return output


def extract_generic_signals(raw_text: str, normalized_text: str = "") -> Dict:
    text = f"{raw_text}\n{normalized_text}".strip()
    normalized = normalized_text or re.sub(r"\s+", " ", raw_text)

    dates: List[str] = []
    for pattern in DATE_PATTERNS:
        dates.extend(re.findall(pattern, text, re.IGNORECASE))

    prices = re.findall(PRICE_PATTERN, text, re.IGNORECASE)

    versions: List[str] = []
    for pattern in VERSION_PATTERNS:
        versions.extend(re.findall(pattern, text, re.IGNORECASE))

    headline_lines = []
    for line in normalized.splitlines():
        compact = re.sub(r"\s+", " ", line).strip()
        lowered = compact.lower()
        if not compact or len(compact) < 12:
            continue
        if any(hint in lowered for hint in HEADLINE_HINTS) or re.search(PRICE_PATTERN, compact):
            headline_lines.append(compact[:220])

    pricing_lines = []
    for line in normalized.splitlines():
        compact = re.sub(r"\s+", " ", line).strip()
        lowered = compact.lower()
        if not compact:
            continue
        if re.search(PRICE_PATTERN, compact) and any(
            hint in lowered for hint in ["price", "pricing", "plan", "month", "year", "订阅", "包月", "包年"]
        ):
            pricing_lines.append(compact[:220])

    return {
        "dates": _dedupe(dates, limit=20),
        "prices": _dedupe(prices, limit=20),
        "resource_versions": _dedupe(versions, limit=20),
        "headline_lines": _dedupe(headline_lines, limit=12),
        "pricing_lines": _dedupe(pricing_lines, limit=12),
    }
