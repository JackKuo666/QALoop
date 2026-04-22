"""
国际化类型定义
"""

from enum import Enum


class Language(Enum):
    """支持的语言枚举"""

    CHINESE = "zh"
    ENGLISH = "en"
