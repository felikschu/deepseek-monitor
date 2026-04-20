"""
源码关键词侦察工具
"""

import re
from typing import Dict, List, Tuple


DEFAULT_KEYWORDS = ["coder", "vision", "agent", "pricing", "api"]

NOISE_MARKERS = [
    "function(",
    "__next",
    "__webpack",
    "reactjs.org/docs/error-decoder",
    "useragent should be a string",
    "useragent parameter can't be empty",
    "textencoder",
    "textdecoder",
]


def prioritize_script_urls(urls: List[str]) -> List[str]:
    def priority(url: str) -> Tuple[int, str]:
        lowered = url.lower()
        if any(token in lowered for token in ["app/", "main.", "page-", "layout-", "main-app"]):
            return (0, lowered)
        if any(token in lowered for token in ["webpack", "polyfills", "vendors", "runtime"]):
            return (2, lowered)
        return (1, lowered)

    return sorted(urls, key=priority)


def _looks_useful_string(value: str) -> bool:
    lowered = value.lower()
    if len(value.strip()) < 4:
        return False
    if any(marker in lowered for marker in NOISE_MARKERS):
        return False
    return True


def extract_keyword_strings(text: str, keywords: List[str], limit: int = 120) -> List[str]:
    output = []
    seen = set()
    for match in re.finditer(r'"([^"\\]{4,300})"', text):
        value = match.group(1)
        lowered = value.lower()
        if not any(keyword.lower() in lowered for keyword in keywords):
            continue
        if not _looks_useful_string(value):
            continue
        if lowered in seen:
            continue
        seen.add(lowered)
        output.append(value)
        if len(output) >= limit:
            break
    return output


def extract_keyword_contexts(text: str, keywords: List[str], per_keyword_limit: int = 4) -> Dict[str, List[str]]:
    result: Dict[str, List[str]] = {}
    lowered = text.lower()
    for keyword in keywords:
        items = []
        start_index = 0
        while True:
            index = lowered.find(keyword.lower(), start_index)
            if index == -1:
                break
            start = max(0, index - 180)
            end = min(len(text), index + len(keyword) + 260)
            snippet = re.sub(r"\s+", " ", text[start:end]).strip()
            if snippet and not any(noise in snippet.lower() for noise in NOISE_MARKERS):
                items.append(snippet[:500])
            if len(items) >= per_keyword_limit:
                break
            start_index = index + len(keyword)
        if items:
            deduped = []
            seen = set()
            for item in items:
                key = item.lower()
                if key in seen:
                    continue
                seen.add(key)
                deduped.append(item)
            result[keyword] = deduped
    return result


def extract_api_paths(text: str, limit: int = 120) -> List[str]:
    values = sorted(set(item.strip('"') for item in re.findall(r'"/api[^"\\]{1,220}"', text)))
    return values[:limit]

