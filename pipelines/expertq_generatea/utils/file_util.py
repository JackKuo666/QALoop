"""
文件工具模块，提供文件下载URL获取功能。

该模块实现了文件下载URL的获取功能，直接调用文件服务，
不依赖 Redis 缓存。
"""

import hashlib
from typing import Dict, List, Optional, Any
from urllib.parse import urljoin

from utils.bio_logger import bio_logger as logger
from utils.http_util import async_http_get, HTTPError
from config.global_storage import get_model_config


class FileUtilError(Exception):
    """文件下载相关错误的异常类。"""

    def __init__(self, message: str, error_code: int = 500):
        self.message = message
        self.error_code = error_code
        super().__init__(f"File Util Error: {message}")


class FileUtil:
    """文件工具类，提供文件下载URL获取功能。"""

    def __init__(self):
        """初始化文件工具类。"""
        self.config = get_model_config()
        self.file_config = self.config.get("file_service", {})
        self.base_url = self.file_config.get("base_url", "")
        self.download_path = self.file_config.get(
            "download_path", "/getFileDownloadUrl"
        )
        self.get_info_path = self.file_config.get("get_info_path", "/getFileInfos")

    def _generate_cache_key(self, file_id: str, biz: str) -> str:
        """
        生成缓存键。

        Args:
            file_id: 文件ID

        Returns:
            缓存键字符串
        """
        cache_key = f"{biz}:{hashlib.md5(file_id.encode()).hexdigest()}"
        return cache_key

    async def _get_download_url_from_service(
        self, file_id: str, user_id: str
    ) -> Dict[str, Any]:
        """
        从文件服务获取下载URL。

        Args:
            file_id: 文件ID

        Returns:
            包含下载URL的字典

        Raises:
            FileUtilError: 当文件服务请求失败时
        """
        try:
            request_url = urljoin(self.base_url, self.download_path)
            params = {"file_id": user_id, "expires": 600}
            headers = {"X-User-Id": file_id, "accept": "application/json"}

            data = await async_http_get(
                url=request_url, params=params, timeout=10.0, headers=headers
            )

            logger.info(f"Successfully got download URL for file_id: {file_id}")
            return data

        except HTTPError as e:
            if e.status_code == 404:
                raise FileUtilError(f"File not found: {file_id}", 404) from e
            elif e.status_code == 403:
                raise FileUtilError(f"Access denied for file: {file_id}", 403) from e
            else:
                logger.error(
                    f"File service error for file_id {file_id}: {e.status_code} - {e.message}"
                )
                raise FileUtilError(
                    f"File service error: {e.status_code} - {e.message}", e.status_code
                ) from e
        except Exception as e:
            logger.error(
                f"Unexpected error when requesting download URL for file_id {file_id}: {e}"
            )
            raise FileUtilError(f"Unexpected error: {str(e)}", 500) from e

    async def _get_file_info_from_service(
        self, file_id_list: List[str], user_id: str
    ) -> Dict[str, Any]:
        """
        从文件服务获取文件信息。

        Args:
            file_id_list: 文件ID列表

        Returns:
            包含文件信息的字典

        Raises:
            FileUtilError: 当文件服务请求失败时
        """
        try:
            request_url = urljoin(self.base_url, self.get_info_path)
            params = {"file_id": file_id_list}
            headers = {"X-User-Id": user_id, "accept": "application/json"}

            data = await async_http_get(
                url=request_url, params=params, timeout=10.0, headers=headers
            )

            return data
        except HTTPError as e:
            if e.status_code == 404:
                raise FileUtilError(f"File not found: {file_id_list}", 404) from e
            elif e.status_code == 403:
                raise FileUtilError(
                    f"Access denied for file: {file_id_list}", 403
                ) from e
            else:
                logger.error(
                    f"File service error for file_id {file_id_list}: {e.status_code} - {e.message}"
                )
                raise FileUtilError(
                    f"File service error: {e.status_code} - {e.message}", e.status_code
                ) from e
        except Exception as e:
            logger.error(
                f"Unexpected error when requesting download URL for file_id {file_id_list}: {e}"
            )
            raise FileUtilError(f"Unexpected error: {str(e)}", 500) from e

    async def get_file_download_url(self, file_id: str, user_id: str) -> Dict[str, Any]:
        """
        获取文件下载URL。

        Args:
            file_id: 文件ID
            user_id: 用户ID

        Returns:
            包含下载URL信息的字典

        Raises:
            FileUtilError: 当获取下载URL失败时
        """
        if not file_id:
            raise FileUtilError("File ID is required", 400)

        return await self._get_download_url_from_service(file_id, user_id)

    async def get_file_info(
        self, file_id_list: List[str], user_id: str
    ) -> Dict[str, Any]:
        """
        获取文件信息。

        Args:
            file_id_list: 文件ID列表
            user_id: 用户ID

        Returns:
            包含文件信息的字典

        Raises:
            FileUtilError: 当获取文件信息失败时
        """
        if not file_id_list:
            raise FileUtilError("File ID list is required", 400)
        if not user_id:
            raise FileUtilError("User ID is required", 400)

        return await self._get_file_info_from_service(file_id_list, user_id)


# 全局文件工具实例
_file_util: Optional[FileUtil] = None


def get_file_util() -> FileUtil:
    """
    获取全局文件工具实例。

    Returns:
        FileUtil实例
    """
    global _file_util
    if _file_util is None:
        _file_util = FileUtil()
    return _file_util
