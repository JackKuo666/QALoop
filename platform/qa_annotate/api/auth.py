"""用户认证相关的工具函数和依赖项"""

from typing import Optional

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from qa_annotate.config import settings
from qa_annotate.database.base import get_db
from qa_annotate.database.crud import UserCRUD
from qa_annotate.schema.user import User

# HTTP Bearer 认证方案
security = HTTPBearer()


def decode_token(token: str) -> Optional[dict]:
    """解码JWT令牌"""
    try:
        # 使用JWT解码令牌
        token_data = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )
        return token_data
    except jwt.ExpiredSignatureError:
        # 令牌已过期
        return None
    except jwt.InvalidTokenError:
        # 令牌无效
        return None
    except Exception:
        return None


def get_token_from_request(request: Request) -> Optional[str]:
    """从请求中获取 token（支持 Authorization 头和 cookie）"""
    # 尝试从请求头获取认证信息
    authorization = request.headers.get("Authorization")
    if authorization and authorization.startswith("Bearer "):
        return authorization.split(" ")[1]

    # 如果没有 Authorization 头，尝试从 cookie 获取
    return request.cookies.get("access_token")


def get_user_from_token(token: str, db: Session) -> Optional[User]:
    """根据 token 获取用户（内部辅助函数）"""
    # 解码令牌
    token_data = decode_token(token)
    if not token_data:
        return None

    # 从令牌中获取用户ID
    user_id = token_data.get("user_id")
    if not user_id:
        return None

    # 从数据库获取用户
    user = UserCRUD.get_by_id(db, user_id=user_id)
    if not user:
        return None

    # 检查用户是否激活
    if not user.is_active:
        return None

    return user


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    """获取当前认证用户（依赖项）"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无法验证凭据",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # 获取令牌
    token = credentials.credentials

    # 使用辅助函数获取用户
    user = get_user_from_token(token, db)
    if not user:
        raise credentials_exception

    return user


async def get_optional_user(
    request: Request, db: Session = Depends(get_db)
) -> Optional[User]:
    """可选获取当前用户（未登录时返回None）"""
    try:
        # 从请求中获取 token
        token = get_token_from_request(request)
        if not token:
            return None

        # 使用辅助函数获取用户
        return get_user_from_token(token, db)
    except Exception:
        return None


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """获取当前激活用户（依赖项）"""
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="用户已被禁用"
        )
    return current_user


async def get_current_superuser(current_user: User = Depends(get_current_user)) -> User:
    """获取当前超级用户（依赖项）"""
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="用户已被禁用"
        )
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="权限不足，需要超级用户权限"
        )
    return current_user
