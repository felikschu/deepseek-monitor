"""
DeepSeek 前端 bundle 语义提取器

把源码级线索整理成更接近产品语义的结构，便于监控和报告复用。
"""

import re
from typing import Dict, List


def _dedupe(values: List[str], limit: int = 40) -> List[str]:
    seen = set()
    output = []
    for value in values:
        compact = re.sub(r"\s+", " ", value).strip()
        if not compact:
            continue
        key = compact.lower()
        if key in seen:
            continue
        seen.add(key)
        output.append(compact)
        if len(output) >= limit:
            break
    return output


def _snippet(text: str, pattern: str, limit: int = 6, before: int = 160, after: int = 260) -> List[str]:
    items = []
    for match in re.finditer(pattern, text, re.IGNORECASE):
        start = max(0, match.start() - before)
        end = min(len(text), match.end() + after)
        items.append(text[start:end])
        if len(items) >= limit:
            break
    return _dedupe(items, limit=limit)


def _extract_api_paths(text: str) -> List[str]:
    values = [
        item.strip('"')
        for item in re.findall(r'"/api/v0/[^"\\]{1,220}"', text, re.IGNORECASE)
    ]
    return _dedupe(sorted(values), limit=120)


def _extract_api_families(paths: List[str]) -> List[str]:
    families = []
    for path in paths:
        parts = [part for part in path.split("/") if part]
        if len(parts) >= 3:
            families.append("/".join(parts[:3]))
    return _dedupe(sorted(families), limit=30)


def _derive_hidden_capabilities(signals: Dict) -> List[str]:
    items = []

    if "CODER" in signals.get("agent_ids", []) and signals.get("route_patterns"):
        items.append("CODER 已进入 Agent 路由体系，而不是纯文案占位")

    coder_blob = " ".join(signals.get("coder_signals", []))
    if any(token in coder_blob.lower() for token in ["oauth", "targetbeforeoauthloginstoragehandle", "从 coder"]):
        items.append("登录前存在指向 coder 的 OAuth 回跳逻辑")

    vision_blob = " ".join(signals.get("vision_signals", []))
    if "file_feature" in vision_blob and "switchable" in vision_blob:
        items.append("Vision 能力由 model_configs 中 enabled/switchable/file_feature.vision 联合决定")
    elif signals.get("vision_signals"):
        items.append("Vision 并非静态文案，已接入模型选择与文件上传链路")

    if "/a/:agentId" in signals.get("route_patterns", []) and "/a/:agentId/s/:sessionId" in signals.get("route_patterns", []):
        items.append("前端主会话结构已明确区分 Agent 与 Agent Session 两级路由")

    families = signals.get("api_families", [])
    if any(family.startswith("api/v0/chat") for family in families):
        items.append("Chat 能力面已包含 completion / resume / session create 等接口族")
    if any(family.startswith("api/v0/file") for family in families):
        items.append("文件上传、预览与 OCR 类入口已经暴露在前端接口面中")
    if any(family.startswith("api/v0/share") for family in families):
        items.append("分享与导出能力已经是正式接口面的一部分")
    if any(family.startswith("api/v0/client") for family in families):
        items.append("客户端设置由 /api/v0/client/settings 下发，适合追踪 model_configs 灰度")

    pricing_blob = " ".join(signals.get("pricing_signals", []))
    if "api pricing" in pricing_blob.lower():
        items.append("官网公开面仍在强调 API Pricing，而非新套餐页切换")

    return _dedupe(items, limit=12)


def extract_deepseek_bundle_semantics(text: str) -> Dict[str, List[str]]:
    api_paths = _extract_api_paths(text)
    route_patterns = _dedupe(
        re.findall(
            r'/(?:a/:agentId(?:/s/:sessionId)?|share/:shareId|authorized|sign_up|sign_in|forgot_password|feedback)',
            text,
        ),
        limit=20,
    )
    agent_ids = _dedupe(re.findall(r"AgentId\.([A-Z_]+)", text), limit=20)

    signals = {
        "agent_ids": agent_ids,
        "route_patterns": route_patterns,
        "api_paths": api_paths,
        "api_families": _extract_api_families(api_paths),
        "coder_signals": _dedupe(
            _snippet(text, r"AgentId\.CODER")
            + _snippet(text, r"targetBeforeOauthLoginStorageHandle")
            + _snippet(text, r"从 coder")
            + _snippet(text, r"oauth [^\"']{0,80}coder"),
            limit=8,
        ),
        "vision_signals": _dedupe(
            _snippet(text, r"findVisionModel")
            + _snippet(text, r"file_feature")
            + _snippet(text, r"modelSwitchVisUploadTooltip")
            + _snippet(text, r"modelSwitchNoTextImagesBanner")
            + _snippet(text, r"dragFileToUpload(?:General|OCR)")
            + _snippet(text, r"onlyExtractTextFromFiles"),
            limit=10,
        ),
        "agent_signals": _dedupe(
            _snippet(text, r"AGENT_SESSION")
            + _snippet(text, r"/a/:agentId/s/:sessionId")
            + _snippet(text, r"agentSelectionCreateSessionTooltip")
            + _snippet(text, r"setAgentPrompt")
            + _snippet(text, r"clearAgentPrompt")
            + _snippet(text, r"isAgentOrSession"),
            limit=10,
        ),
        "pricing_signals": _dedupe(
            _snippet(text, r"API Pricing")
            + _snippet(text, r"Reasoning-first models built for agents")
            + _snippet(text, r"Chat Prefix Completion")
            + _snippet(text, r"FIM Completion")
            + _snippet(text, r"Function Calling"),
            limit=10,
        ),
    }
    signals["hidden_capabilities"] = _derive_hidden_capabilities(signals)
    return signals
