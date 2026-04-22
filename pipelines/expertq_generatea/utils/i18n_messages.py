"""
国际化消息配置文件
包含所有错误消息、成功消息、状态消息和UI标签消息的中英文映射
"""

from utils.i18n_types import Language


# 错误消息国际化
ERROR_MESSAGES = {
    Language.CHINESE: {
        "invalid_request": "无效的请求参数",
        "search_failed": "搜索失败",
        "no_results": "未找到相关结果",
        "service_unavailable": "服务暂时不可用",
        "internal_error": "内部服务器错误",
        "invalid_language": "不支持的语言设置",
        "query_too_long": "查询内容过长",
        "rate_limit_exceeded": "请求频率过高，请稍后重试",
        "authentication_failed": "认证失败",
        "permission_denied": "权限不足",
        "resource_not_found": "资源未找到",
        "network_error": "网络连接错误",
        "timeout_error": "请求超时",
        "invalid_format": "数据格式错误",
        "missing_required_field": "缺少必需字段",
        "invalid_user_id": "无效的用户ID",
        "search_service_error": "搜索服务错误",
        "llm_service_error": "语言模型服务错误",
        "embedding_service_error": "向量化服务错误",
        "database_error": "数据库错误",
    },
    Language.ENGLISH: {
        "invalid_request": "Invalid request parameters",
        "search_failed": "Search failed",
        "no_results": "No relevant results found",
        "service_unavailable": "Service temporarily unavailable",
        "internal_error": "Internal server error",
        "invalid_language": "Unsupported language setting",
        "query_too_long": "Query content too long",
        "rate_limit_exceeded": "Request rate exceeded, please try again later",
        "authentication_failed": "Authentication failed",
        "permission_denied": "Permission denied",
        "resource_not_found": "Resource not found",
        "network_error": "Network connection error",
        "timeout_error": "Request timeout",
        "invalid_format": "Invalid data format",
        "missing_required_field": "Missing required field",
        "invalid_user_id": "Invalid user ID",
        "search_service_error": "Search service error",
        "llm_service_error": "Language model service error",
        "embedding_service_error": "Embedding service error",
        "database_error": "Database error",
    },
}

# 成功消息国际化
SUCCESS_MESSAGES = {
    Language.CHINESE: {
        "search_success": "搜索成功",
        "chat_success": "聊天服务正常",
        "health_check_ok": "服务运行正常",
        "results_found": "找到相关结果",
        "processing_complete": "处理完成",
    },
    Language.ENGLISH: {
        "search_success": "Search successful",
        "chat_success": "Chat service normal",
        "health_check_ok": "Service running normally",
        "results_found": "Relevant results found",
        "processing_complete": "Processing complete",
    },
}

# 状态消息国际化
STATUS_MESSAGES = {
    Language.CHINESE: {
        "processing": "正在处理",
        "searching": "正在搜索",
        "generating": "正在生成回答",
        "completed": "已完成",
        "failed": "处理失败",
    },
    Language.ENGLISH: {
        "processing": "Processing",
        "searching": "Searching",
        "generating": "Generating answer",
        "completed": "Completed",
        "failed": "Processing failed",
    },
}

# UI标签消息国际化
LABEL_MESSAGES = {
    Language.CHINESE: {
        "web_search_start": "正在调用 Browser 进行内容检索，所需时间较长，请等待...",
        "web_search": "正在调用 Browser 进行内容检索",
        "personal_search_start": "正在调用 个人知识库 进行内容检索，所需时间较长，请等待...",
        "personal_search": "正在调用 个人知识库 进行内容检索",
        "pubmed_search_start": "正在调用 PubMed 进行内容检索，所需时间较长，请等待...",
        "pubmed_search": "正在调用 PubMed 进行内容检索",
        "generating_answer": "正在生成回答",
        "processing": "正在处理",
        "personal_search_description": "片段 {index}",
    },
    Language.ENGLISH: {
        "web_search_start": "Retrieving content from Browser, this may take a while, please wait...",
        "web_search": "Retrieving content from Browser",
        "personal_search_start": "Retrieving content from Personal Knowledge Base, this may take a while, please wait...",
        "personal_search": "Retrieving content from Personal Knowledge Base",
        "pubmed_search_start": "Retrieving content from PubMed, this may take a while, please wait...",
        "pubmed_search": "Retrieving content from PubMed",
        "generating_answer": "Generating answer",
        "processing": "Processing",
        "personal_search_description": "Chunk {index} from this reference.",
    },
}

