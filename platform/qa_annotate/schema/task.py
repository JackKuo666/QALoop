"""任务相关的Pydantic模型"""

from typing import List, Optional

from pydantic import BaseModel, Field


class EvaluationDimension(BaseModel):
    """评估维度模型"""

    name: str = Field(..., description="评估维度名称")
    description: Optional[str] = Field(None, description="评估维度描述")


class TaskInfo(BaseModel):
    """任务信息模型"""

    dataset_id: int = Field(..., description="数据集ID")
    dataset_name: str = Field(..., description="数据集名称")
    task_description: Optional[str] = Field(None, description="任务描述")
    category: Optional[str] = Field(
        None, description="数据集分类（用于匹配用户物种标签）"
    )
    target_annotation_count: int = Field(..., description="目标标注数量（计算得出）")
    project_id: Optional[int] = Field(None, description="项目ID")
    project_name: Optional[str] = Field(None, description="项目名称")
    evaluation_purpose: Optional[str] = Field(
        None, description="评估目的（从项目 metadata 获取）"
    )
    deadline: Optional[str] = Field(
        None, description="要求完成时间（从项目 metadata 获取，ISO 8601 格式）"
    )
    evaluation_dimensions: List[EvaluationDimension] = Field(
        default_factory=list,
        description="评估维度列表（从项目 annotation_configs 获取）",
    )
    annotated_count: Optional[int] = Field(None, description="已标注数量")
    progress_rate: Optional[float] = Field(None, description="标注进度百分比（0-100）")
