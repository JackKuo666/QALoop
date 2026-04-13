"""数据库模型定义"""

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
)
from sqlalchemy.orm import backref, relationship

from qa_annotate.database.base import Base
from qa_annotate.schema.annotation import (
    AnnotationConfig,
    AnnotationResult,
    AnnotationType,
    AnnotationValue,
)
from qa_annotate.schema.dataset import Dataset, QAPair
from qa_annotate.schema.project import Project
from qa_annotate.schema.question_type import QuestionType, QuestionTypeCreate
from qa_annotate.schema.seed_question import SeedQuestion, SeedQuestionCreate
from qa_annotate.schema.user import User, UserCreate, UserUpdate

# 关联表：Dataset 与 AnnotationConfig 的多对多关系
dataset_annotation_config_association = Table(
    "dataset_annotation_config_association",
    Base.metadata,
    Column(
        "dataset_id",
        Integer,
        ForeignKey("datasets.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "annotation_config_id",
        Integer,
        ForeignKey("annotation_configs.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("created_at", DateTime, default=datetime.now, nullable=False),
)

# 关联表：Project 与 AnnotationConfig 的多对多关系
project_annotation_config_association = Table(
    "project_annotation_config_association",
    Base.metadata,
    Column(
        "project_id",
        Integer,
        ForeignKey("projects.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "annotation_config_id",
        Integer,
        ForeignKey("annotation_configs.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "order", Integer, default=0, nullable=False, comment="配置在项目中的显示顺序"
    ),
    Column("created_at", DateTime, default=datetime.now, nullable=False),
)


class AnnotationConfigModel(Base):
    """标注配置数据库模型"""

    __tablename__ = "annotation_configs"

    # 主键（自增）
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)

    # 基本信息
    name = Column(String, nullable=False, index=True)
    description = Column(Text, nullable=True)
    required = Column(Boolean, default=True, nullable=False)
    show_reason = Column(Boolean, default=False, nullable=False)
    show_confidence = Column(Boolean, default=False, nullable=False)

    # 标注类型
    annotation_type = Column(String, nullable=False, index=True)

    # 配置内容（JSON 序列化）
    config_json = Column(JSON, nullable=False)

    # 自定义字段（JSON 序列化）
    custom_fields_json = Column(JSON, nullable=True)

    # 时间戳
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.now, onupdate=datetime.now, nullable=False
    )

    # 标记删除（已废弃：不再使用标记删除功能，删除操作改为硬删除，但保留字段以维持数据库结构）
    is_deleted = Column(Boolean, default=False, nullable=False, index=True)
    deleted_at = Column(DateTime, nullable=True)

    # 关系：标注配置可以关联到多个数据集和项目
    datasets = relationship(
        "DatasetModel",
        secondary=dataset_annotation_config_association,
        back_populates="annotation_configs",
    )
    projects = relationship(
        "ProjectModel",
        secondary=project_annotation_config_association,
        back_populates="annotation_configs",
    )

    @classmethod
    def from_pydantic(cls, config: AnnotationConfig) -> "AnnotationConfigModel":
        """从 Pydantic 模型创建数据库模型"""
        # 处理 annotation_type：可能是枚举或字符串
        if isinstance(config.annotation_type, str):
            annotation_type_value = config.annotation_type
        else:
            annotation_type_value = config.annotation_type.value

        # 创建时如果提供了 id 则使用，否则让数据库自动生成
        model_data = {
            "name": config.name,
            "description": config.description,
            "required": config.required,
            "show_reason": config.show_reason,
            "show_confidence": config.show_confidence,
            "annotation_type": annotation_type_value,
            "config_json": config.config.model_dump(),
            "custom_fields_json": config.custom_fields,
            "created_at": config.created_at,
            "updated_at": config.updated_at,
        }
        if config.id is not None:
            model_data["id"] = config.id

        return cls(**model_data)

    def to_pydantic(self) -> AnnotationConfig:
        """转换为 Pydantic 模型"""
        from qa_annotate.schema.annotation import (
            BinaryConfig,
            CategoryConfig,
            ChoiceConfig,
            ScoreConfig,
            TextConfig,
        )

        # 根据 annotation_type 反序列化 config
        type_config_map = {
            AnnotationType.SCORE.value: ScoreConfig,
            AnnotationType.CATEGORY.value: CategoryConfig,
            AnnotationType.TEXT.value: TextConfig,
            AnnotationType.MULTI_CHOICE.value: ChoiceConfig,
            AnnotationType.SINGLE_CHOICE.value: ChoiceConfig,
            AnnotationType.BINARY.value: BinaryConfig,
        }

        config_class = type_config_map.get(self.annotation_type)
        if config_class is None:
            raise ValueError(f"未知的标注类型: {self.annotation_type}")

        config = config_class(**self.config_json)

        return AnnotationConfig(
            id=self.id,
            name=self.name,
            description=self.description,
            required=self.required,
            show_reason=self.show_reason,
            show_confidence=self.show_confidence,
            annotation_type=AnnotationType(self.annotation_type),
            config=config,
            custom_fields=self.custom_fields_json,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )


class AnnotationResultModel(Base):
    """标注结果数据库模型"""

    __tablename__ = "annotation_results"

    # 主键（自增）
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)

    # 关联信息
    dataset_id = Column(
        Integer,
        ForeignKey("datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    dataset_item_id = Column(
        Integer,
        ForeignKey("qa_pairs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    annotation_config_id = Column(
        Integer,
        ForeignKey("annotation_configs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # 标注值（JSON 序列化）
    value_json = Column(JSON, nullable=False)

    # 标注者信息
    annotator_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    annotator_name = Column(String, nullable=True)

    # 时间戳
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.now, onupdate=datetime.now, nullable=False
    )
    duration_seconds = Column(Float, nullable=True)

    # 质量信息
    confidence = Column(Float, nullable=True)
    notes = Column(Text, nullable=True)

    # 自定义字段（JSON 序列化）
    custom_fields_json = Column(JSON, nullable=True)

    # 关系：标注结果属于一个数据集、一个QA对、一个标注配置、一个标注者
    dataset = relationship(
        "DatasetModel",
        backref=backref("annotation_results", passive_deletes=True),
        passive_deletes=True,
    )
    qa_pair = relationship(
        "QAPairModel",
        backref=backref("annotation_results", passive_deletes=True),
        passive_deletes=True,
    )
    annotation_config = relationship(
        "AnnotationConfigModel",
        backref=backref("annotation_results", passive_deletes=True),
        passive_deletes=True,
    )
    annotator = relationship(
        "UserModel", foreign_keys=[annotator_id], backref="annotation_results"
    )

    @classmethod
    def from_pydantic(cls, result: AnnotationResult) -> "AnnotationResultModel":
        """从 Pydantic 模型创建数据库模型"""
        # 创建时如果提供了 id 则使用，否则让数据库自动生成
        model_data = {
            "dataset_id": result.dataset_id,
            "dataset_item_id": result.dataset_item_id,
            "annotation_config_id": result.annotation_config_id,
            "value_json": result.value.model_dump(exclude_none=True),
            "annotator_id": result.annotator_id,
            "annotator_name": result.annotator_name,
            "created_at": result.created_at,
            "updated_at": result.updated_at,
            "duration_seconds": result.duration_seconds,
            "confidence": result.confidence,
            "notes": result.notes,
            "custom_fields_json": result.custom_fields,
        }
        if result.id is not None:
            model_data["id"] = result.id

        return cls(**model_data)

    def to_pydantic(self) -> AnnotationResult:
        """转换为 Pydantic 模型"""
        # 从 JSON 重建 AnnotationValue
        value = AnnotationValue(**self.value_json)

        return AnnotationResult(
            id=self.id,
            dataset_id=self.dataset_id,
            dataset_item_id=self.dataset_item_id,
            annotation_config_id=self.annotation_config_id,
            value=value,
            annotator_id=self.annotator_id,
            annotator_name=self.annotator_name,
            created_at=self.created_at,
            updated_at=self.updated_at,
            duration_seconds=self.duration_seconds,
            confidence=self.confidence,
            notes=self.notes,
            custom_fields=self.custom_fields_json,
        )


class ProjectModel(Base):
    """项目数据库模型"""

    __tablename__ = "projects"

    # 主键（自增）
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)

    # 基本信息
    name = Column(String, nullable=False, index=True)
    description = Column(Text, nullable=True)

    # 版本和状态
    version = Column(String, nullable=True, index=True)
    status = Column(String, nullable=True, default="active", index=True)

    # 标签和分类
    tags_json = Column(JSON, nullable=True, comment="标签列表（JSON序列化）")
    category = Column(String, nullable=True, index=True)

    # 创建者信息
    creator = Column(String, nullable=True)
    creator_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # 数据来源
    source = Column(String, nullable=True)
    source_url = Column(Text, nullable=True)

    # 元数据
    metadata_json = Column(JSON, nullable=True, comment="额外的元数据（JSON格式）")

    # 要显示的extra字段配置（JSON序列化，数据集可继承）
    display_extra_fields_json = Column(
        JSON, nullable=True, comment="要显示的extra字段列表（JSON序列化，数据集可继承）"
    )

    # 时间戳
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.now, onupdate=datetime.now, nullable=False
    )

    # 关系：项目可以关联到多个标注配置
    annotation_configs = relationship(
        "AnnotationConfigModel",
        secondary=project_annotation_config_association,
        back_populates="projects",
    )
    # 关系：项目由某个用户创建
    creator_user = relationship(
        "UserModel", foreign_keys=[creator_id], backref="created_projects"
    )
    # 关系：项目包含多个数据集
    datasets = relationship("DatasetModel", back_populates="project")

    @classmethod
    def from_pydantic(cls, project: Project) -> "ProjectModel":
        """从 Pydantic 模型创建数据库模型"""
        # 创建时如果提供了 id 则使用，否则让数据库自动生成
        model_data = {
            "name": project.name,
            "description": project.description,
            "version": project.version,
            "status": project.status,
            "tags_json": project.tags,
            "category": project.category,
            "creator": project.creator,
            "creator_id": project.creator_id,
            "source": project.source,
            "source_url": project.source_url,
            "metadata_json": project.metadata,
            "display_extra_fields_json": project.display_extra_fields,
        }
        if project.id is not None:
            model_data["id"] = project.id
        if project.created_at is not None:
            model_data["created_at"] = project.created_at
        if project.updated_at is not None:
            model_data["updated_at"] = project.updated_at

        return cls(**model_data)

    def to_pydantic(self) -> Project:
        """转换为 Pydantic 模型"""
        return Project(
            id=self.id,
            name=self.name,
            description=self.description,
            version=self.version,
            status=self.status,
            tags=self.tags_json,
            category=self.category,
            creator=self.creator,
            creator_id=self.creator_id,
            source=self.source,
            source_url=self.source_url,
            metadata=self.metadata_json,
            display_extra_fields=self.display_extra_fields_json,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )


class DatasetModel(Base):
    """数据集数据库模型"""

    __tablename__ = "datasets"

    # 主键（自增）
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)

    # 基本信息
    name = Column(String, nullable=False, index=True)
    description = Column(Text, nullable=True)

    # 版本和状态
    version = Column(String, nullable=True, index=True)
    status = Column(String, nullable=True, default="active", index=True)

    # 标签和分类
    tags_json = Column(JSON, nullable=True, comment="标签列表（JSON序列化）")
    category = Column(String, nullable=True, index=True)

    # 创建者信息
    creator = Column(String, nullable=True)
    creator_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # 标注者信息
    annotator_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    annotator_name = Column(String, nullable=True)

    # 数据来源
    source = Column(String, nullable=True)
    source_url = Column(Text, nullable=True)

    # 元数据
    metadata_json = Column(JSON, nullable=True, comment="额外的元数据（JSON格式）")

    # 要显示的extra字段配置（JSON序列化）
    display_extra_fields_json = Column(
        JSON, nullable=True, comment="要显示的extra字段列表（JSON序列化）"
    )

    # 外键：所属项目（可选）
    project_id = Column(
        Integer,
        ForeignKey("projects.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # 时间戳
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.now, onupdate=datetime.now, nullable=False
    )

    # 关系：数据集可以关联到多个标注配置
    annotation_configs = relationship(
        "AnnotationConfigModel",
        secondary=dataset_annotation_config_association,
        back_populates="datasets",
    )
    # 关系：数据集由某个用户创建
    creator_user = relationship(
        "UserModel", foreign_keys=[creator_id], backref="created_datasets"
    )
    # 关系：数据集由某个用户标注
    annotator_user = relationship(
        "UserModel", foreign_keys=[annotator_id], backref="annotated_datasets"
    )
    # 关系：数据集属于一个项目（可选）
    project = relationship("ProjectModel", back_populates="datasets")

    @classmethod
    def from_pydantic(cls, dataset: Dataset) -> "DatasetModel":
        """从 Pydantic 模型创建数据库模型"""
        # 创建时如果提供了 id 则使用，否则让数据库自动生成
        model_data = {
            "name": dataset.name,
            "description": dataset.description,
            "version": dataset.version,
            "status": dataset.status,
            "tags_json": dataset.tags,
            "category": dataset.category,
            "creator": dataset.creator,
            "creator_id": dataset.creator_id,
            "annotator_id": dataset.annotator_id,
            "annotator_name": dataset.annotator_name,
            "source": dataset.source,
            "source_url": dataset.source_url,
            "metadata_json": dataset.metadata,
            "display_extra_fields_json": dataset.display_extra_fields,
        }
        # 处理project_id
        if dataset.project_id is not None:
            model_data["project_id"] = dataset.project_id
        if dataset.id is not None:
            model_data["id"] = dataset.id
        if dataset.created_at is not None:
            model_data["created_at"] = dataset.created_at
        if dataset.updated_at is not None:
            model_data["updated_at"] = dataset.updated_at

        return cls(**model_data)

    def to_pydantic(self) -> Dataset:
        """转换为 Pydantic 模型"""
        return Dataset(
            id=self.id,
            name=self.name,
            description=self.description,
            version=self.version,
            status=self.status,
            tags=self.tags_json,
            category=self.category,
            creator=self.creator,
            creator_id=self.creator_id,
            annotator_id=self.annotator_id,
            annotator_name=self.annotator_name,
            source=self.source,
            source_url=self.source_url,
            metadata=self.metadata_json,
            display_extra_fields=self.display_extra_fields_json,
            project_id=self.project_id,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )


class QAPairModel(Base):
    """QA对数据库模型"""

    __tablename__ = "qa_pairs"

    # 主键（自增）
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)

    # 外键：所属数据集
    dataset_id = Column(
        Integer,
        ForeignKey("datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # QA 对内容
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)

    # 额外字段（JSON 序列化，用于存储 QAPair 的 extra 字段）
    extra_fields_json = Column(JSON, nullable=True)

    # 时间戳
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.now, onupdate=datetime.now, nullable=False
    )

    # 关系：QA 对属于一个数据集
    dataset = relationship("DatasetModel", passive_deletes=True)

    @classmethod
    def from_pydantic(cls, qa_pair: QAPair) -> "QAPairModel":
        """从 Pydantic 模型创建数据库模型"""
        # 提取额外字段（除了 id, dataset_id, question, answer 之外的所有字段）
        extra_fields = {}
        for key, value in qa_pair.model_dump().items():
            if key not in ["id", "dataset_id", "question", "answer"]:
                extra_fields[key] = value

        # 创建时如果提供了 id 则使用，否则让数据库自动生成
        model_data = {
            "dataset_id": qa_pair.dataset_id,
            "question": qa_pair.question,
            "answer": qa_pair.answer,
            "extra_fields_json": extra_fields if extra_fields else None,
        }
        if qa_pair.id is not None:
            model_data["id"] = qa_pair.id

        return cls(**model_data)

    def to_pydantic(self) -> QAPair:
        """转换为 Pydantic 模型"""
        # 构建基础字段
        data = {
            "id": self.id,
            "dataset_id": self.dataset_id,
            "question": self.question,
            "answer": self.answer,
        }

        # 添加额外字段
        if self.extra_fields_json:
            data.update(self.extra_fields_json)

        return QAPair(**data)


class UserModel(Base):
    """用户数据库模型"""

    __tablename__ = "users"

    # 主键（自增）
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)

    # 基本信息
    username = Column(String, nullable=False, unique=True, index=True)
    full_name = Column(String, nullable=True)
    organization = Column(String, nullable=True)
    team = Column(String, nullable=True)
    species = Column(String, nullable=True)

    # 密码（应该存储哈希值，而不是明文）
    hashed_password = Column(String, nullable=False)

    # 状态和权限
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    is_superuser = Column(Boolean, default=False, nullable=False)

    # 时间戳
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.now, onupdate=datetime.now, nullable=False
    )

    @classmethod
    def from_pydantic(cls, user: UserCreate) -> "UserModel":
        """从 Pydantic 模型创建数据库模型"""
        # 前端已经对密码进行了SHA-256哈希，这里直接存储
        # 注意：user.password 此时已经是SHA-256哈希值
        model_data = {
            "username": user.username,
            "full_name": user.full_name,
            "organization": user.organization,
            "team": user.team,
            "species": user.species,
            "hashed_password": user.password,  # 存储SHA-256哈希值
            "is_active": user.is_active,
            "is_superuser": user.is_superuser,
        }

        return cls(**model_data)

    def update_from_pydantic(self, user_update: UserUpdate) -> "UserModel":
        """从 Pydantic 更新模型更新数据库模型"""
        if user_update.username is not None:
            self.username = user_update.username
        if user_update.full_name is not None:
            self.full_name = user_update.full_name
        if user_update.organization is not None:
            self.organization = user_update.organization
        if user_update.team is not None:
            self.team = user_update.team
        if user_update.species is not None:
            self.species = user_update.species
        if user_update.password is not None:
            # 前端已经对密码进行了SHA-256哈希，这里直接存储
            # 注意：user_update.password 此时已经是SHA-256哈希值
            self.hashed_password = user_update.password
        if user_update.is_active is not None:
            self.is_active = user_update.is_active
        if user_update.is_superuser is not None:
            self.is_superuser = user_update.is_superuser

        return self

    def to_pydantic(self) -> User:
        """转换为 Pydantic 模型"""
        return User(
            id=self.id,
            username=self.username,
            full_name=self.full_name,
            organization=self.organization,
            team=self.team,
            species=self.species,
            is_active=self.is_active,
            is_superuser=self.is_superuser,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )


