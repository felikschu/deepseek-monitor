"""
竞品站点中的模型型号/版本/价格信号提取器
"""

import re
from typing import Dict, List


MODEL_PATTERNS = {
    "zhipu": [
        r"\bGLM-5\.1\b",
        r"\bGLM-5V-Turbo\b",
        r"\bGLM-5-Turbo\b",
        r"\bGLM-5\b",
        r"\bGLM-4\.7-Flash\b",
        r"\bGLM-4\.7\b",
        r"\bGLM-4\.5-Flash\b",
        r"\bGLM-4-Voice\b",
        r"\bGLM-4\.6V\b",
        r"\bGLM-4\.6\b",
        r"\bGLM-4\.5V\b",
        r"\bGLM-4\.5\b",
        r"\bGLM-4-Plus\b",
        r"\bGLM-4-Flash\b",
        r"\bGLM-4V-Plus\b",
        r"\bGLM-4V-9B\b",
        r"\bGLM-4V\b",
        r"\bGLM-Image\b",
        r"\bGLM-OCR\b",
        r"\bGLM-TTS\b",
        r"\bGLM-ASR-Nano\b",
        r"\bAutoGLM(?:\s+Rumination)?\b",
        r"\bGLM-PC\b",
        r"\bGLM-OS\b",
        r"\bCogAgent-9B(?:-\d+)?\b",
    ],
    "minimax": [
        r"\bMiniMax M2\.7\b",
        r"\bMiniMax M2\.5\b",
        r"\bMiniMax M2-Her\b",
        r"\bMiniMax M2\.1\b",
        r"\bMiniMax M2\b",
        r"\bMiniMax-M2-her\b",
        r"\bMiniMax Speech 2\.8\b",
        r"\bMiniMax Speech 2\.6\b",
        r"\bMiniMax Speech 2\.5\b",
        r"\bMiniMax Hailuo 2\.3(?: / 2\.3 Fast)?\b",
        r"\bMiniMax Hailuo 02\b",
        r"\bMiniMax Music 2\.6\b",
        r"\bMiniMax Music 2\.5\+\b",
        r"\bMiniMax Music 2\.5\b",
        r"\bMiniMax Music 2\.0\b",
        r"\bMiniMax Music 1\.5\b",
        r"\bMiniMax Agent\b",
        r"\bM2\.7\b",
        r"\bM2\.5\b",
        r"\bM2\.1\b",
        r"\bM2-her\b",
        r"\bHailuo 2\.3\b",
        r"\bHailuo 02\b",
        r"\bSpeech 2\.8\b",
        r"\bMusic 2\.6\b",
    ],
}


RESOURCE_VERSION_PATTERNS = {
    "minimax": [
        r"prod-en-minimax-[0-9.]+",
        r"prod-[a-z\-]+-minimax-[0-9.]+",
    ],
    "zhipu": [
        r"main-app-[a-f0-9]+",
        r"webpack-[a-f0-9]+",
    ],
}


BUSINESS_PATTERNS = {
    "zhipu": [
        r"龙虾套餐",
        r"免费试用",
        r"注册即享",
        r"2000万\s*Tokens",
        r"搜索工具服务",
        r"Code Interpreter",
        r"Web_search(?:_pro)?",
        r"本地私有化解决方案",
        r"免费申请授权",
        r"预约咨询",
        r"开放平台",
    ],
    "minimax": [
        r"Coding Plan",
        r"Token Plan",
        r"Audio Subscription",
        r"Video Packages",
        r"Pay as You Go",
        r"MiniMax Agent",
        r"free credits",
        r"立即订阅",
        r"联系销售",
        r"免费额度",
        r"contact our business team",
        r"MCP",
    ],
}


def _dedupe(values: List[str]) -> List[str]:
    seen = set()
    output = []
    for value in values:
        normalized = value.lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        output.append(value)
    return output


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _looks_useful_snippet(snippet: str) -> bool:
    if len(snippet) < 8:
        return False
    noise_markers = [
        "function(",
        "TypeError",
        "__next",
        "webpack",
        "new URL(",
        "push({stem",
        "parsedOptions",
        "metaTokens",
    ]
    lower = snippet.lower()
    if any(marker.lower() in lower for marker in noise_markers):
        return False
    return True


def _extract_context_snippets(text: str, anchor_patterns: List[str], limit: int = 16) -> List[str]:
    snippets = []
    for pattern in anchor_patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            start = max(0, match.start() - 120)
            end = min(len(text), match.end() + 180)
            snippet = _normalize_text(text[start:end]).strip()
            if snippet and _looks_useful_snippet(snippet):
                snippets.append(snippet[:220])
            if len(snippets) >= limit:
                return _dedupe(snippets)[:limit]
    return _dedupe(snippets)[:limit]


