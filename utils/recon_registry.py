"""
网页侦察的 extractor / 站点规则注册表
"""

from typing import Callable, Dict, List
from urllib.parse import urlparse

from utils.deepseek_signal_extractor import extract_deepseek_signals
from utils.generic_signal_extractor import extract_generic_signals
from utils.model_signal_extractor import extract_model_signals


SITE_KEYS: Dict[str, List[str]] = {
    "deepseek": ["deepseek.com", "api-docs.deepseek.com", "cdn.deepseek.com", "status.deepseek.com"],
    "zhipu": ["zhipuai.cn", "bigmodel.cn", "z.ai"],
    "minimax": ["minimax.io", "minimaxi.com", "minimax.chat"],
    "generic": [],
}


def _host(url: str) -> str:
    return urlparse(url).netloc.lower().split(":")[0]


def infer_extractor_name(url: str) -> str:
    host = _host(url)
    for name, site_keys in SITE_KEYS.items():
        if name == "generic":
            continue
        if any(host == site or host.endswith(f".{site}") for site in site_keys):
            return name
    return "generic"


def get_allowed_site_keys(extractor_name: str) -> List[str]:
    return list(SITE_KEYS.get(extractor_name, []))


def build_signal_extractor(extractor_name: str) -> Callable[[str, str], Dict]:
    if extractor_name == "deepseek":
        return extract_deepseek_signals
    if extractor_name in ("zhipu", "minimax"):
        return lambda raw_text, normalized_text="": extract_model_signals(
            f"{raw_text}\n{normalized_text}".strip(),
            extractor_name,
        )
    return extract_generic_signals
