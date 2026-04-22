"""
国际化上下文管理器
提供更优雅的语言设置方式，避免在函数间传递language参数
"""

import contextvars
from utils.i18n_types import Language

# 创建上下文变量
_language_context = contextvars.ContextVar("language", default=Language.ENGLISH)


class I18nContext:
    """国际化上下文管理器"""

    @staticmethod
    def set_language(language: Language) -> None:
        """
        设置当前上下文的语言

        Args:
            language: 语言枚举值
        """
        _language_context.set(language)

    @staticmethod
    def get_language() -> Language:
        """
        获取当前上下文的语言

        Returns:
            当前语言枚举值
        """
        return _language_context.get()

    @staticmethod
    def reset_language() -> None:
        """重置语言为默认值"""
        _language_context.set(Language.ENGLISH)

    @staticmethod
    def get_language_value() -> str:
        """
        获取当前语言的字符串值

        Returns:
            语言字符串值
        """
        return _language_context.get().value


class I18nContextManager:
    """国际化上下文管理器，支持with语句"""

    def __init__(self, language: Language):
        """
        初始化上下文管理器

        Args:
            language: 要设置的语言
        """
        self.language = language
        self._previous_language = None

    def __enter__(self):
        """进入上下文时保存当前语言并设置新语言"""
        self._previous_language = I18nContext.get_language()
        I18nContext.set_language(self.language)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """退出上下文时恢复之前的语言"""
        if self._previous_language is not None:
            I18nContext.set_language(self._previous_language)


# 便捷函数
def set_language(language: Language) -> None:
    """设置当前语言"""
    I18nContext.set_language(language)


def get_language() -> Language:
    """获取当前语言"""
    return I18nContext.get_language()


def reset_language() -> None:
    """重置语言为默认值"""
    I18nContext.reset_language()


def with_language(language: Language):
    """
    创建语言上下文管理器

    Args:
        language: 要设置的语言

    Returns:
        上下文管理器
    """
    return I18nContextManager(language)


# 装饰器，用于自动设置语言
def with_language_decorator(language: Language):
    """
    装饰器，为函数自动设置语言上下文

    Args:
        language: 要设置的语言

    Returns:
        装饰器函数
    """

    def decorator(func):
        def wrapper(*args, **kwargs):
            with I18nContextManager(language):
                return func(*args, **kwargs)

        return wrapper

    return decorator
