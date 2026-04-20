"""
前端 bundle 深度分析工具

把 hash 级监控提升为语义级监控：
1. default-vendors.*.js -> 依赖/运行时层
2. main.*.js -> 业务/API/feature flag 层
3. main.*.css -> UI 组件/token 层
"""

import json
import re
from typing import Dict, List, Any

from utils.deepseek_bundle_semantics import extract_deepseek_bundle_semantics


KNOWN_VENDOR_TERMS = [
    "react",
    "react-dom",
    "sentry",
    "axios",
    "highlight",
    "katex",
    "mermaid",
    "dayjs",
    "lodash",
    "protobuf",
    "zod",
    "dompurify",
    "marked",
    "websocket",
]

CLUE_PATTERNS = {
    "model_configs": r"model_configs",
    "reasoning": r"reasoning|deepthink|thinking",
    "file_upload": r"upload_file|fetch_files|file/preview|upload",
    "search": r"web_search|search",
    "captcha": r"hcaptcha|captcha|pow_challenge|pow_prefetch",
    "session_resume": r"resume_stream|session_prefetch|clean_session|logout_all_sessions",
    "share_export": r"share/create|share/list|export_all|download_export_history",
    "billing": r"billing|subscription|upgrade|paywall|payment|充值|套餐|付费",
    "coder_route": r"AgentId\.CODER|from=coder|targetBeforeOauthLoginStorageHandle",
}


def _unique_sorted(items: List[str], limit: int = 50) -> List[str]:
    values = sorted({item for item in items if item})
    return values[:limit]


def _sample(items: List[str], limit: int = 12) -> List[str]:
    return items[:limit]


def _normalize_insights(data: Dict[str, Any]) -> Dict[str, Any]:
    normalized = {}
    for key, value in (data or {}).items():
        if value in (None, "", [], {}):
            continue
        normalized[key] = value
    return normalized


def _looks_human_readable(value: str) -> bool:
    lower = value.lower()
    if len(value.strip()) < 8:
        return False
    noise_markers = [
        "function(",
        "=>",
        "__webpack",
        "typeof",
        "switch(",
        "case ",
        "new url(",
        "textencoder",
        "textdecoder",
    ]
    if any(marker in lower for marker in noise_markers):
        return False
    return (" " in value) or any("\u4e00" <= ch <= "\u9fff" for ch in value)


def _extract_keyword_strings(content: str, keywords: List[str], limit: int = 24) -> List[str]:
    pattern = re.compile(r'"([^"\\]{4,240})"', re.IGNORECASE)
    output = []
    for match in pattern.finditer(content):
        value = match.group(1)
        lower = value.lower()
        if any(keyword in lower for keyword in keywords) and _looks_human_readable(value):
            output.append(value.strip())
    return _unique_sorted(output, limit=limit)


def analyze_js_bundle(filename: str, content: str) -> Dict[str, Any]:
    lower = content.lower()
    api_endpoints = _unique_sorted(
        [ep.strip('"') for ep in re.findall(r'"/api[^"]*"', content)],
        limit=200,
    )
    external_urls = _unique_sorted(re.findall(r'https://[^"\']+', content), limit=200)
    feature_flags = []
    for name, default in re.findall(r'getFeature\("([^"]+)",\s*([^)]+)\)', content):
        feature_flags.append({"name": name, "default": default.strip()[:80]})
    dedup_flags = []
    seen_flags = set()
    for flag in feature_flags:
        key = (flag["name"], flag["default"])
        if key in seen_flags:
            continue
        dedup_flags.append(flag)
        seen_flags.add(key)

    locales = _unique_sorted(re.findall(r'\./([A-Za-z_]+)\.tsx', content), limit=200)
    vendor_terms = [term for term in KNOWN_VENDOR_TERMS if term in lower]
    agent_ids = _unique_sorted(re.findall(r'AgentId\.([A-Z_]+)', content), limit=20)
    route_clues = _unique_sorted(
        re.findall(
            r'from=coder|targetBeforeOauthLoginStorageHandle|oauth [^"]{0,40} coder|AgentId\.CODER',
            content,
            re.IGNORECASE,
        ),
        limit=20,
    )
    business_strings = _extract_keyword_strings(
        content,
        [
            "agent",
            "coder",
            "code",
            "search",
            "upload",
            "export",
            "share",
            "train",
            "pricing",
            "price",
            "reasoning",
            "vision",
        ],
        limit=24,
    )
    clue_hits = {
        clue: bool(re.search(pattern, content, re.IGNORECASE))
        for clue, pattern in CLUE_PATTERNS.items()
    }
    commit_datetime_match = re.search(r'commit_datetime:"([^"]*)"', content)

    role = "app_runtime"
    if filename.startswith("default-vendors."):
        role = "vendor_runtime"
    elif filename.startswith("main."):
        role = "application_bundle"

    if role == "vendor_runtime":
        agent_ids = []
        route_clues = []
        business_strings = []
        clue_hits["billing"] = False
        clue_hits["coder_route"] = False
        semantics = {}
    else:
        semantics = extract_deepseek_bundle_semantics(content)

    insights = {
        "bundle_role": role,
        "content_length": len(content),
        "api_endpoint_count": len(api_endpoints),
        "api_endpoints_sample": _sample(api_endpoints, 20),
        "external_url_count": len(external_urls),
        "external_urls_sample": _sample(external_urls, 20),
        "feature_flag_count": len(dedup_flags),
        "feature_flags": dedup_flags[:20],
        "locale_count": len(locales),
        "locale_sample": _sample(locales, 20),
        "vendor_terms": vendor_terms,
        "agent_ids": agent_ids,
        "route_clues": route_clues,
        "business_strings": business_strings,
        "clue_hits": clue_hits,
        "commit_datetime": commit_datetime_match.group(1) if commit_datetime_match else None,
    }
    for key, limit in [
        ("route_patterns", None),
        ("api_families", None),
        ("coder_signals", 6),
        ("vision_signals", 6),
        ("agent_signals", 6),
        ("pricing_signals", 6),
        ("hidden_capabilities", None),
    ]:
        values = semantics.get(key) or []
        if values:
            insights[key] = values[:limit] if limit else values
    return insights


