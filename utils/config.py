"""
配置管理工具
"""

import yaml
from pathlib import Path
from typing import Dict


def load_config(config_path: Path) -> Dict:
    """加载配置文件

    Args:
        config_path: 配置文件路径

    Returns:
        配置字典
    """
    config_path = Path(config_path)

    if not config_path.exists():
        raise FileNotFoundError(f"配置文件不存在: {config_path}")

    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    return config


def validate_config(config: Dict) -> bool:
    """验证配置

    Args:
        config: 配置字典

    Returns:
        是否有效
    """
    required_keys = [
        "monitoring",
        "targets",
        "storage"
    ]

    for key in required_keys:
        if key not in config:
            raise ValueError(f"配置缺少必需的键: {key}")

    return True
