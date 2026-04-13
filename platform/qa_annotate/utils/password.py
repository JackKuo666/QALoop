"""密码加密和验证工具（使用SHA-256哈希+时间戳防重放）"""

import hashlib
import hmac
import time


def hash_password(password: str) -> str:
    """
    对密码进行SHA-256哈希（用于存储）

    Args:
        password: 原始密码

    Returns:
        SHA-256哈希值（64字符的十六进制字符串）
    """
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def hash_password_with_timestamp(password_hash: str, timestamp: int) -> str:
    """
    对已哈希的密码加上时间戳再次哈希（用于传输，防止重放攻击）

    Args:
        password_hash: 第一次SHA-256哈希值
        timestamp: 时间戳（Unix时间戳，秒）

    Returns:
        带时间戳的SHA-256哈希值
    """
    message = f"{password_hash}:{timestamp}"
    return hashlib.sha256(message.encode("utf-8")).hexdigest()


def verify_password_with_timestamp(
    password_hash: str, stored_hash: str, timestamp: int, time_window: int = 300
) -> bool:
    """
    验证带时间戳的密码哈希

    Args:
        password_hash: 前端传来的带时间戳的哈希值
        stored_hash: 数据库中存储的密码哈希值（第一次SHA-256的结果）
        timestamp: 时间戳
        time_window: 时间窗口（秒），默认5分钟

    Returns:
        是否验证通过
    """
    # 验证时间戳是否在有效窗口内
    current_time = int(time.time())
    if abs(current_time - timestamp) > time_window:
        return False

    # 使用存储的哈希值和时间戳重新计算
    expected_hash = hash_password_with_timestamp(stored_hash, timestamp)

    # 使用常量时间比较，防止时序攻击
    return hmac.compare_digest(
        password_hash.encode("utf-8"), expected_hash.encode("utf-8")
    )
