"""
国际化工具类，支持中英文切换功能
"""

from typing import Dict, Any, Optional
from utils.i18n_types import Language
from utils.i18n_messages import get_message
from utils.i18n_context import I18nContext


class I18nUtil:
    """国际化工具类"""

    # 默认语言
    DEFAULT_LANGUAGE = Language.ENGLISH

    # 语言映射
    LANGUAGE_MAPPING = {
        "zh": Language.CHINESE,
        "zh_cn": Language.CHINESE,
        "en": Language.ENGLISH,
        "en_us": Language.ENGLISH,
    }

    @classmethod
    def parse_language(cls, language_str: Optional[str]) -> Language:
        """
        解析语言字符串

        Args:
            language_str: 语言字符串

        Returns:
            语言枚举值
        """
        if not language_str:
            return cls.DEFAULT_LANGUAGE

        # 标准化语言字符串
        normalized = language_str.lower()
        # 处理连字符和下划线
        normalized = normalized.replace("-", "_")

        return cls.LANGUAGE_MAPPING.get(normalized, cls.DEFAULT_LANGUAGE)

    @classmethod
    def get_error_message(cls, key: str, language: Optional[Language] = None) -> str:
        """
        获取错误消息

        Args:
            key: 错误消息键
            language: 语言，如果为None则使用上下文中的语言

        Returns:
            错误消息
        """
        if language is None:
            language = I18nContext.get_language()

        return get_message("error", key, language)

    @classmethod
    def get_success_message(cls, key: str, language: Optional[Language] = None) -> str:
        """
        获取成功消息

        Args:
            key: 成功消息键
            language: 语言，如果为None则使用上下文中的语言

        Returns:
            成功消息
        """
        if language is None:
            language = I18nContext.get_language()

        return get_message("success", key, language)

    @classmethod
    def get_status_message(cls, key: str, language: Optional[Language] = None) -> str:
        """
        获取状态消息

        Args:
            key: 状态消息键
            language: 语言，如果为None则使用上下文中的语言

        Returns:
            状态消息
        """
        if language is None:
            language = I18nContext.get_language()

        return get_message("status", key, language)

    @classmethod
    def get_label_message(cls, key: str, language: Optional[Language] = None) -> str:
        """
        获取UI标签消息

        Args:
            key: 标签消息键
            language: 语言，如果为None则使用上下文中的语言

        Returns:
            标签消息
        """
        if language is None:
            language = I18nContext.get_language()

        return get_message("label", key, language)

    @classmethod
    def get_system_message(cls, key: str, language: Optional[Language] = None) -> str:
        """
        获取系统消息

        Args:
            key: 系统消息键
            language: 语言，如果为None则使用上下文中的语言

        Returns:
            系统消息
        """
        if language is None:
            language = I18nContext.get_language()

        return get_message("system", key, language)

    @classmethod
    def get_business_message(cls, key: str, language: Optional[Language] = None) -> str:
        """
        获取业务消息

        Args:
            key: 业务消息键
            language: 语言，如果为None则使用上下文中的语言

        Returns:
            业务消息
        """
        if language is None:
            language = I18nContext.get_language()

        return get_message("business", key, language)

    @classmethod
    def create_error_response(
        cls,
        error_key: str,
        language: Optional[Language] = None,
        details: Optional[str] = None,
        error_code: int = 400,
    ) -> Dict[str, Any]:
        """
        创建错误响应

        Args:
            error_key: 错误消息键
            language: 语言
            details: 错误详情
            error_code: 错误代码

        Returns:
            错误响应字典
        """
        if language is None:
            language = I18nContext.get_language()

        response = {
            "success": False,
            "error": {
                "code": error_code,
                "message": cls.get_error_message(error_key, language),
                "language": language.value,
            },
        }

        if details:
            response["error"]["details"] = details

        return response

    @classmethod
    def create_success_response(
        cls,
        data: Any,
        language: Optional[Language] = None,
        message_key: str = "search_success",
    ) -> Dict[str, Any]:
        """
        创建成功响应

        Args:
            data: 响应数据
            language: 语言
            message_key: 成功消息键

        Returns:
            成功响应字典
        """
        if language is None:
            language = I18nContext.get_language()

        return {
            "success": True,
            "data": data,
            "message": cls.get_success_message(message_key, language),
            "language": language.value,
        }

    @classmethod
    def create_status_response(
        cls,
        status_key: str,
        language: Optional[Language] = None,
        data: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        创建状态响应

        Args:
            status_key: 状态消息键
            language: 语言
            data: 响应数据

        Returns:
            状态响应字典
        """
        if language is None:
            language = I18nContext.get_language()

        response = {
            "status": cls.get_status_message(status_key, language),
            "language": language.value,
        }

        if data is not None:
            response["data"] = data

        return response


# 便捷函数
def get_language(language_str: Optional[str]) -> Language:
    """获取语言枚举值"""
    return I18nUtil.parse_language(language_str)


def get_error_message(key: str, language: Optional[Language] = None) -> str:
    """获取错误消息"""
    return I18nUtil.get_error_message(key, language)


def get_success_message(key: str, language: Optional[Language] = None) -> str:
    """获取成功消息"""
    return I18nUtil.get_success_message(key, language)


def get_status_message(key: str, language: Optional[Language] = None) -> str:
    """获取状态消息"""
    return I18nUtil.get_status_message(key, language)


def get_label_message(key: str, language: Optional[Language] = None) -> str:
    """获取UI标签消息"""
    return I18nUtil.get_label_message(key, language)


def get_system_message(key: str, language: Optional[Language] = None) -> str:
    """获取系统消息"""
    return I18nUtil.get_system_message(key, language)


def get_business_message(key: str, language: Optional[Language] = None) -> str:
    """获取业务消息"""
    return I18nUtil.get_business_message(key, language)


def create_error_response(
    error_key: str,
    language: Optional[Language] = None,
    details: Optional[str] = None,
    error_code: int = 400,
) -> Dict[str, Any]:
    """创建错误响应"""
    return I18nUtil.create_error_response(error_key, language, details, error_code)


def create_success_response(
    data: Any, language: Optional[Language] = None, message_key: str = "search_success"
) -> Dict[str, Any]:
    """创建成功响应"""
    return I18nUtil.create_success_response(data, language, message_key)


def create_status_response(
    status_key: str, language: Optional[Language] = None, data: Optional[Any] = None
) -> Dict[str, Any]:
    """创建状态响应"""
    return I18nUtil.create_status_response(status_key, language, data)
