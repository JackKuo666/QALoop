"""种子问题相关的Pydantic模型"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class SeedQuestionBase(BaseModel):
    """种子问题基础模型"""

    model_config = ConfigDict(from_attributes=True)

    question: str = Field(..., description="种子问题文本", min_length=1)
    type: str = Field(..., description="类型名称", min_length=1)
    subtype: str = Field(..., description="亚类名称", min_length=1)
    species_or_domain: str = Field(..., description="物种/领域", min_length=1)
    model: str = Field(..., description="使用的模型名称", min_length=1)
    date: datetime = Field(..., description="日期")
    is_verified: bool = Field(..., description="是否人工核验")


class SeedQuestionCreate(SeedQuestionBase):
    """创建种子问题模型"""

    pass


class SeedQuestionUpdate(BaseModel):
    """更新种子问题模型"""

    model_config = ConfigDict(from_attributes=True)

    question: Optional[str] = Field(
        default=None, description="种子问题文本", min_length=1
    )
    type: Optional[str] = Field(default=None, description="类型名称", min_length=1)
    subtype: Optional[str] = Field(default=None, description="亚类名称", min_length=1)
    species_or_domain: Optional[str] = Field(default=None, description="物种/领域")
    model: Optional[str] = Field(default=None, description="使用的模型名称")
    date: Optional[datetime] = Field(default=None, description="日期")
    is_verified: Optional[bool] = Field(default=None, description="是否人工核验")


class SeedQuestion(SeedQuestionBase):
    """种子问题模型"""

    id: int = Field(..., description="种子问题ID")
    creator_id: int = Field(..., description="创建者ID")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")


class SeedQuestionWithCreator(SeedQuestion):
    """种子问题模型（包含创建者全名）"""

    creator_full_name: Optional[str] = Field(None, description="创建者全名")
