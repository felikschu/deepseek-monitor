"""
差异分析工具

提供各种差异比较和分析功能
"""

import re
from typing import Dict, List, Any
from difflib import SequenceMatcher


def extract_code_patterns(content: str, patterns: List[Dict]) -> Dict[str, Any]:
    """从代码中提取关键模式

    Args:
        content: 代码内容
        patterns: 模式配置列表

    Returns:
        提取的模式字典 {pattern_name: value}
    """
    extracted = {}

    for pattern_config in patterns:
        pattern = pattern_config.get("pattern")
        description = pattern_config.get("description", "")

        # 尝试匹配模式
        matches = re.findall(pattern, content, re.IGNORECASE | re.MULTILINE)

        if matches:
            # 如果有多个匹配，取前几个
            if len(matches) <= 5:
                extracted[pattern] = matches
            else:
                extracted[pattern] = matches[:5]
        else:
            extracted[pattern] = None

    return extracted


def compare_patterns(old_patterns: Dict, new_patterns: Dict) -> List[Dict]:
    """比较代码模式变化

    Args:
        old_patterns: 旧的模式字典
        new_patterns: 新的模式字典

    Returns:
        变化列表
    """
    changes = []

    all_patterns = set(old_patterns.keys()) | set(new_patterns.keys())

    for pattern in all_patterns:
        old_value = old_patterns.get(pattern)
        new_value = new_patterns.get(pattern)

        if old_value != new_value:
            change_type = "modified"
            if old_value is None:
                change_type = "added"
            elif new_value is None:
                change_type = "removed"

            changes.append({
                "pattern_name": pattern,
                "change_type": change_type,
                "old_value": old_value,
                "new_value": new_value
            })

    return changes


def deep_diff(dict1: Dict, dict2: Dict, path: str = "") -> List[Dict]:
    """深度比较两个字典的差异

    Args:
        dict1: 字典1
        dict2: 字典2
        path: 当前路径

    Returns:
        差异列表
    """
    diffs = []

    # 获取所有键
    keys1 = set(dict1.keys()) if dict1 else set()
    keys2 = set(dict2.keys()) if dict2 else set()

    all_keys = keys1 | keys2

    for key in all_keys:
        current_path = f"{path}.{key}" if path else key

        if key not in dict1:
            diffs.append({
                "path": current_path,
                "type": "added",
                "value": dict2[key]
            })
        elif key not in dict2:
            diffs.append({
                "path": current_path,
                "type": "removed",
                "value": dict1[key]
            })
        else:
            value1 = dict1[key]
            value2 = dict2[key]

            if isinstance(value1, dict) and isinstance(value2, dict):
                # 递归比较
                diffs.extend(deep_diff(value1, value2, current_path))
            elif value1 != value2:
                diffs.append({
                    "path": current_path,
                    "type": "changed",
                    "old_value": value1,
                    "new_value": value2
                })

    return diffs


def analyze_response_changes(old_response: str, new_response: str) -> Dict:
    """分析响应文本的变化

    Args:
        old_response: 旧响应
        new_response: 新响应

    Returns:
        变化分析字典
    """
    # 计算相似度
    similarity = SequenceMatcher(None, old_response, new_response).ratio()

    # 长度变化
    length_change = len(new_response) - len(old_response)

    # 检测结构变化
    old_has_code = bool(re.search(r'```[\s\S]*?```', old_response))
    new_has_code = bool(re.search(r'```[\s\S]*?```', new_response))

    return {
        "similarity": similarity,
        "length_change": length_change,
        "code_block_changed": old_has_code != new_has_code,
        "significant_change": similarity < 0.7  # 相似度低于70%认为是显著变化
    }


def normalize_text(text: str) -> str:
    """标准化文本（用于比较）

    Args:
        text: 原始文本

    Returns:
        标准化后的文本
    """
    # 移除多余空格
    text = re.sub(r'\s+', ' ', text)

    # 移除时间戳等动态内容
    text = re.sub(r'\d{4}-\d{2}-\d{2}[\s\T:]*', '[DATE]', text)
    text = re.sub(r'\d{2}:\d{2}:\d{2}', '[TIME]', text)

    return text.strip()