def _extract_price_tokens(pricing_lines: List[str]) -> List[str]:
    prices = []
    ignore_markers = [
        "bench",
        "benchmark",
        "leaderboard",
        "swe",
        "aime",
        "claude",
        "gpt",
        "gemini",
        "balance",
        "余额",
        "voucher",
        "reward",
        "payment amount",
    ]
    for line in pricing_lines:
        lowered = line.lower()
        if any(marker in lowered for marker in ignore_markers):
            continue
        prices.extend(re.findall(r"(?:¥\s?\d+(?:\.\d+)?|\$\s?\d+(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?元)", line))
    return _dedupe(prices)[:30]


def _filter_pricing_lines(pricing_lines: List[str]) -> List[str]:
    keep_terms = [
        "元",
        "$",
        "month",
        "year",
        "价格",
        "price",
        "包月",
        "包年",
        "订阅",
        "试用",
        "免费",
    ]
    ignore_markers = [
        "bench",
        "benchmark",
        "leaderboard",
        "swe",
        "aime",
        "claude",
        "gpt",
        "gemini",
        "balance",
        "余额",
        "score",
    ]
    kept = []
    for line in pricing_lines:
        lowered = line.lower()
        if any(marker in lowered for marker in ignore_markers):
            continue
        if any(term.lower() in lowered for term in keep_terms):
            kept.append(line)
    return _dedupe(kept)[:20]


def _summarize_commercial_actions(vendor: str, normalized: str, signals: Dict) -> List[str]:
    actions = []

    if vendor == "zhipu":
        if re.search(r"GLM Coding Plan[^。]{0,40}低至20元包月|低至20元包月[^。]{0,40}GLM Coding Plan", normalized, re.IGNORECASE):
            actions.append("GLM Coding Plan 出现低至20元包月文案")
        if re.search(r"2\.9元[^。]{0,40}5000万\s*Tokens|5000万\s*Tokens[^。]{0,40}2\.9元", normalized, re.IGNORECASE):
            actions.append("开放平台出现 2.9元 / 5000万 Tokens 特惠包")
        if "2000万 Tokens".lower() in normalized.lower():
            actions.append("新用户/拉新权益出现 2000万 Tokens")
        if "龙虾套餐" in normalized:
            actions.append("龙虾套餐与 Team 版订阅入口存在")
        if re.search(r"GLM-5V-Turbo[^。]{0,80}Coding Plan|Coding Plan[^。]{0,80}GLM-5V-Turbo", normalized, re.IGNORECASE):
            actions.append("GLM-5V-Turbo 已出现纳入 Coding Plan 的申请/预告文案")
        if "本地私有化解决方案" in normalized:
            actions.append("企业本地私有化解决方案入口存在")
        if "Code Interpreter" in normalized or "Web_search_pro" in normalized:
            actions.append("开放平台工具能力含 Code Interpreter / Web_search_pro")
        if "AutoClaw" in normalized or "autoglm.zhipuai.cn/autoclaw" in normalized.lower():
            actions.append("AutoClaw 下载入口已挂在官网/研究页")

    if vendor == "minimax":
        prices = " ".join(signals.get("prices", []))
        if all(price in prices for price in ["$10", "$20", "$50"]):
            actions.append("Token Plan 月付档位为 $10 / $20 / $50")
        if all(price in prices for price in ["$100", "$200", "$500"]):
            actions.append("Token Plan 年付档位为 $100 / $200 / $500")
        if all(price in prices for price in ["$400", "$800", "$1,500"]):
            actions.append("Highspeed 年付档位为 $400 / $800 / $1,500")
        if "Audio Subscription" in signals.get("offerings", []):
            actions.append("语音资源包入口存在")
        if "Video Packages" in signals.get("offerings", []):
            actions.append("视频资源包入口存在")
        if "Pay as You Go" in signals.get("offerings", []):
            actions.append("按量计费入口存在")
        if "/docs/token-plan/promotion" in " ".join(signals.get("pricing_paths", [])):
            actions.append("Token Plan 存在 referral / voucher 活动页")
        if "MiniMax Agent" in normalized or "agent.minimax.io" in normalized.lower():
            actions.append("Agent 独立入口存在")
        if re.search(r"MiniMax launches MCP server|MiniMax MCP Tools Now Live", normalized, re.IGNORECASE):
            actions.append("MCP Tools 已上线并兼容多家 Agent 客户端")

    return _dedupe(actions)[:12]


