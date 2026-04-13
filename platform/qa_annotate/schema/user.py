"""用户相关的Pydantic模型"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class UserBase(BaseModel):
    """用户基础模型"""

    username: str = Field(..., description="用户名", min_length=3, max_length=50)
    full_name: Optional[str] = Field(None, description="全名", max_length=100)
    organization: Optional[str] = Field(None, description="单位", max_length=100)
    team: Optional[str] = Field(None, description="团队", max_length=100)
    species: Optional[str] = Field(None, description="物种", max_length=100)
    is_active: bool = Field(True, description="是否激活")
    is_superuser: bool = Field(False, description="是否超级用户")


class UserCreate(UserBase):
    """创建用户模型"""

    password: str = Field(..., description="密码哈希值（SHA-256）", min_length=64)


class UserUpdate(BaseModel):
    """更新用户模型"""

    username: Optional[str] = Field(
        None, description="用户名", min_length=3, max_length=50
    )
    full_name: Optional[str] = Field(None, description="全名", max_length=100)
    organization: Optional[str] = Field(None, description="单位", max_length=100)
    team: Optional[str] = Field(None, description="团队", max_length=100)
    species: Optional[str] = Field(None, description="物种", max_length=100)
    password: Optional[str] = Field(
        None, description="密码哈希值（SHA-256）", min_length=64
    )
    is_active: Optional[bool] = Field(None, description="是否激活")
    is_superuser: Optional[bool] = Field(None, description="是否超级用户")


class User(UserBase):
    """用户模型"""

    id: int = Field(..., description="用户ID")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")

    class Config:
        from_attributes = True


class UserRegister(BaseModel):
    """用户注册模型"""

    username: str = Field(..., description="用户名", min_length=3, max_length=50)
    password: str = Field(..., description="密码哈希值（SHA-256）", min_length=64)
    full_name: Optional[str] = Field(None, description="全名", max_length=100)
    organization: Optional[str] = Field(None, description="单位", max_length=100)
    team: Optional[str] = Field(None, description="团队", max_length=100)
    species: Optional[str] = Field(None, description="物种", max_length=100)


class UserLogin(BaseModel):
    """用户登录模型"""

    username: str = Field(..., description="用户名", min_length=3, max_length=50)
    password: str = Field(
        ..., description="密码哈希值（SHA-256+时间戳）", min_length=64
    )
    timestamp: int = Field(..., description="时间戳（Unix时间戳，秒）")


class Token(BaseModel):
    """登录令牌模型"""

    access_token: str = Field(..., description="访问令牌")
    token_type: str = Field(default="bearer", description="令牌类型")
    user: User = Field(..., description="用户信息")