class QuestionTypeModel(Base):
    """问题类型数据库模型"""

    __tablename__ = "question_types"

    # 主键（自增）
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)

    # 类型和亚类
    type = Column(String, nullable=False, index=True)
    subtype = Column(String, nullable=False, index=True)

    # 显示顺序
    order = Column(Integer, default=0, nullable=False)

    # 时间戳
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.now, onupdate=datetime.now, nullable=False
    )

    @classmethod
    def from_pydantic(cls, question_type: QuestionTypeCreate) -> "QuestionTypeModel":
        """从 Pydantic 模型创建数据库模型"""
        model_data = {
            "type": question_type.type,
            "subtype": question_type.subtype,
            "order": question_type.order or 0,
        }
        return cls(**model_data)

    def to_pydantic(self) -> QuestionType:
        """转换为 Pydantic 模型"""
        return QuestionType(
            id=self.id,
            type=self.type,
            subtype=self.subtype,
            order=self.order,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )


class SeedQuestionModel(Base):
    """种子问题数据库模型"""

    __tablename__ = "seed_questions"

    # 主键（自增）
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)

    # 种子问题内容
    question = Column(Text, nullable=False)

    # 类型和亚类
    type = Column(String, nullable=False, index=True)
    subtype = Column(String, nullable=False, index=True)

    # 其他字段
    species_or_domain = Column(String, nullable=True)
    model = Column(String, nullable=True)
    date = Column(Date, nullable=True)
    is_verified = Column(Boolean, default=False, nullable=False)

    # 创建者信息
    creator_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=False,
        index=True,
    )

    # 时间戳
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.now, onupdate=datetime.now, nullable=False
    )

    # 关系：种子问题由某个用户创建
    creator = relationship(
        "UserModel", foreign_keys=[creator_id], backref="seed_questions"
    )

    @classmethod
    def from_pydantic(
        cls, seed_question: SeedQuestionCreate, creator_id: int
    ) -> "SeedQuestionModel":
        """从 Pydantic 模型创建数据库模型"""
        model_data = {
            "question": seed_question.question,
            "type": seed_question.type,
            "subtype": seed_question.subtype,
            "species_or_domain": seed_question.species_or_domain,
            "model": seed_question.model,
            "date": seed_question.date,
            "is_verified": seed_question.is_verified,
            "creator_id": creator_id,
        }
        return cls(**model_data)

    def to_pydantic(self) -> SeedQuestion:
        """转换为 Pydantic 模型"""
        return SeedQuestion(
            id=self.id,
            question=self.question,
            type=self.type,
            subtype=self.subtype,
            species_or_domain=self.species_or_domain,
            model=self.model,
            date=self.date,
            is_verified=self.is_verified,
            creator_id=self.creator_id,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )


class SystemConfigModel(Base):
    """系统配置数据库模型"""

    __tablename__ = "system_configs"

    # 主键（自增）
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)

    # 配置键（唯一）
    key = Column(String, unique=True, nullable=False, index=True)

    # 配置值（JSON格式存储）
    value = Column(Text, nullable=False)

    # 配置描述
    description = Column(Text, nullable=True)

    # 时间戳
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.now, onupdate=datetime.now, nullable=False
    )


class LlmAnalysisCacheModel(Base):
    """LLM 分析报告缓存数据库模型"""

    __tablename__ = "llm_analysis_cache"

    # 主键（自增）
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)

    # 关联项目
    project_id = Column(Integer, nullable=False, index=True)

    # 分析报告内容（Markdown）
    analysis_text = Column(Text, nullable=False)

    # 使用的模型名称
    model_name = Column(String, nullable=False)

    # 分析的备注数量
    notes_count = Column(Integer, nullable=False)

    # 报告语言
    language = Column(String, default="zh", nullable=False)

    # 时间戳
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.now, onupdate=datetime.now, nullable=False
    )