def extract_model_signals(text: str, vendor: str) -> Dict:
    normalized = _normalize_text(text)

    models = []
    for pattern in MODEL_PATTERNS.get(vendor, []):
        models.extend(re.findall(pattern, normalized, re.IGNORECASE))

    resource_versions = []
    for pattern in RESOURCE_VERSION_PATTERNS.get(vendor, []):
        resource_versions.extend(re.findall(pattern, normalized, re.IGNORECASE))

    date_hits = re.findall(r"2026[-/.]\d{1,2}[-/.]\d{1,2}", normalized)
    article_dates = re.findall(
        r"2026[-/]\d{1,2}[-/]\d{1,2}(?:[ T]\d{1,2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z)?)?",
        normalized,
    )
    news_slugs = re.findall(r"/news/[a-zA-Z0-9\-]+", normalized)
    offerings = []
    for pattern in BUSINESS_PATTERNS.get(vendor, []):
        offerings.extend(re.findall(pattern, normalized, re.IGNORECASE))

    pricing_lines = _extract_context_snippets(
        normalized,
        [
            r"GLM-[0-9.]+(?:-[A-Za-z0-9]+)?[^\"'\n]{0,140}(?:元|\$)",
            r"GLM-[0-9.]+(?:-[A-Za-z0-9]+)?[^\n]{0,180}(?:inPrice|outPrice|Price)[^\n]{0,80}(?:元|\$)",
            r"MiniMax(?:\s+|-)?M[0-9.]+(?:-Her)?[^\"'\n]{0,140}(?:元|\$)",
            r"MiniMax(?:\s+)?Speech\s*[0-9.]+[^\"'\n]{0,140}(?:元|\$)",
            r"MiniMax(?:\s+)?Music\s*[0-9.]+(?:\+)?[^\"'\n]{0,140}(?:元|\$)",
            r"Price[^\n]{0,220}(?:\$|\d+元)",
            r"\$\s?\d+(?:,\d{3})*(?:\.\d+)?\s*/(?:month|year)[^\n]{0,180}",
            r"(?:Coding Plan|Token Plan|Audio Subscription|Video Packages|Pay as You Go)[^\"'\n]{0,140}(?:元|\$)",
            r"(?:限时免费|免费玩到爽|注册即享|新用户注册得|立即订阅|联系销售|免费额度)[^\"'\n]{0,160}",
        ],
        limit=20,
    )
    pricing_lines = _filter_pricing_lines(pricing_lines)
    prices = _extract_price_tokens(pricing_lines)
    plan_signals = _extract_context_snippets(
        normalized,
        [
            r"(?:限时免费|免费玩到爽|注册即享|新用户注册得|免费试用|免费额度|立即订阅|联系销售)[^\"'\n]{0,160}",
            r"2000万\s*Tokens[^\"'\n]{0,120}",
            r"(?:邀你体验|卓越模型体验)[^\"'\n]{0,160}",
            r"搜索工具服务[^\"'\n]{0,140}",
            r"Code Interpreter[^\"'\n]{0,140}",
            r"Web_search(?:_pro)?[^\"'\n]{0,140}",
            r"本地私有化解决方案[^\"'\n]{0,160}",
            r"Coding Plan[^\"'\n]{0,140}",
            r"Token Plan[^\"'\n]{0,140}",
            r"Audio Subscription[^\"'\n]{0,140}",
            r"Video Packages[^\"'\n]{0,140}",
            r"Pay as You Go[^\"'\n]{0,140}",
            r"MiniMax Agent[^\"'\n]{0,140}",
        ],
        limit=12,
    )
    pricing_paths = re.findall(
        r"/docs/(?:guides/)?pricing[-a-z]+|/docs/token-plan/(?:intro|promotion)|/subscribe/token-plan|/pricing|bigmodel\.cn/[a-z0-9\-]+|autoglm\.zhipuai\.cn/[a-z0-9\-/]+|agent\.minimax\.io",
        normalized,
        re.IGNORECASE,
    )
    headline_lines = _extract_context_snippets(
        normalized,
        [
            r"GLM-[0-9.]+(?:-[A-Za-z0-9]+)?[^\"'\n]{0,180}",
            r"MiniMax(?:\s+|-)?M[0-9.]+(?:-Her)?[^\"'\n]{0,180}",
            r"MiniMax(?:\s+)?Speech\s*[0-9.]+[^\"'\n]{0,180}",
            r"MiniMax(?:\s+)?Hailuo[^\"'\n]{0,180}",
            r"MiniMax(?:\s+)?Music[^\"'\n]{0,180}",
            r"Token Plan[^\"'\n]{0,180}",
            r"GLM Coding Plan[^\"'\n]{0,180}",
            r"龙虾套餐[^\"'\n]{0,180}",
            r"MCP[^\"'\n]{0,180}",
        ],
        limit=14,
    )

    signals = {
        "models": _dedupe(models)[:80],
        "resource_versions": _dedupe(resource_versions)[:20],
        "dates": _dedupe(date_hits)[:20],
        "article_dates": _dedupe(article_dates)[:20],
        "news_slugs": _dedupe(news_slugs)[:30],
        "prices": prices,
        "pricing_lines": _dedupe(pricing_lines)[:20],
        "plan_signals": _dedupe(plan_signals)[:12],
        "offerings": _dedupe(offerings)[:20],
        "pricing_paths": _dedupe(pricing_paths)[:20],
        "headline_lines": _dedupe(headline_lines)[:14],
    }
    signals["commercial_actions"] = _summarize_commercial_actions(vendor, normalized, signals)
    return signals
