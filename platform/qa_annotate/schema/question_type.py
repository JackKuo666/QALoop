"""问题类型相关的Pydantic模型"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class QuestionTypeBase(BaseModel):
    """问题类型基础模型"""

    type: str = Field(..., description="类型名称", min_length=1)
    subtype: str = Field(..., description="亚类名称", min_length=1)
    order: Optional[int] = Field(0, description="显示顺序")


class QuestionTypeCreate(QuestionTypeBase):
    """创建问题类型模型"""

    pass


class QuestionTypeUpdate(BaseModel):
    """更新问题类型模型"""

    type: Optional[str] = Field(None, description="类型名称", min_length=1)
    subtype: Optional[str] = Field(None, description="亚类名称", min_length=1)
    order: Optional[int] = Field(None, description="显示顺序")


class QuestionType(QuestionTypeBase):
    """问题类型模型"""

    id: int = Field(..., description="类型ID")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")

    model_config = ConfigDict(from_attributes=True)
