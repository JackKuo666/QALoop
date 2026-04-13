"""项目相关的Pydantic模型"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from qa_annotate.schema.annotation import AnnotationConfig
from qa_annotate.schema.dataset import Dataset


class Project(BaseModel):
    """项目模型"""

    id: Optional[int] = Field(None, description="项目ID（自增主键，创建时无需提供）")
    name: str = Field(..., description="项目名称")
    description: Optional[str] = Field(None, description="项目描述")

    # 版本和状态
    version: Optional[str] = Field(None, description="项目版本号")
    status: Optional[str] = Field(
        "active", description="项目状态（active/inactive/archived）"
    )

    # 标签和分类
    tags: Optional[List[str]] = Field(None, description="项目标签列表")
    category: Optional[str] = Field(None, description="项目分类")

    # 创建者信息
    creator: Optional[str] = Field(None, description="创建者名称")
    creator_id: Optional[int] = Field(None, description="创建者ID")

    # 数据来源
    source: Optional[str] = Field(None, description="数据来源")
    source_url: Optional[str] = Field(None, description="数据来源URL")

    # 元数据
    metadata: Optional[Dict[str, Any]] = Field(
        None, description="额外的元数据（JSON格式）"
    )

    # 要显示的extra字段配置（数据集可继承）
    display_extra_fields: Optional[List[str]] = Field(
        None, description="要显示的extra字段列表（数据集可继承）"
    )

    # 时间戳
    created_at: Optional[datetime] = Field(None, description="创建时间")
    updated_at: Optional[datetime] = Field(None, description="更新时间")

    # 关联数据（可选，用于返回详细信息）
    datasets: Optional[List[Dataset]] = Field(
        None, description="项目下的数据集列表（可选）"
    )
    annotation_configs: Optional[List[AnnotationConfig]] = Field(
        None, description="项目关联的标注配置列表（可选）"
    )
