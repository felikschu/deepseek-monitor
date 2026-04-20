"""
DeepSeek 官网/文档页信号提取器
"""

import re
from typing import Dict, List

from utils.deepseek_bundle_semantics import extract_deepseek_bundle_semantics


MODEL_PATTERNS = [
    r"\bDeepSeek-V3\.2-Exp\b",
    r"\bDeepSeek-V3\.2\b",
    r"\bDeepSeek-V3-0324\b",
    r"\bDeepSeek-R1-0528\b",
    r"\bDeepSeek-R1-Lite\b",
    r"\bDeepSeek-R1\b",
    r"\bDeepSeek-V3\b",
    r"\bDeepSeek-V2\.5-1210\b",
    r"\bDeepSeek-V2\.5\b",
    r"\bDeepSeek-Coder V2\b",
    r"\bDeepSeek-Coder\b",
    r"\bDeepSeek-VL\b",
    r"\bDeepSeek-Math\b",
    r"\bDeepSeek-LLM\b",
    r"\bdeepseek-chat\b",
    r"\bdeepseek-reasoner\b",
]

CODING_PATTERNS = [
    r"\bCoder\b",
    r"\bcoding\b",
    r"\bcoder\b",
    r"\bagent\b",
    r"\btool use\b",
    r"\bFIM Completion\b",
    r"\bChat Prefix Completion\b",
]

PRICE_PATTERNS = [
    r"\$0\.028",
    r"\$0\.28",
    r"\$0\.42",
    r"\$0\.07",
    r"\$0\.27",
    r"\$1\.10",
    r"\$0\.14",
    r"\$0\.55",
    r"\$2\.19",
    r"0\.2元",
    r"2元",
    r"3元",
    r"0\.5元",
    r"8元",
    r"1元",
    r"4元",
    r"16元",
]


def _dedupe(values: List[str]) -> List[str]:
    seen = set()
    output = []
    for value in values:
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        output.append(value)
    return output


def _extract_context_lines(text: str, patterns: List[str], limit: int = 16) -> List[str]:
    output = []
    for pattern in patterns:
        regex = re.compile(pattern, re.IGNORECASE)
        for line in text.splitlines():
            compact = re.sub(r"\s+", " ", line).strip()
            if compact and regex.search(compact):
                output.append(compact[:220])
            if len(output) >= limit:
                return _dedupe(output)[:limit]
    return _dedupe(output)[:limit]


def extract_deepseek_signals(raw_text: str, normalized_text: str = "") -> Dict:
    text = f"{raw_text}\n{normalized_text}".strip()
    normalized = normalized_text or re.sub(r"\s+", " ", raw_text)
    bundle_signals = extract_deepseek_bundle_semantics(text)

    models = []
    for pattern in MODEL_PATTERNS:
        models.extend(re.findall(pattern, text, re.IGNORECASE))

    coding = []
    for pattern in CODING_PATTERNS:
        coding.extend(re.findall(pattern, text, re.IGNORECASE))

    prices = []
    for pattern in PRICE_PATTERNS:
        prices.extend(re.findall(pattern, text, re.IGNORECASE))

    # 尝试提取定价页中的结构化行
    pricing_lines = []
    for line in normalized.splitlines():
        compact = line.strip()
        if not compact:
            continue
        lower = compact.lower()
        if ("deepseek-chat" in lower or "deepseek-reasoner" in lower) and any(
            token in compact for token in ["$", "元", "¥"]
        ):
            pricing_lines.append(compact[:200])
        if ("pricing" in lower or "price" in lower or "agents" in lower) and any(
            token in compact for token in ["DeepSeek", "$", "元"]
        ):
            pricing_lines.append(compact[:200])

    headline_source = normalized_text
    if not headline_source:
        literal_chunks = re.findall(r'"([^"\\]{6,260})"', raw_text)
        headline_source = "\n".join(literal_chunks)

    headline_lines = _extract_context_lines(
        headline_source,
        [
            r"DeepSeek-V3\.2[^\"'\n]{0,180}",
            r"Reasoning-first models built for agents[^\"'\n]{0,120}",
            r"Chat Prefix Completion[^\"'\n]{0,140}",
            r"FIM[^\"'\n]{0,140}",
            r"Function Calling[^\"'\n]{0,140}",
            r"DeepSeek API Pricing[^\"'\n]{0,140}",
        ],
        limit=12,
    )

    return {
        "models": _dedupe(models)[:40],
        "coding_signals": _dedupe(coding)[:20],
        "prices": _dedupe(prices)[:30],
        "pricing_lines": _dedupe(pricing_lines)[:20],
        "headline_lines": _dedupe(headline_lines)[:12],
        "agent_ids": bundle_signals.get("agent_ids", []),
        "route_patterns": bundle_signals.get("route_patterns", []),
        "api_paths": bundle_signals.get("api_paths", []),
        "api_families": bundle_signals.get("api_families", []),
        "coder_signals": bundle_signals.get("coder_signals", []),
        "vision_signals": bundle_signals.get("vision_signals", []),
        "agent_signals": bundle_signals.get("agent_signals", []),
        "pricing_signals": bundle_signals.get("pricing_signals", []),
        "hidden_capabilities": bundle_signals.get("hidden_capabilities", []),
    }
