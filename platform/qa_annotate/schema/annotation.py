"""标注相关的Pydantic模型"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field, model_validator


class AnnotationType(str, Enum):
    """标注类型枚举"""

    SCORE = "score"  # 评分标注（如1-5分）
    CATEGORY = "category"  # 分类标注
    TEXT = "text"  # 文本标注
    MULTI_CHOICE = "multi_choice"  # 多选题
    SINGLE_CHOICE = "single_choice"  # 单选题
    BINARY = "binary"  # 二元标注（是/否）


class AnnotationOption(BaseModel):
    """标注选项配置"""

    option_id: str = Field(..., description="选项ID")
    label: str = Field(..., description="选项标签")
    description: Optional[str] = Field(None, description="选项描述")
    value: Union[str, int, float, bool] = Field(..., description="选项值")
    order: int = Field(0, description="显示顺序")
    enabled: bool = Field(True, description="是否启用")


class ScoreConfig(BaseModel):
    """评分配置"""

    min_score: int = Field(..., description="最小分数")
    max_score: int = Field(..., description="最大分数")
    score_step: float = Field(1.0, description="分数步长")


class CategoryConfig(BaseModel):
    """分类配置"""

    categories: Optional[List[str]] = Field(None, description="可选分类列表")


class TextConfig(BaseModel):
    """文本配置"""

    max_length: Optional[int] = Field(None, description="最大长度")


class ChoiceConfig(BaseModel):
    """选择题配置"""

    options: List[AnnotationOption] = Field(..., description="选项列表")


class BinaryConfig(BaseModel):
    """二元配置"""

    true_label: Optional[str] = Field("是", description="True值标签")
    false_label: Optional[str] = Field("否", description="False值标签")


# 配置联合类型
ConfigType = Union[
    ScoreConfig,
    CategoryConfig,
    TextConfig,
    ChoiceConfig,
    BinaryConfig,
]


class AnnotationConfig(BaseModel):
    """标注配置 - 统一配置类"""

    id: Optional[int] = Field(None, description="标注ID（自增主键，创建时无需提供）")
    name: str = Field(..., description="标注名称")
    description: Optional[str] = Field(None, description="标注描述")
    required: bool = Field(True, description="是否必填")
    show_reason: bool = Field(False, description="是否显示标注理由输入框")
    show_confidence: bool = Field(False, description="是否显示置信度输入框")

    # 标注类型
    annotation_type: AnnotationType = Field(..., description="标注类型")

    # 统一配置字段（根据 annotation_type 使用对应的配置类型）
    config: ConfigType = Field(..., description="配置内容")

    # 自定义字段
    custom_fields: Optional[Dict[str, Any]] = Field(None, description="自定义字段")

    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    @model_validator(mode="after")
    def validate_config_type(self):
        """验证 config 字段的类型是否与 annotation_type 匹配"""
        type_config_map = {
            AnnotationType.SCORE: ScoreConfig,
            AnnotationType.CATEGORY: CategoryConfig,
            AnnotationType.TEXT: TextConfig,
            AnnotationType.MULTI_CHOICE: ChoiceConfig,
            AnnotationType.SINGLE_CHOICE: ChoiceConfig,
            AnnotationType.BINARY: BinaryConfig,
        }

        expected_type = type_config_map.get(self.annotation_type)
        if expected_type is None:
            raise ValueError(f"未知的标注类型: {self.annotation_type}")

        if not isinstance(self.config, expected_type):
            raise ValueError(
                f"当 annotation_type={self.annotation_type.value} 时，"
                f"config 必须是 {expected_type.__name__} 类型，"
                f"但实际是 {type(self.config).__name__}"
            )

        return self

    class Config:
        use_enum_values = True


class ScoreAnnotation(BaseModel):
    """评分标注结果"""

    score: Union[int, float] = Field(..., description="评分")
    reason: Optional[str] = Field(None, description="评分理由")
    dimension: Optional[str] = Field(None, description="评分维度")


class TextAnnotation(BaseModel):
    """文本标注结果"""

    text: str = Field(..., description="标注文本")
    tags: Optional[List[str]] = Field(None, description="标签")


class CategoryAnnotation(BaseModel):
    """分类标注结果"""

    category: str = Field(..., description="分类")
    sub_category: Optional[str] = Field(None, description="子分类")


class ChoiceAnnotation(BaseModel):
    """选择题标注结果"""

    selected_options: List[str] = Field(..., description="选中的选项ID列表")


class BinaryAnnotation(BaseModel):
    """二元标注结果"""

    value: bool = Field(..., description="标注值（True/False）")
    confidence: Optional[float] = Field(None, ge=0, le=1, description="置信度")


class AnnotationValue(BaseModel):
    """标注值（联合类型）"""

    score: Optional[ScoreAnnotation] = None
    text: Optional[TextAnnotation] = None
    category: Optional[CategoryAnnotation] = None
    choice: Optional[ChoiceAnnotation] = None
    binary: Optional[BinaryAnnotation] = None
    raw_value: Optional[Union[str, int, float, bool, Dict[str, Any]]] = None


class AnnotationResult(BaseModel):
    """标注结果"""

    id: Optional[int] = Field(
        None, description="标注结果ID（自增主键，创建时无需提供）"
    )
    dataset_id: int = Field(..., description="数据集ID")
    dataset_item_id: int = Field(..., description="数据集项ID")
    annotation_config_id: int = Field(..., description="标注配置ID")

    # 标注值
    value: AnnotationValue = Field(..., description="标注值")

    # 标注者信息
    annotator_id: Optional[int] = Field(None, description="标注者ID")
    annotator_name: Optional[str] = Field(None, description="标注者名称")

    # 元数据
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    duration_seconds: Optional[float] = Field(None, description="标注耗时（秒）")

    # 质量信息
    confidence: Optional[float] = Field(None, ge=0, le=1, description="标注置信度")
    notes: Optional[str] = Field(None, description="备注")

    # 自定义字段
    custom_fields: Optional[Dict[str, Any]] = Field(None, description="自定义字段")


# ==================== 分析结果Schema ====================


class ScoreAnalysisStats(BaseModel):
    """评分分析统计"""

    type: str
    count: int
    average: Optional[float] = None
    min: Optional[float] = None
    max: Optional[float] = None
    distribution: Optional[Dict[str, int]] = None


class ChoiceAnalysisStats(BaseModel):
    """选择题分析统计"""

    type: str
    count: int
    option_distribution: Dict[str, int]
    option_labels: Dict[str, str]


class CategoryAnalysisStats(BaseModel):
    """分类分析统计"""

    type: str
    count: int
    category_distribution: Dict[str, int]


class BinaryAnalysisStats(BaseModel):
    """二元分析统计"""

    type: str
    count: int
    true_count: int
    false_count: int
    true_ratio: float


class TextAnalysisStats(BaseModel):
    """文本分析统计"""

    type: str
    count: int
    avg_length: Optional[float] = None
    max_length: Optional[int] = None
    min_length: Optional[int] = None
    avg_words: Optional[float] = None


class ConfigAnalysisStats(BaseModel):
    """配置分析统计"""

    config_id: int
    config_name: str
    annotation_type: str
    total_annotations: int
    coverage: float
    stats: Union[
        ScoreAnalysisStats,
        ChoiceAnalysisStats,
        CategoryAnalysisStats,
        BinaryAnalysisStats,
        TextAnalysisStats,
    ]


class NotesSummaryItem(BaseModel):
    """Notes汇总项"""

    config_name: str
    notes: List[str]
    count: int


class ProjectAnnotationAnalysis(BaseModel):
    """项目标注分析结果"""

    total_datasets: int
    total_items: int
    annotated_items_count: int  # 已标注的QA对数量（至少1个配置）
    fully_annotated_count: int  # 已完整标注的QA对数量（所有配置）
    completion_rate: float
    configs_stats: List[ConfigAnalysisStats]
    notes_summary: List[NotesSummaryItem]
