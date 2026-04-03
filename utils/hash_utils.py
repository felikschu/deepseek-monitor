"""Hash 工具模块"""

import hashlib


def calculate_file_hash(content: bytes, algorithm: str = "md5") -> str:
    """计算文件内容的 hash

    Args:
        content: 文件内容字节
        algorithm: hash 算法，默认 md5

    Returns:
        hash 十六进制字符串
    """
    h = hashlib.new(algorithm)
    h.update(content)
    return h.hexdigest()
