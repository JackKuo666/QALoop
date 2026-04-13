"""用户相关的API接口"""

from datetime import datetime, timedelta
from typing import List

import jwt
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from qa_annotate.api.auth import get_current_active_user, get_current_superuser
from qa_annotate.config import settings
from qa_annotate.database.base import get_db
from qa_annotate.database.crud import SystemConfigCRUD, UserCRUD
from qa_annotate.schema.user import (
    Token,
    User,
    UserCreate,
    UserLogin,
    UserRegister,
    UserUpdate,
)

router = APIRouter(prefix="/users", tags=["users"])


@router.post("/register", response_model=User, status_code=status.HTTP_201_CREATED)
def register(user_register: UserRegister, db: Session = Depends(get_db)):
    """用户注册（公开接口，无需认证）

    注意：
    - 生产环境：新注册的用户默认禁用（is_active=False），需要管理员启用后才能登录
    - 非生产环境：新注册的用户默认启用（is_active=True），可以直接登录
    - 注册功能可以通过系统配置进行开关控制
    """
    # 检查是否允许注册
    allow_registration = SystemConfigCRUD.get_value(
        db, key="allow_registration", default="true"
    )
    if allow_registration and allow_registration.lower() not in ("true", "1", "yes"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="注册功能已禁用，请联系管理员",
        )

    # 检查用户名是否已存在
    existing_user = UserCRUD.get_by_username(db, username=user_register.username)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"用户名 '{user_register.username}' 已存在",
        )

    # 根据环境设置用户激活状态
    # 生产环境默认禁用，非生产环境默认启用
    is_active = not settings.is_production

    # 创建用户
    user_create = UserCreate(
        username=user_register.username,
        password=user_register.password,
        full_name=user_register.full_name,
        organization=user_register.organization,
        team=user_register.team,
        species=user_register.species,
        is_active=is_active,
        is_superuser=False,
    )

    return UserCRUD.create(db=db, user=user_create)


@router.post("/login", response_model=Token)
def login(
    user_login: UserLogin, db: Session = Depends(get_db), response: Response = None
):
    """用户登录"""
    # 先检查用户是否存在
    user = UserCRUD.authenticate_user(
        db, user_login.username, user_login.password, user_login.timestamp
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 检查用户是否激活
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="用户已被禁用，请联系管理员",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 生成JWT访问令牌
    token_expire_seconds = settings.TOKEN_EXPIRE_DAYS * 24 * 60 * 60
    expire_time = datetime.utcnow() + timedelta(days=settings.TOKEN_EXPIRE_DAYS)

    # 创建令牌载荷
    token_data = {
        "user_id": user.id,
        "username": user.username,
        "exp": int(expire_time.timestamp()),
    }

    # 使用JWT生成令牌
    access_token = jwt.encode(
        token_data,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )

    # 设置cookie: 从配置读取过期时间，HttpOnly
    if response is not None:
        response.set_cookie(
            key="access_token",
            value=access_token,
            max_age=token_expire_seconds,
            expires=token_expire_seconds,
            path="/",
            httponly=True,
            samesite="lax",
        )

    return Token(access_token=access_token, token_type="bearer", user=user)


@router.post("/", response_model=User, status_code=status.HTTP_201_CREATED)
def create_user(
    user: UserCreate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_superuser),
):
    """创建用户"""
    # 检查用户名是否已存在
    existing_user = UserCRUD.get_by_username(db, username=user.username)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"用户名 '{user.username}' 已存在",
        )

    return UserCRUD.create(db=db, user=user)


@router.put("/{user_id}", response_model=User)
def update_user(
    user_id: int,
    user_update: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """更新用户"""
    # 检查用户是否存在
    existing_user = UserCRUD.get_by_id(db, user_id=user_id)
    if not existing_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"用户 ID {user_id} 不存在"
        )

    # 非超级用户只能更新自己的信息
    if not current_user.is_superuser and current_user.id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="只能更新自己的信息"
        )

    # 非超级用户不能修改某些字段
    if not current_user.is_superuser:
        if user_update.is_active is not None or user_update.is_superuser is not None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="无权修改用户状态或权限"
            )

    # 如果更新用户名，检查新用户名是否已被使用
    if (
        user_update.username is not None
        and user_update.username != existing_user.username
    ):
        username_user = UserCRUD.get_by_username(db, username=user_update.username)
        if username_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"用户名 '{user_update.username}' 已存在",
            )

    updated_user = UserCRUD.update(db=db, user_id=user_id, user_update=user_update)
    if not updated_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"用户 ID {user_id} 不存在"
        )

    return updated_user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    """删除用户"""
    # 检查用户是否存在
    existing_user = UserCRUD.get_by_id(db, user_id=user_id)
    if not existing_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"用户 ID {user_id} 不存在"
        )

    success = UserCRUD.delete(db=db, user_id=user_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"用户 ID {user_id} 不存在"
        )

    return None


@router.get("/me", response_model=User)
def get_current_user_info(
    current_user: User = Depends(get_current_active_user),
):
    """获取当前登录用户信息"""
    return current_user


@router.get("/", response_model=List[User])
def list_users(
    skip: int = 0,
    limit: int = 100,
    is_active: bool = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取用户列表（支持分页和过滤）"""
    # 非超级用户只能查看自己的信息
    if not current_user.is_superuser:
        return [current_user]

    return UserCRUD.get_all(db=db, skip=skip, limit=limit, is_active=is_active)


@router.get("/{user_id}", response_model=User)
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """根据ID获取用户"""
    # 非超级用户只能查看自己的信息
    if not current_user.is_superuser and current_user.id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="只能查看自己的信息"
        )

    user = UserCRUD.get_by_id(db, user_id=user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"用户 ID {user_id} 不存在"
        )
    return user
