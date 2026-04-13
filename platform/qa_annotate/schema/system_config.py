"""系统配置相关的Pydantic模型"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class SystemConfigBase(BaseModel):
    """系统配置基础模型"""

    key: str = Field(..., description="配置键")
    value: str = Field(..., description="配置值")
    description: Optional[str] = Field(None, description="配置描述")


class SystemConfig(SystemConfigBase):
    """系统配置模型"""

    id: int = Field(..., description="配置ID")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")

    class Config:
        from_attributes = True


class SystemConfigUpdate(BaseModel):
    """更新系统配置模型"""

    value: Optional[str] = Field(None, description="配置值")
    description: Optional[str] = Field(None, description="配置描述")
