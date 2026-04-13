"""QA对数据集相关的Pydantic模型 - 通用设计"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class QAPair(BaseModel):
    """问题-答案对模型"""

    id: Optional[int] = Field(None, description="数据项ID（自增主键，创建时无需提供）")
    dataset_id: int = Field(..., description="所属数据集ID")
    question: str = Field(..., description="问题内容", min_length=1)
    answer: str = Field(..., description="答案内容", min_length=1)

    class Config:
        """Pydantic配置"""

        # 允许额外字段
        extra = "allow"


class Dataset(BaseModel):
    """数据集模型"""

    id: Optional[int] = Field(None, description="数据集ID（自增主键，创建时无需提供）")
    name: str = Field(..., description="数据集名称")
    description: Optional[str] = Field(None, description="数据集描述")

    # 版本和状态
    version: Optional[str] = Field(None, description="数据集版本号")
    status: Optional[str] = Field(
        "active", description="数据集状态（active/inactive/archived）"
    )

    # 标签和分类
    tags: Optional[List[str]] = Field(None, description="数据集标签列表")
    category: Optional[str] = Field(None, description="数据集分类")

    # 创建者信息
    creator: Optional[str] = Field(None, description="创建者名称")
    creator_id: Optional[int] = Field(None, description="创建者ID")

    # 标注者信息
    annotator_id: Optional[int] = Field(None, description="标注者ID")
    annotator_name: Optional[str] = Field(None, description="标注者名称")

    # 数据来源
    source: Optional[str] = Field(None, description="数据来源")
    source_url: Optional[str] = Field(None, description="数据来源URL")

    # 元数据
    metadata: Optional[Dict[str, Any]] = Field(
        None, description="额外的元数据（JSON格式）"
    )

    # 要显示的extra字段配置
    display_extra_fields: Optional[List[str]] = Field(
        None, description="要显示的extra字段列表"
    )

    # 所属项目（可选）
    project_id: Optional[int] = Field(None, description="所属项目ID（可选）")

    # 时间戳（如果需要在 Pydantic 模型中包含）
    created_at: Optional[datetime] = Field(None, description="创建时间")
    updated_at: Optional[datetime] = Field(None, description="更新时间")