# 系统消息国际化
SYSTEM_MESSAGES = {
    Language.CHINESE: {
        "welcome": "欢迎使用生物医学RAG服务",
        "service_start": "服务已启动",
        "service_stop": "服务已停止",
        "connection_established": "连接已建立",
        "connection_lost": "连接已断开",
        "maintenance_mode": "系统维护中",
        "updating": "系统更新中",
        "backup_restore": "备份恢复中",
    },
    Language.ENGLISH: {
        "welcome": "Welcome to Biomedical RAG Service",
        "service_start": "Service started",
        "service_stop": "Service stopped",
        "connection_established": "Connection established",
        "connection_lost": "Connection lost",
        "maintenance_mode": "System under maintenance",
        "updating": "System updating",
        "backup_restore": "Backup restoring",
    },
}


# 业务消息国际化
BUSINESS_MESSAGES = {
    Language.CHINESE: {
        "search_started": "开始搜索...",
        "search_completed": "搜索完成",
        "no_search_results": "未找到搜索结果",
        "processing_request": "正在处理请求...",
        "request_completed": "请求处理完成",
        "upload_success": "文件上传成功",
        "upload_failed": "文件上传失败",
        "download_started": "开始下载...",
        "download_completed": "下载完成",
        "operation_success": "操作成功",
        "operation_failed": "操作失败",
        "data_saved": "数据已保存",
        "data_deleted": "数据已删除",
        "data_updated": "数据已更新",
        "connection_timeout": "连接超时",
        "server_busy": "服务器繁忙",
        "maintenance_notice": "系统维护通知",
    },
    Language.ENGLISH: {
        "search_started": "Search started...",
        "search_completed": "Search completed",
        "no_search_results": "No search results found",
        "processing_request": "Processing request...",
        "request_completed": "Request completed",
        "upload_success": "File uploaded successfully",
        "upload_failed": "File upload failed",
        "download_started": "Download started...",
        "download_completed": "Download completed",
        "operation_success": "Operation successful",
        "operation_failed": "Operation failed",
        "data_saved": "Data saved",
        "data_deleted": "Data deleted",
        "data_updated": "Data updated",
        "connection_timeout": "Connection timeout",
        "server_busy": "Server busy",
        "maintenance_notice": "System maintenance notice",
    },
}

# 所有消息类型的映射
ALL_MESSAGE_TYPES = {
    "error": ERROR_MESSAGES,
    "success": SUCCESS_MESSAGES,
    "status": STATUS_MESSAGES,
    "label": LABEL_MESSAGES,
    "system": SYSTEM_MESSAGES,
    "business": BUSINESS_MESSAGES,
}


def get_message(message_type: str, key: str, language: Language) -> str:
    """
    获取指定类型的国际化消息

    Args:
        message_type: 消息类型 (error, success, status, label, system, business)
        key: 消息键
        language: 语言

    Returns:
        国际化消息字符串
    """
    if message_type not in ALL_MESSAGE_TYPES:
        return f"Unknown message type: {message_type}"

    messages = ALL_MESSAGE_TYPES[message_type]
    default_language = Language.CHINESE

    return messages.get(language, messages[default_language]).get(
        key,
        messages[default_language].get(key, f"Unknown {message_type} message: {key}"),
    )


def get_all_messages_for_language(language: Language) -> dict:
    """
    获取指定语言的所有消息

    Args:
        language: 语言

    Returns:
        包含所有消息类型的字典
    """
    result = {}
    for message_type, messages in ALL_MESSAGE_TYPES.items():
        result[message_type] = messages.get(language, messages[Language.CHINESE])
    return result


def get_available_message_types() -> list:
    """
    获取所有可用的消息类型

    Returns:
        消息类型列表
    """
    return list(ALL_MESSAGE_TYPES.keys())


def get_available_keys_for_type(message_type: str) -> list:
    """
    获取指定消息类型的所有可用键

    Args:
        message_type: 消息类型

    Returns:
        键列表
    """
    if message_type not in ALL_MESSAGE_TYPES:
        return []

    messages = ALL_MESSAGE_TYPES[message_type]
    # 使用中文作为默认语言来获取所有键
    return list(messages[Language.CHINESE].keys())