def analyze_css_bundle(filename: str, content: str) -> Dict[str, Any]:
    classes = _unique_sorted(re.findall(r'\.([A-Za-z0-9_-]+)', content), limit=3000)
    css_vars = _unique_sorted(re.findall(r'--([A-Za-z0-9_-]+)', content), limit=5000)
    ds_classes = [cls for cls in classes if cls.startswith("ds-")]
    clue_classes = {}
    for clue, pattern in {
        "upload": r"upload|file",
        "search": r"search|browse|web",
        "captcha": r"captcha|pow",
        "auth": r"auth|login|wechat|sms|email",
        "share_export": r"share|export",
        "reasoning": r"thinking|reasoning|deepthink",
    }.items():
        regex = re.compile(pattern, re.IGNORECASE)
        clue_classes[clue] = [cls for cls in classes if regex.search(cls)][:12]

    return {
        "bundle_role": "style_bundle",
        "content_length": len(content),
        "class_count": len(classes),
        "class_sample": _sample(classes, 24),
        "ds_class_count": len(ds_classes),
        "ds_class_sample": _sample(ds_classes, 24),
        "css_var_count": len(css_vars),
        "css_var_sample": _sample(css_vars, 24),
        "clue_classes": clue_classes,
    }


def summarize_bundle_diff(old: Dict[str, Any], new: Dict[str, Any]) -> List[str]:
    old = _normalize_insights(old)
    new = _normalize_insights(new)
    evidence = []

    count_pairs = [
        ("api_endpoint_count", "API 端点数"),
        ("feature_flag_count", "Feature Flag 数"),
        ("locale_count", "语言包数"),
        ("external_url_count", "外链数"),
        ("class_count", "CSS 类数"),
        ("ds_class_count", "ds-* 组件类数"),
        ("css_var_count", "CSS 变量数"),
    ]
    for key, label in count_pairs:
        old_v = old.get(key)
        new_v = new.get(key)
        if old_v is not None and new_v is not None and old_v != new_v:
            evidence.append(f"{label}: {old_v} -> {new_v}")

    for key, label in [
        ("api_endpoints_sample", "API 样本"),
        ("vendor_terms", "依赖特征"),
        ("locale_sample", "语言包"),
        ("agent_ids", "Agent ID"),
        ("route_clues", "路由线索"),
        ("route_patterns", "路由模式"),
        ("api_families", "API 家族"),
        ("business_strings", "业务文案"),
        ("coder_signals", "Coder 线索"),
        ("vision_signals", "Vision 线索"),
        ("agent_signals", "Agent 线索"),
        ("pricing_signals", "Pricing 线索"),
        ("hidden_capabilities", "隐藏能力"),
        ("class_sample", "CSS 类"),
        ("css_var_sample", "CSS 变量"),
    ]:
        old_set = set(old.get(key) or [])
        new_set = set(new.get(key) or [])
        added = sorted(new_set - old_set)[:6]
        removed = sorted(old_set - new_set)[:6]
        if added:
            evidence.append(f"{label}新增: " + ", ".join(added))
        if removed:
            evidence.append(f"{label}移除: " + ", ".join(removed))

    old_clues = old.get("clue_hits") or {}
    new_clues = new.get("clue_hits") or {}
    for clue in sorted(set(old_clues) | set(new_clues)):
        if old_clues.get(clue) != new_clues.get(clue):
            evidence.append(f"能力线索 {clue}: {old_clues.get(clue)} -> {new_clues.get(clue)}")

    if old.get("commit_datetime") != new.get("commit_datetime") and (old.get("commit_datetime") or new.get("commit_datetime")):
        evidence.append(f"bundle commit 时间: {old.get('commit_datetime')} -> {new.get('commit_datetime')}")

    return evidence[:10]


def insights_equal(old: Dict[str, Any], new: Dict[str, Any]) -> bool:
    return json.dumps(_normalize_insights(old), ensure_ascii=False, sort_keys=True) == json.dumps(
        _normalize_insights(new),
        ensure_ascii=False,
        sort_keys=True,
    )
