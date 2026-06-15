"""数据库 CRUD 操作接口"""

from datetime import datetime
from typing import List, Optional

from sqlalchemy import and_, select, update
from sqlalchemy.orm import Session

from qa_annotate.database.models import (
    AnnotationConfigModel,
    AnnotationResultModel,
    DatasetModel,
    LlmAnalysisCacheModel,
    ProjectModel,
    QAPairModel,
    QuestionTypeModel,
    SeedQuestionModel,
    SystemConfigModel,
    UserModel,
)
from qa_annotate.schema.annotation import AnnotationConfig, AnnotationResult
from qa_annotate.schema.dataset import Dataset, QAPair
from qa_annotate.schema.project import Project
from qa_annotate.schema.question_type import (
    QuestionType,
    QuestionTypeCreate,
    QuestionTypeUpdate,
)
from qa_annotate.schema.seed_question import (
    SeedQuestion,
    SeedQuestionCreate,
    SeedQuestionUpdate,
    SeedQuestionWithCreator,
)
from qa_annotate.schema.system_config import SystemConfig, SystemConfigUpdate
from qa_annotate.schema.user import User, UserCreate, UserUpdate

# ==================== AnnotationConfig CRUD ====================


class AnnotationConfigCRUD:
    """标注配置 CRUD 操作"""

    @staticmethod
    def create(db: Session, config: AnnotationConfig) -> AnnotationConfig:
        """创建标注配置"""
        db_model = AnnotationConfigModel.from_pydantic(config)
        db.add(db_model)
        db.commit()
        db.refresh(db_model)
        return db_model.to_pydantic()

    @staticmethod
    def get_by_id(db: Session, config_id: int) -> Optional[AnnotationConfig]:
        """根据 ID 获取标注配置"""
        db_model = (
            db.query(AnnotationConfigModel)
            .filter(AnnotationConfigModel.id == config_id)
            .first()
        )
        return db_model.to_pydantic() if db_model else None

    @staticmethod
    def get_all(
        db: Session,
        skip: int = 0,
        limit: int = 100,
        annotation_type: Optional[str] = None,
    ) -> List[AnnotationConfig]:
        """获取所有标注配置（支持分页和过滤）"""
        query = db.query(AnnotationConfigModel)

        # 按类型过滤
        if annotation_type:
            query = query.filter(
                AnnotationConfigModel.annotation_type == annotation_type
            )

        results = query.offset(skip).limit(limit).all()
        return [model.to_pydantic() for model in results]

    @staticmethod
    def update(
        db: Session, config_id: int, config: AnnotationConfig
    ) -> Optional[AnnotationConfig]:
        """更新标注配置"""
        db_model = (
            db.query(AnnotationConfigModel)
            .filter(AnnotationConfigModel.id == config_id)
            .first()
        )

        if not db_model:
            return None

        # 更新字段
        # 处理 annotation_type：可能是枚举或字符串
        if isinstance(config.annotation_type, str):
            annotation_type_value = config.annotation_type
        else:
            annotation_type_value = config.annotation_type.value

        db_model.name = config.name
        db_model.description = config.description
        db_model.required = config.required
        db_model.show_reason = config.show_reason
        db_model.show_confidence = config.show_confidence
        db_model.annotation_type = annotation_type_value
        db_model.config_json = config.config.model_dump()
        db_model.custom_fields_json = config.custom_fields
        db_model.updated_at = datetime.now()

        db.commit()
        db.refresh(db_model)
        return db_model.to_pydantic()

    @staticmethod
    def delete(db: Session, config_id: int) -> bool:
        """删除标注配置（硬删除）"""
        db_model = (
            db.query(AnnotationConfigModel)
            .filter(AnnotationConfigModel.id == config_id)
            .first()
        )

        if not db_model:
            return False

        # 硬删除
        db.delete(db_model)
        db.commit()
        return True

    @staticmethod
    def count(db: Session) -> int:
        """获取标注配置总数"""
        return db.query(AnnotationConfigModel).count()


# ==================== AnnotationResult CRUD ====================


class AnnotationResultCRUD:
    """标注结果 CRUD 操作"""

    @staticmethod
    def create(db: Session, result: AnnotationResult) -> AnnotationResult:
        """创建标注结果"""
        db_model = AnnotationResultModel.from_pydantic(result)
        db.add(db_model)
        db.commit()
        db.refresh(db_model)
        return db_model.to_pydantic()

    @staticmethod
    def get_by_id(db: Session, result_id: int) -> Optional[AnnotationResult]:
        """根据 ID 获取标注结果"""
        db_model = (
            db.query(AnnotationResultModel)
            .filter(AnnotationResultModel.id == result_id)
            .first()
        )
        return db_model.to_pydantic() if db_model else None

    @staticmethod
    def get_all(
        db: Session,
        skip: int = 0,
        limit: int = 100,
        dataset_id: Optional[int] = None,
        dataset_item_id: Optional[int] = None,
        annotation_config_id: Optional[int] = None,
        annotator_id: Optional[int] = None,
    ) -> List[AnnotationResult]:
        """获取所有标注结果（支持分页和过滤）"""
        query = db.query(AnnotationResultModel)

        if dataset_id:
            query = query.filter(AnnotationResultModel.dataset_id == dataset_id)

        if dataset_item_id:
            query = query.filter(
                AnnotationResultModel.dataset_item_id == dataset_item_id
            )

        if annotation_config_id:
            query = query.filter(
                AnnotationResultModel.annotation_config_id == annotation_config_id
            )

        if annotator_id:
            query = query.filter(AnnotationResultModel.annotator_id == annotator_id)

        results = query.offset(skip).limit(limit).all()
        return [model.to_pydantic() for model in results]

    @staticmethod
    def get_by_dataset_item(
        db: Session,
        dataset_id: int,
        dataset_item_id: int,
    ) -> List[AnnotationResult]:
        """获取指定数据集项的所有标注结果"""
        db_models = (
            db.query(AnnotationResultModel)
            .filter(
                and_(
                    AnnotationResultModel.dataset_id == dataset_id,
                    AnnotationResultModel.dataset_item_id == dataset_item_id,
                )
            )
            .all()
        )
        return [model.to_pydantic() for model in db_models]

    @staticmethod
    def update(
        db: Session, result_id: int, result: AnnotationResult
    ) -> Optional[AnnotationResult]:
        """更新标注结果"""
        db_model = (
            db.query(AnnotationResultModel)
            .filter(AnnotationResultModel.id == result_id)
            .first()
        )

        if not db_model:
            return None

        # 更新字段
        db_model.dataset_id = result.dataset_id
        db_model.dataset_item_id = result.dataset_item_id
        db_model.annotation_config_id = result.annotation_config_id
        db_model.value_json = result.value.model_dump(exclude_none=True)
        db_model.annotator_id = result.annotator_id
        db_model.annotator_name = result.annotator_name
        db_model.duration_seconds = result.duration_seconds
        db_model.confidence = result.confidence
        db_model.notes = result.notes
        db_model.custom_fields_json = result.custom_fields
        db_model.updated_at = datetime.now()

        db.commit()
        db.refresh(db_model)
        return db_model.to_pydantic()

    @staticmethod
    def delete(db: Session, result_id: int) -> bool:
        """删除标注结果"""
        db_model = (
            db.query(AnnotationResultModel)
            .filter(AnnotationResultModel.id == result_id)
            .first()
        )

        if not db_model:
            return False

        db.delete(db_model)
        db.commit()
        return True

    @staticmethod
    def delete_by_dataset_item(
        db: Session,
        dataset_id: int,
        dataset_item_id: int,
    ) -> int:
        """删除指定数据集项的所有标注结果，返回删除的数量"""
        count = (
            db.query(AnnotationResultModel)
            .filter(
                and_(
                    AnnotationResultModel.dataset_id == dataset_id,
                    AnnotationResultModel.dataset_item_id == dataset_item_id,
                )
            )
            .delete()
        )
        db.commit()
        return count

    @staticmethod
    def delete_by_config(
        db: Session,
        annotation_config_id: int,
    ) -> int:
        """删除指定标注配置的所有标注结果，返回删除的数量"""
        count = (
            db.query(AnnotationResultModel)
            .filter(AnnotationResultModel.annotation_config_id == annotation_config_id)
            .delete()
        )
        db.commit()
        return count

    @staticmethod
    def count(
        db: Session,
        dataset_id: Optional[int] = None,
        annotation_config_id: Optional[int] = None,
    ) -> int:
        """获取标注结果总数（支持过滤）"""
        query = db.query(AnnotationResultModel)

        if dataset_id:
            query = query.filter(AnnotationResultModel.dataset_id == dataset_id)

        if annotation_config_id:
            query = query.filter(
                AnnotationResultModel.annotation_config_id == annotation_config_id
            )

        return query.count()


# ==================== Dataset CRUD ====================


class DatasetCRUD:
    """数据集 CRUD 操作"""

    @staticmethod
    def create(db: Session, dataset: Dataset) -> Dataset:
        """创建数据集"""
        db_model = DatasetModel.from_pydantic(dataset)
        db.add(db_model)
        db.commit()
        db.refresh(db_model)
        return db_model.to_pydantic()

    @staticmethod
    def get_by_id(db: Session, dataset_id: int) -> Optional[Dataset]:
        """根据 ID 获取数据集"""
        db_model = db.query(DatasetModel).filter(DatasetModel.id == dataset_id).first()
        return db_model.to_pydantic() if db_model else None

    @staticmethod
    def get_by_name(db: Session, name: str) -> Optional[Dataset]:
        """根据名称获取数据集"""
        db_model = db.query(DatasetModel).filter(DatasetModel.name == name).first()
        return db_model.to_pydantic() if db_model else None

    @staticmethod
    def get_all(
        db: Session,
        skip: int = 0,
        limit: int = 100,
        name_search: Optional[str] = None,
    ) -> List[Dataset]:
        """获取所有数据集（支持分页和名称搜索）"""
        query = db.query(DatasetModel)

        if name_search:
            query = query.filter(DatasetModel.name.contains(name_search))

        results = query.offset(skip).limit(limit).all()
        return [model.to_pydantic() for model in results]

    @staticmethod
    def update(db: Session, dataset_id: int, dataset: Dataset) -> Optional[Dataset]:
        """更新数据集"""
        db_model = db.query(DatasetModel).filter(DatasetModel.id == dataset_id).first()

        if not db_model:
            return None

        # 更新基本信息
        db_model.name = dataset.name
        db_model.description = dataset.description
        db_model.version = dataset.version
        db_model.status = dataset.status
        db_model.tags_json = dataset.tags
        db_model.category = dataset.category
        db_model.creator = dataset.creator
        db_model.creator_id = dataset.creator_id
        db_model.annotator_id = dataset.annotator_id
        db_model.annotator_name = dataset.annotator_name
        db_model.source = dataset.source
        db_model.source_url = dataset.source_url
        db_model.metadata_json = dataset.metadata
        db_model.display_extra_fields_json = dataset.display_extra_fields
        db_model.updated_at = datetime.now()

        db.commit()
        db.refresh(db_model)
        return db_model.to_pydantic()

    @staticmethod
    def delete(db: Session, dataset_id: int) -> bool:
        """删除数据集（级联删除所有 QA 对）"""
        db_model = db.query(DatasetModel).filter(DatasetModel.id == dataset_id).first()

        if not db_model:
            return False

        db.delete(db_model)
        db.commit()
        return True

    @staticmethod
    def claim_dataset(
        db: Session,
        dataset_id: int,
        annotator_id: int,
        annotator_name: str,
    ) -> Optional[Dataset]:
        """原子性地领取任务（将数据集分配给指定用户）

        使用原子更新操作，确保并发安全：
        - 只有当 annotator_id 为 None 时才会更新
        - 如果更新成功，返回更新后的数据集
        - 如果更新失败（已被其他用户领取），返回 None

        Args:
            db: 数据库会话
            dataset_id: 数据集 ID
            annotator_id: 标注者用户 ID
            annotator_name: 标注者用户名

        Returns:
            更新后的数据集对象，如果领取失败则返回 None
        """
        # 使用原子更新：只有当 annotator_id 为 None 时才更新
        stmt = (
            update(DatasetModel)
            .where(
                and_(
                    DatasetModel.id == dataset_id,
                    DatasetModel.annotator_id.is_(None),
                )
            )
            .values(
                annotator_id=annotator_id,
                annotator_name=annotator_name,
                updated_at=datetime.now(),
            )
        )

        result = db.execute(stmt)
        db.commit()

        # 如果更新影响的行数为 0，说明已经被其他用户领取或不存在
        if result.rowcount == 0:
            return None

        # 刷新并返回更新后的数据集
        db_model = db.query(DatasetModel).filter(DatasetModel.id == dataset_id).first()
        if db_model:
            db.refresh(db_model)
            return db_model.to_pydantic()
        return None

    @staticmethod
    def release_dataset(
        db: Session,
        dataset_id: int,
        annotator_id: int,
    ) -> Optional[Dataset]:
        """原子性地退回任务（将数据集从指定用户释放）

        使用原子更新操作，确保并发安全：
        - 只有当 annotator_id 匹配时才会更新
        - 如果更新成功，返回更新后的数据集
        - 如果更新失败（不属于该用户或不存在），返回 None

        Args:
            db: 数据库会话
            dataset_id: 数据集 ID
            annotator_id: 标注者用户 ID（用于验证任务是否属于该用户）

        Returns:
            更新后的数据集对象，如果退回失败则返回 None
        """
        # 使用原子更新：只有当 annotator_id 匹配时才更新
        stmt = (
            update(DatasetModel)
            .where(
                and_(
                    DatasetModel.id == dataset_id,
                    DatasetModel.annotator_id == annotator_id,
                )
            )
            .values(
                annotator_id=None,
                annotator_name=None,
                updated_at=datetime.now(),
            )
        )

        result = db.execute(stmt)
        db.commit()

        # 如果更新影响的行数为 0，说明不属于该用户或不存在
        if result.rowcount == 0:
            return None

        # 刷新并返回更新后的数据集
        db_model = db.query(DatasetModel).filter(DatasetModel.id == dataset_id).first()
        if db_model:
            db.refresh(db_model)
            return db_model.to_pydantic()
        return None

    @staticmethod
    def count(db: Session) -> int:
        """获取数据集总数"""
        return db.query(DatasetModel).count()

    @staticmethod
    def get_items_count(db: Session, dataset_id: int) -> int:
        """获取指定数据集的 QA 对数量"""
        return (
            db.query(QAPairModel).filter(QAPairModel.dataset_id == dataset_id).count()
        )

    @staticmethod
    def get_available_datasets(
        db: Session,
        skip: int = 0,
        limit: int = 100,
        user_species: Optional[str] = None,
    ) -> List[Dataset]:
        """获取可领取的数据集列表

        规则：
        1. 只返回 annotator_id 为空的数据集
        2. 如果用户有 species：
           - 返回匹配用户 species 的数据集（category == user_species）
           - 或没有 category 的数据集（category 为 None）
        3. 如果用户没有 species：
           - 只返回没有 category 的数据集（category 为 None）
           - 排除有 category 的数据集，因为用户无法领取它们

        Args:
            db: 数据库会话
            skip: 跳过数量
            limit: 返回数量限制
            user_species: 用户的物种标签（可选）

        Returns:
            可领取的数据集列表
        """
        from sqlalchemy import or_

        # 构建查询：只查询 annotator_id 为空的数据集
        query = db.query(DatasetModel).filter(DatasetModel.annotator_id.is_(None))

        # 构建过滤条件：
        # 1. 所有用户都可以领取没有 category 的数据集（category 为 None）
        # 2. 如果用户有 species，还可以领取匹配的数据集（category == user_species）
        conditions = [DatasetModel.category.is_(None)]
        if user_species:
            conditions.append(DatasetModel.category == user_species)

        query = query.filter(or_(*conditions))

        # 分页
        results = query.offset(skip).limit(limit).all()
        return [model.to_pydantic() for model in results]

    @staticmethod
    def get_by_annotator(
        db: Session,
        annotator_id: int,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Dataset]:
        """根据标注者ID获取数据集列表

        Args:
            db: 数据库会话
            annotator_id: 标注者ID
            skip: 跳过数量
            limit: 返回数量限制

        Returns:
            分配给指定标注者的数据集列表
        """
        query = db.query(DatasetModel).filter(DatasetModel.annotator_id == annotator_id)
        results = query.offset(skip).limit(limit).all()
        return [model.to_pydantic() for model in results]


# ==================== QAPair CRUD ====================


class QAPairCRUD:
    """QA对 CRUD 操作"""

    @staticmethod
    def create(db: Session, qa_pair: QAPair) -> QAPair:
        """创建 QA 对"""
        db_model = QAPairModel.from_pydantic(qa_pair)
        db.add(db_model)
        db.commit()
        db.refresh(db_model)
        return db_model.to_pydantic()

    @staticmethod
    def get_by_id(db: Session, qa_pair_id: int) -> Optional[QAPair]:
        """根据 ID 获取 QA 对"""
        db_model = db.query(QAPairModel).filter(QAPairModel.id == qa_pair_id).first()
        return db_model.to_pydantic() if db_model else None

    @staticmethod
    def get_by_dataset(
        db: Session,
        dataset_id: int,
        skip: int = 0,
        limit: int = 100,
    ) -> List[QAPair]:
        """获取指定数据集的所有 QA 对（支持分页）"""
        db_models = (
            db.query(QAPairModel)
            .filter(QAPairModel.dataset_id == dataset_id)
            .offset(skip)
            .limit(limit)
            .all()
        )
        return [model.to_pydantic() for model in db_models]

    @staticmethod
    def get_all(
        db: Session,
        skip: int = 0,
        limit: int = 100,
        dataset_id: Optional[int] = None,
        question_search: Optional[str] = None,
    ) -> List[QAPair]:
        """获取所有 QA 对（支持分页和过滤）"""
        query = db.query(QAPairModel)

        if dataset_id:
            query = query.filter(QAPairModel.dataset_id == dataset_id)

        if question_search:
            query = query.filter(QAPairModel.question.contains(question_search))

        results = query.offset(skip).limit(limit).all()
        return [model.to_pydantic() for model in results]

    @staticmethod
    def update(db: Session, qa_pair_id: int, qa_pair: QAPair) -> Optional[QAPair]:
        """更新 QA 对"""
        db_model = db.query(QAPairModel).filter(QAPairModel.id == qa_pair_id).first()

        if not db_model:
            return None

        # 更新字段
        db_model.dataset_id = qa_pair.dataset_id
        db_model.question = qa_pair.question
        db_model.answer = qa_pair.answer
        db_model.updated_at = datetime.now()

        # 更新额外字段
        extra_fields = {}
        for key, value in qa_pair.model_dump().items():
            if key not in ["id", "dataset_id", "question", "answer"]:
                extra_fields[key] = value
        db_model.extra_fields_json = extra_fields if extra_fields else None

        db.commit()
        db.refresh(db_model)
        return db_model.to_pydantic()

    @staticmethod
    def delete(db: Session, qa_pair_id: int) -> bool:
        """删除 QA 对"""
        db_model = db.query(QAPairModel).filter(QAPairModel.id == qa_pair_id).first()

        if not db_model:
            return False

        db.delete(db_model)
        db.commit()
        return True

    @staticmethod
    def delete_by_dataset(db: Session, dataset_id: int) -> int:
        """删除指定数据集的所有 QA 对，返回删除的数量"""
        count = (
            db.query(QAPairModel).filter(QAPairModel.dataset_id == dataset_id).delete()
        )
        db.commit()
        return count

    @staticmethod
    def count(
        db: Session,
        dataset_id: Optional[int] = None,
    ) -> int:
        """获取 QA 对总数（支持过滤）"""
        query = db.query(QAPairModel)

        if dataset_id:
            query = query.filter(QAPairModel.dataset_id == dataset_id)

        return query.count()


# ==================== Dataset-AnnotationConfig Association CRUD ====================


class DatasetAnnotationConfigCRUD:
    """数据集与标注配置关联 CRUD 操作"""

    @staticmethod
    def associate(
        db: Session,
        dataset_id: int,
        annotation_config_id: int,
    ) -> bool:
        """关联数据集和标注配置"""
        # 检查数据集是否存在
        dataset = db.query(DatasetModel).filter(DatasetModel.id == dataset_id).first()
        if not dataset:
            return False

        # 检查标注配置是否存在
        config = (
            db.query(AnnotationConfigModel)
            .filter(AnnotationConfigModel.id == annotation_config_id)
            .first()
        )
        if not config:
            return False

        # 检查是否已经关联
        if config in dataset.annotation_configs:
            return True  # 已经关联，返回成功

        # 添加关联
        dataset.annotation_configs.append(config)
        db.commit()
        return True

    @staticmethod
    def disassociate(
        db: Session,
        dataset_id: int,
        annotation_config_id: int,
    ) -> bool:
        """取消数据集和标注配置的关联"""
        dataset = db.query(DatasetModel).filter(DatasetModel.id == dataset_id).first()
        if not dataset:
            return False

        config = (
            db.query(AnnotationConfigModel)
            .filter(AnnotationConfigModel.id == annotation_config_id)
            .first()
        )
        if not config:
            return False

        # 移除关联
        if config in dataset.annotation_configs:
            dataset.annotation_configs.remove(config)
            db.commit()
            return True

        return False  # 本来就没有关联

    @staticmethod
    def get_datasets_by_config(
        db: Session,
        annotation_config_id: int,
    ) -> List[Dataset]:
        """获取使用指定标注配置的所有数据集"""
        config = (
            db.query(AnnotationConfigModel)
            .filter(AnnotationConfigModel.id == annotation_config_id)
            .first()
        )

        if not config:
            return []

        return [dataset.to_pydantic() for dataset in config.datasets]

    @staticmethod
    def get_configs_by_dataset(
        db: Session,
        dataset_id: int,
    ) -> List[AnnotationConfig]:
        """获取指定数据集关联的所有标注配置"""
        dataset = db.query(DatasetModel).filter(DatasetModel.id == dataset_id).first()

        if not dataset:
            return []

        return [config.to_pydantic() for config in dataset.annotation_configs]

    @staticmethod
    def set_dataset_configs(
        db: Session,
        dataset_id: int,
        annotation_config_ids: List[int],
    ) -> bool:
        """设置数据集关联的标注配置（会替换现有关联）"""
        dataset = db.query(DatasetModel).filter(DatasetModel.id == dataset_id).first()
        if not dataset:
            return False

        # 验证所有配置是否存在
        configs = (
            db.query(AnnotationConfigModel)
            .filter(AnnotationConfigModel.id.in_(annotation_config_ids))
            .all()
        )

        if len(configs) != len(annotation_config_ids):
            return False  # 有配置不存在

        # 替换关联
        dataset.annotation_configs = configs
        db.commit()
        return True

    @staticmethod
    def is_associated(
        db: Session,
        dataset_id: int,
        annotation_config_id: int,
    ) -> bool:
        """检查数据集和标注配置是否已关联"""
        dataset = db.query(DatasetModel).filter(DatasetModel.id == dataset_id).first()
        if not dataset:
            return False

        config = (
            db.query(AnnotationConfigModel)
            .filter(AnnotationConfigModel.id == annotation_config_id)
            .first()
        )
        if not config:
            return False

        return config in dataset.annotation_configs

    @staticmethod
    def count_configs_by_dataset(db: Session, dataset_id: int) -> int:
        """统计指定数据集关联的标注配置数量"""
        dataset = db.query(DatasetModel).filter(DatasetModel.id == dataset_id).first()
        if not dataset:
            return 0

        return len(dataset.annotation_configs)

    @staticmethod
    def count_datasets_by_config(db: Session, annotation_config_id: int) -> int:
        """统计使用指定标注配置的数据集数量"""
        config = (
            db.query(AnnotationConfigModel)
            .filter(AnnotationConfigModel.id == annotation_config_id)
            .first()
        )
        if not config:
            return 0

        return len(config.datasets)


# ==================== User CRUD ====================


class UserCRUD:
    """用户 CRUD 操作"""

    @staticmethod
    def create(db: Session, user: UserCreate) -> User:
        """创建用户"""
        db_model = UserModel.from_pydantic(user)
        db.add(db_model)
        db.commit()
        db.refresh(db_model)
        return db_model.to_pydantic()

    @staticmethod
    def get_by_id(db: Session, user_id: int) -> Optional[User]:
        """根据 ID 获取用户"""
        db_model = db.query(UserModel).filter(UserModel.id == user_id).first()
        return db_model.to_pydantic() if db_model else None

    @staticmethod
    def get_by_username(db: Session, username: str) -> Optional[User]:
        """根据用户名获取用户"""
        db_model = db.query(UserModel).filter(UserModel.username == username).first()
        return db_model.to_pydantic() if db_model else None

    @staticmethod
    def authenticate_user(
        db: Session, username: str, password_hash: str, timestamp: int
    ) -> Optional[User]:
        """验证用户密码（使用SHA-256哈希+时间戳）, 但不检查用户是否激活"""
        from qa_annotate.utils.password import verify_password_with_timestamp

        db_model = db.query(UserModel).filter(UserModel.username == username).first()

        if not db_model:
            return None

        # 验证密码哈希（带时间戳，防止重放攻击）
        if not verify_password_with_timestamp(
            password_hash, db_model.hashed_password, timestamp
        ):
            return None

        return db_model.to_pydantic()

    @staticmethod
    def get_all(
        db: Session,
        skip: int = 0,
        limit: int = 100,
        is_active: Optional[bool] = None,
    ) -> List[User]:
        """获取所有用户（支持分页和过滤）"""
        query = db.query(UserModel)

        if is_active is not None:
            query = query.filter(UserModel.is_active == is_active)

        results = query.offset(skip).limit(limit).all()
        return [model.to_pydantic() for model in results]

    @staticmethod
    def update(db: Session, user_id: int, user_update: UserUpdate) -> Optional[User]:
        """更新用户"""
        db_model = db.query(UserModel).filter(UserModel.id == user_id).first()

        if not db_model:
            return None

        db_model.update_from_pydantic(user_update)
        db_model.updated_at = datetime.now()

        db.commit()
        db.refresh(db_model)
        return db_model.to_pydantic()

    @staticmethod
    def delete(db: Session, user_id: int) -> bool:
        """删除用户"""
        db_model = db.query(UserModel).filter(UserModel.id == user_id).first()

        if not db_model:
            return False

        db.delete(db_model)
        db.commit()
        return True

    @staticmethod
    def count(db: Session, is_active: Optional[bool] = None) -> int:
        """获取用户总数（支持过滤）"""
        query = db.query(UserModel)

        if is_active is not None:
            query = query.filter(UserModel.is_active == is_active)

        return query.count()


# ==================== Project CRUD ====================


class ProjectCRUD:
    """项目 CRUD 操作"""

    @staticmethod
    def create(db: Session, project: Project) -> Project:
        """创建项目"""
        db_model = ProjectModel.from_pydantic(project)
        db.add(db_model)
        db.commit()
        db.refresh(db_model)
        return db_model.to_pydantic()

    @staticmethod
    def get_by_id(db: Session, project_id: int) -> Optional[Project]:
        """根据 ID 获取项目"""
        db_model = db.query(ProjectModel).filter(ProjectModel.id == project_id).first()
        return db_model.to_pydantic() if db_model else None

    @staticmethod
    def get_by_name(db: Session, name: str) -> Optional[Project]:
        """根据名称获取项目"""
        db_model = db.query(ProjectModel).filter(ProjectModel.name == name).first()
        return db_model.to_pydantic() if db_model else None

    @staticmethod
    def get_all(
        db: Session,
        skip: int = 0,
        limit: int = 100,
        name_search: Optional[str] = None,
        category: Optional[str] = None,
        status: Optional[str] = None,
        order_by: Optional[str] = "created_at",
        order: Optional[str] = "desc",
    ) -> List[Project]:
        """获取所有项目（支持分页、过滤和排序）"""
        query = db.query(ProjectModel)

        if name_search:
            query = query.filter(ProjectModel.name.contains(name_search))

        if category:
            query = query.filter(ProjectModel.category == category)

        if status:
            query = query.filter(ProjectModel.status == status)

        # 排序
        if order_by:
            # 支持的排序字段
            valid_order_fields = {
                "id": ProjectModel.id,
                "name": ProjectModel.name,
                "created_at": ProjectModel.created_at,
                "updated_at": ProjectModel.updated_at,
                "version": ProjectModel.version,
                "status": ProjectModel.status,
                "category": ProjectModel.category,
            }

            order_field = valid_order_fields.get(order_by.lower())
            if order_field:
                if order and order.lower() == "asc":
                    query = query.order_by(order_field.asc())
                else:
                    query = query.order_by(order_field.desc())
            else:
                # 默认按创建时间倒序
                query = query.order_by(ProjectModel.created_at.desc())
        else:
            # 默认按创建时间倒序
            query = query.order_by(ProjectModel.created_at.desc())

        results = query.offset(skip).limit(limit).all()
        return [model.to_pydantic() for model in results]

    @staticmethod
    def update(db: Session, project_id: int, project: Project) -> Optional[Project]:
        """更新项目"""
        db_model = db.query(ProjectModel).filter(ProjectModel.id == project_id).first()

        if not db_model:
            return None

        # 更新字段
        db_model.name = project.name
        db_model.description = project.description
        db_model.version = project.version
        db_model.status = project.status
        db_model.tags_json = project.tags
        db_model.category = project.category
        db_model.source = project.source
        db_model.source_url = project.source_url
        db_model.metadata_json = project.metadata
        db_model.display_extra_fields_json = project.display_extra_fields
        db_model.updated_at = datetime.now()

        db.commit()
        db.refresh(db_model)
        return db_model.to_pydantic()

    @staticmethod
    def delete(db: Session, project_id: int) -> bool:
        """删除项目（数据集的project_id会设为NULL）"""
        db_model = db.query(ProjectModel).filter(ProjectModel.id == project_id).first()

        if not db_model:
            return False

        db.delete(db_model)
        db.commit()
        return True

    @staticmethod
    def get_datasets_by_project(
        db: Session,
        project_id: int,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Dataset]:
        """获取项目下的所有数据集（支持分页）"""
        project = db.query(ProjectModel).filter(ProjectModel.id == project_id).first()
        if not project:
            return []

        datasets = project.datasets[skip : skip + limit]
        return [dataset.to_pydantic() for dataset in datasets]

    @staticmethod
    def add_dataset_to_project(
        db: Session,
        project_id: int,
        dataset_id: int,
    ) -> bool:
        """将数据集添加到项目"""
        project = db.query(ProjectModel).filter(ProjectModel.id == project_id).first()
        if not project:
            return False

        dataset = db.query(DatasetModel).filter(DatasetModel.id == dataset_id).first()
        if not dataset:
            return False

        dataset.project_id = project_id
        db.commit()
        return True

    @staticmethod
    def remove_dataset_from_project(
        db: Session,
        project_id: int,
        dataset_id: int,
    ) -> bool:
        """从项目移除数据集"""
        project = db.query(ProjectModel).filter(ProjectModel.id == project_id).first()
        if not project:
            return False

        dataset = db.query(DatasetModel).filter(DatasetModel.id == dataset_id).first()
        if not dataset:
            return False

        if dataset.project_id != project_id:
            return False  # 数据集不属于该项目

        dataset.project_id = None
        db.commit()
        return True

    @staticmethod
    def count(db: Session) -> int:
        """获取项目总数"""
        return db.query(ProjectModel).count()

    @staticmethod
    def count_datasets_by_project(db: Session, project_id: int) -> int:
        """获取指定项目下的数据集数量"""
        project = db.query(ProjectModel).filter(ProjectModel.id == project_id).first()
        if not project:
            return 0

        return len(project.datasets)


# ==================== Project-AnnotationConfig Association CRUD ====================


class ProjectAnnotationConfigCRUD:
    """项目与标注配置关联 CRUD 操作"""

    @staticmethod
    def associate(
        db: Session,
        project_id: int,
        annotation_config_id: int,
    ) -> bool:
        """关联项目和标注配置"""
        from qa_annotate.database.models import project_annotation_config_association

        # 检查项目是否存在
        project = db.query(ProjectModel).filter(ProjectModel.id == project_id).first()
        if not project:
            return False

        # 检查标注配置是否存在
        config = (
            db.query(AnnotationConfigModel)
            .filter(AnnotationConfigModel.id == annotation_config_id)
            .first()
        )
        if not config:
            return False

        # 检查是否已经关联
        if config in project.annotation_configs:
            return True  # 已经关联，返回成功

        # 获取当前项目的最大order值
        stmt = (
            select(project_annotation_config_association.c.order)
            .where(project_annotation_config_association.c.project_id == project_id)
            .order_by(project_annotation_config_association.c.order.desc())
            .limit(1)
        )
        result = db.execute(stmt).first()
        next_order = (result[0] + 1) if result else 0

        # 添加关联，使用insert方法设置order
        stmt = project_annotation_config_association.insert().values(
            project_id=project_id,
            annotation_config_id=annotation_config_id,
            order=next_order,
        )
        db.execute(stmt)
        db.commit()
        return True

    @staticmethod
    def disassociate(
        db: Session,
        project_id: int,
        annotation_config_id: int,
    ) -> bool:
        """取消项目和标注配置的关联"""
        project = db.query(ProjectModel).filter(ProjectModel.id == project_id).first()
        if not project:
            return False

        config = (
            db.query(AnnotationConfigModel)
            .filter(AnnotationConfigModel.id == annotation_config_id)
            .first()
        )
        if not config:
            return False

        # 移除关联
        if config in project.annotation_configs:
            project.annotation_configs.remove(config)
            db.commit()
            return True

        return False  # 本来就没有关联

    @staticmethod
    def get_projects_by_config(
        db: Session,
        annotation_config_id: int,
    ) -> List[Project]:
        """获取使用指定标注配置的所有项目"""
        config = (
            db.query(AnnotationConfigModel)
            .filter(AnnotationConfigModel.id == annotation_config_id)
            .first()
        )

        if not config:
            return []

        return [project.to_pydantic() for project in config.projects]

    @staticmethod
    def get_configs_by_project(
        db: Session,
        project_id: int,
    ) -> List[AnnotationConfig]:
        """获取指定项目关联的所有标注配置（按order排序）"""
        from qa_annotate.database.models import project_annotation_config_association

        project = db.query(ProjectModel).filter(ProjectModel.id == project_id).first()

        if not project:
            return []

        # 获取所有配置及其order值
        configs_with_order = []
        for config in project.annotation_configs:
            # 查询order值
            stmt = select(project_annotation_config_association.c.order).where(
                and_(
                    project_annotation_config_association.c.project_id == project_id,
                    project_annotation_config_association.c.annotation_config_id
                    == config.id,
                )
            )
            result = db.execute(stmt).first()
            order = result[0] if result else 0
            configs_with_order.append((order, config))

        # 按order排序
        configs_with_order.sort(key=lambda x: x[0])

        return [config.to_pydantic() for _, config in configs_with_order]

    @staticmethod
    def set_project_configs(
        db: Session,
        project_id: int,
        annotation_config_ids: List[int],
    ) -> bool:
        """设置项目关联的标注配置（会替换现有关联）"""
        project = db.query(ProjectModel).filter(ProjectModel.id == project_id).first()
        if not project:
            return False

        # 验证所有配置是否存在
        configs = (
            db.query(AnnotationConfigModel)
            .filter(AnnotationConfigModel.id.in_(annotation_config_ids))
            .all()
        )

        if len(configs) != len(annotation_config_ids):
            return False  # 有配置不存在

        # 替换关联
        project.annotation_configs = configs
        db.commit()
        return True

    @staticmethod
    def is_associated(
        db: Session,
        project_id: int,
        annotation_config_id: int,
    ) -> bool:
        """检查项目和标注配置是否已关联"""
        project = db.query(ProjectModel).filter(ProjectModel.id == project_id).first()
        if not project:
            return False

        config = (
            db.query(AnnotationConfigModel)
            .filter(AnnotationConfigModel.id == annotation_config_id)
            .first()
        )
        if not config:
            return False

        return config in project.annotation_configs

    @staticmethod
    def count_configs_by_project(db: Session, project_id: int) -> int:
        """统计指定项目关联的标注配置数量"""
        project = db.query(ProjectModel).filter(ProjectModel.id == project_id).first()
        if not project:
            return 0

        return len(project.annotation_configs)

    @staticmethod
    def count_projects_by_config(db: Session, annotation_config_id: int) -> int:
        """统计使用指定标注配置的项目数量"""
        config = (
            db.query(AnnotationConfigModel)
            .filter(AnnotationConfigModel.id == annotation_config_id)
            .first()
        )
        if not config:
            return 0

        return len(config.projects)

    @staticmethod
    def swap_config_order(
        db: Session,
        project_id: int,
        config_id1: int,
        config_id2: int,
    ) -> bool:
        """交换两个配置的顺序"""
        from qa_annotate.database.models import project_annotation_config_association

        # 获取两个配置的当前order
        stmt1 = select(project_annotation_config_association.c.order).where(
            and_(
                project_annotation_config_association.c.project_id == project_id,
                project_annotation_config_association.c.annotation_config_id
                == config_id1,
            )
        )
        result1 = db.execute(stmt1).first()

        stmt2 = select(project_annotation_config_association.c.order).where(
            and_(
                project_annotation_config_association.c.project_id == project_id,
                project_annotation_config_association.c.annotation_config_id
                == config_id2,
            )
        )
        result2 = db.execute(stmt2).first()

        if not result1 or not result2:
            return False

        # 交换order值
        order1 = result1[0]
        order2 = result2[0]

        stmt_update1 = (
            update(project_annotation_config_association)
            .where(
                and_(
                    project_annotation_config_association.c.project_id == project_id,
                    project_annotation_config_association.c.annotation_config_id
                    == config_id1,
                )
            )
            .values(order=order2)
        )

        stmt_update2 = (
            update(project_annotation_config_association)
            .where(
                and_(
                    project_annotation_config_association.c.project_id == project_id,
                    project_annotation_config_association.c.annotation_config_id
                    == config_id2,
                )
            )
            .values(order=order1)
        )

        db.execute(stmt_update1)
        db.execute(stmt_update2)
        db.commit()
        return True


# ==================== QuestionType CRUD ====================


class QuestionTypeCRUD:
    """问题类型 CRUD 操作"""

    @staticmethod
    def create(db: Session, question_type: QuestionTypeCreate) -> QuestionType:
        """创建问题类型"""
        db_model = QuestionTypeModel.from_pydantic(question_type)
        db.add(db_model)
        db.commit()
        db.refresh(db_model)
        return db_model.to_pydantic()

    @staticmethod
    def get_by_id(db: Session, type_id: int) -> Optional[QuestionType]:
        """根据 ID 获取问题类型"""
        db_model = (
            db.query(QuestionTypeModel).filter(QuestionTypeModel.id == type_id).first()
        )
        return db_model.to_pydantic() if db_model else None

    @staticmethod
    def get_by_type_subtype(
        db: Session, type: str, subtype: str
    ) -> Optional[QuestionType]:
        """根据类型和亚类获取问题类型"""
        db_model = (
            db.query(QuestionTypeModel)
            .filter(
                QuestionTypeModel.type == type,
                QuestionTypeModel.subtype == subtype,
            )
            .first()
        )
        return db_model.to_pydantic() if db_model else None

    @staticmethod
    def get_all(db: Session, skip: int = 0, limit: int = 1000) -> List[QuestionType]:
        """获取所有问题类型（支持分页）"""
        results = (
            db.query(QuestionTypeModel)
            .order_by(
                QuestionTypeModel.type,
                QuestionTypeModel.order,
                QuestionTypeModel.subtype,
            )
            .offset(skip)
            .limit(limit)
            .all()
        )
        return [model.to_pydantic() for model in results]

    @staticmethod
    def get_all_grouped(db: Session) -> dict:
        """获取所有问题类型，按类型分组"""
        results = (
            db.query(QuestionTypeModel)
            .order_by(
                QuestionTypeModel.type,
                QuestionTypeModel.order,
                QuestionTypeModel.subtype,
            )
            .all()
        )
        grouped = {}
        for model in results:
            type_name = model.type
            if type_name not in grouped:
                grouped[type_name] = []
            grouped[type_name].append(model.subtype)
        return grouped

    @staticmethod
    def update(
        db: Session, type_id: int, question_type_update: QuestionTypeUpdate
    ) -> Optional[QuestionType]:
        """更新问题类型"""
        db_model = (
            db.query(QuestionTypeModel).filter(QuestionTypeModel.id == type_id).first()
        )
        if not db_model:
            return None

        # 如果更新了类型或亚类，检查是否与现有记录冲突
        if (
            question_type_update.type is not None
            or question_type_update.subtype is not None
        ):
            new_type = (
                question_type_update.type
                if question_type_update.type is not None
                else db_model.type
            )
            new_subtype = (
                question_type_update.subtype
                if question_type_update.subtype is not None
                else db_model.subtype
            )

            # 检查是否存在其他记录有相同的类型和亚类
            existing = (
                db.query(QuestionTypeModel)
                .filter(
                    QuestionTypeModel.type == new_type,
                    QuestionTypeModel.subtype == new_subtype,
                    QuestionTypeModel.id != type_id,
                )
                .first()
            )
            if existing:
                return None

        if question_type_update.type is not None:
            db_model.type = question_type_update.type
        if question_type_update.subtype is not None:
            db_model.subtype = question_type_update.subtype
        if question_type_update.order is not None:
            db_model.order = question_type_update.order

        db.commit()
        db.refresh(db_model)
        return db_model.to_pydantic()

    @staticmethod
    def delete(db: Session, type_id: int) -> bool:
        """删除问题类型"""
        db_model = (
            db.query(QuestionTypeModel).filter(QuestionTypeModel.id == type_id).first()
        )

        if not db_model:
            return False

        db.delete(db_model)
        db.commit()
        return True

    @staticmethod
    def import_from_csv(db: Session, csv_path: str) -> dict:
        """从CSV文件导入类型/亚类数据"""
        import csv
        from pathlib import Path

        csv_file = Path(csv_path)
        if not csv_file.exists():
            raise FileNotFoundError(f"CSV文件不存在: {csv_path}")

        imported_count = 0
        skipped_count = 0
        errors = []
        current_type = None  # 用于跟踪当前类型（处理层级关系）

        with open(csv_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row_num, row in enumerate(
                reader, start=2
            ):  # 从第2行开始（第1行是标题）
                try:
                    type_name = row.get("类型", "").strip()
                    subtype_name = row.get("亚类", "").strip()

                    # 如果类型列有值，更新当前类型
                    if type_name:
                        current_type = type_name

                    # 如果类型或亚类为空，跳过
                    if not current_type or not subtype_name:
                        skipped_count += 1
                        continue

                    # 检查是否已存在
                    existing = QuestionTypeCRUD.get_by_type_subtype(
                        db, current_type, subtype_name
                    )
                    if existing:
                        skipped_count += 1
                        continue

                    # 创建新的类型/亚类
                    question_type = QuestionTypeCreate(
                        type=current_type, subtype=subtype_name, order=0
                    )
                    QuestionTypeCRUD.create(db, question_type)
                    imported_count += 1

                except Exception as e:
                    errors.append(f"第{row_num}行: {str(e)}")

        return {
            "imported_count": imported_count,
            "skipped_count": skipped_count,
            "errors": errors,
        }

    @staticmethod
    def count(db: Session) -> int:
        """获取问题类型总数"""
        return db.query(QuestionTypeModel).count()


# ==================== SeedQuestion CRUD ====================


class SeedQuestionCRUD:
    """种子问题 CRUD 操作"""

    @staticmethod
    def create(
        db: Session, seed_question: SeedQuestionCreate, creator_id: int
    ) -> SeedQuestion:
        """创建种子问题"""
        db_model = SeedQuestionModel.from_pydantic(seed_question, creator_id)
        db.add(db_model)
        db.commit()
        db.refresh(db_model)
        return db_model.to_pydantic()

    @staticmethod
    def get_by_id(db: Session, question_id: int) -> Optional[SeedQuestion]:
        """根据 ID 获取种子问题"""
        db_model = (
            db.query(SeedQuestionModel)
            .filter(SeedQuestionModel.id == question_id)
            .first()
        )
        return db_model.to_pydantic() if db_model else None

    @staticmethod
    def get_all(
        db: Session,
        skip: int = 0,
        limit: int = 100,
        creator_id: Optional[int] = None,
        type: Optional[str] = None,
        subtype: Optional[str] = None,
        search: Optional[str] = None,
    ) -> List[SeedQuestion]:
        """获取所有种子问题（支持分页和过滤）"""
        query = db.query(SeedQuestionModel)

        if creator_id is not None:
            query = query.filter(SeedQuestionModel.creator_id == creator_id)

        if type:
            query = query.filter(SeedQuestionModel.type == type)

        if subtype:
            query = query.filter(SeedQuestionModel.subtype == subtype)

        if search:
            query = query.filter(SeedQuestionModel.question.contains(search))

        results = (
            query.order_by(SeedQuestionModel.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )
        return [model.to_pydantic() for model in results]

    @staticmethod
    def get_all_with_creator(
        db: Session,
        skip: int = 0,
        limit: int = 100,
        creator_id: Optional[int] = None,
        type: Optional[str] = None,
        subtype: Optional[str] = None,
        search: Optional[str] = None,
    ) -> List[SeedQuestionWithCreator]:
        """获取所有种子问题（包含创建者全名，支持分页和过滤）"""
        query = db.query(SeedQuestionModel, UserModel.full_name).outerjoin(
            UserModel, SeedQuestionModel.creator_id == UserModel.id
        )

        if creator_id is not None:
            query = query.filter(SeedQuestionModel.creator_id == creator_id)

        if type:
            query = query.filter(SeedQuestionModel.type == type)

        if subtype:
            query = query.filter(SeedQuestionModel.subtype == subtype)

        if search:
            query = query.filter(SeedQuestionModel.question.contains(search))

        results = (
            query.order_by(SeedQuestionModel.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

        return [
            SeedQuestionWithCreator(
                id=model.id,
                question=model.question,
                type=model.type,
                subtype=model.subtype,
                species_or_domain=model.species_or_domain,
                model=model.model,
                date=model.date,
                is_verified=model.is_verified,
                creator_id=model.creator_id,
                creator_full_name=full_name,
                created_at=model.created_at,
                updated_at=model.updated_at,
            )
            for model, full_name in results
        ]

    @staticmethod
    def update(
        db: Session, question_id: int, seed_question: SeedQuestionUpdate
    ) -> Optional[SeedQuestion]:
        """更新种子问题"""
        db_model = (
            db.query(SeedQuestionModel)
            .filter(SeedQuestionModel.id == question_id)
            .first()
        )

        if not db_model:
            return None

        # 更新字段
        if seed_question.question is not None:
            db_model.question = seed_question.question
        if seed_question.type is not None:
            db_model.type = seed_question.type
        if seed_question.subtype is not None:
            db_model.subtype = seed_question.subtype
        if seed_question.species_or_domain is not None:
            db_model.species_or_domain = seed_question.species_or_domain
        if seed_question.model is not None:
            db_model.model = seed_question.model
        if seed_question.date is not None:
            db_model.date = seed_question.date
        if seed_question.is_verified is not None:
            db_model.is_verified = seed_question.is_verified

        db_model.updated_at = datetime.now()

        db.commit()
        db.refresh(db_model)
        return db_model.to_pydantic()

    @staticmethod
    def delete(db: Session, question_id: int) -> bool:
        """删除种子问题"""
        db_model = (
            db.query(SeedQuestionModel)
            .filter(SeedQuestionModel.id == question_id)
            .first()
        )

        if not db_model:
            return False

        db.delete(db_model)
        db.commit()
        return True

    @staticmethod
    def count(
        db: Session,
        creator_id: Optional[int] = None,
        type: Optional[str] = None,
        subtype: Optional[str] = None,
    ) -> int:
        """获取种子问题总数（支持过滤）"""
        query = db.query(SeedQuestionModel)

        if creator_id is not None:
            query = query.filter(SeedQuestionModel.creator_id == creator_id)

        if type:
            query = query.filter(SeedQuestionModel.type == type)

        if subtype:
            query = query.filter(SeedQuestionModel.subtype == subtype)

        return query.count()

    @staticmethod
    def export_all(db: Session) -> List[SeedQuestionWithCreator]:
        """导出所有种子问题（管理员用，包含创建者全名）"""
        results = (
            db.query(SeedQuestionModel, UserModel.full_name)
            .outerjoin(UserModel, SeedQuestionModel.creator_id == UserModel.id)
            .order_by(SeedQuestionModel.created_at.desc())
            .all()
        )

        return [
            SeedQuestionWithCreator(
                id=model.id,
                question=model.question,
                type=model.type,
                subtype=model.subtype,
                species_or_domain=model.species_or_domain,
                model=model.model,
                date=model.date,
                is_verified=model.is_verified,
                creator_id=model.creator_id,
                creator_full_name=full_name,
                created_at=model.created_at,
                updated_at=model.updated_at,
            )
            for model, full_name in results
        ]

    @staticmethod
    def create_batch(
        db: Session, seed_questions: List[SeedQuestionCreate], creator_id: int
    ) -> List[SeedQuestion]:
        """批量创建种子问题"""
        db_models = [
            SeedQuestionModel.from_pydantic(seed_question, creator_id)
            for seed_question in seed_questions
        ]
        db.add_all(db_models)
        db.commit()
        for db_model in db_models:
            db.refresh(db_model)
        return [model.to_pydantic() for model in db_models]


# ==================== SystemConfig CRUD ====================


class SystemConfigCRUD:
    """系统配置 CRUD 操作"""

    @staticmethod
    def get_by_key(db: Session, key: str) -> Optional[SystemConfig]:
        """根据键获取系统配置"""
        db_model = (
            db.query(SystemConfigModel).filter(SystemConfigModel.key == key).first()
        )
        if not db_model:
            return None
        return SystemConfig(
            id=db_model.id,
            key=db_model.key,
            value=db_model.value,
            description=db_model.description,
            created_at=db_model.created_at,
            updated_at=db_model.updated_at,
        )

    @staticmethod
    def get_value(db: Session, key: str, default: str = None) -> Optional[str]:
        """获取配置值（便捷方法）"""
        config = SystemConfigCRUD.get_by_key(db, key)
        if config:
            return config.value
        return default

    @staticmethod
    def set_value(
        db: Session, key: str, value: str, description: str = None
    ) -> SystemConfig:
        """设置配置值（如果不存在则创建，存在则更新）"""
        db_model = (
            db.query(SystemConfigModel).filter(SystemConfigModel.key == key).first()
        )
        if db_model:
            # 更新现有配置
            if value is not None:
                db_model.value = value
            if description is not None:
                db_model.description = description
            db_model.updated_at = datetime.now()
        else:
            # 创建新配置
            db_model = SystemConfigModel(
                key=key,
                value=value,
                description=description,
            )
            db.add(db_model)
        db.commit()
        db.refresh(db_model)
        return SystemConfig(
            id=db_model.id,
            key=db_model.key,
            value=db_model.value,
            description=db_model.description,
            created_at=db_model.created_at,
            updated_at=db_model.updated_at,
        )

    @staticmethod
    def update(
        db: Session, key: str, config_update: SystemConfigUpdate
    ) -> Optional[SystemConfig]:
        """更新系统配置"""
        db_model = (
            db.query(SystemConfigModel).filter(SystemConfigModel.key == key).first()
        )
        if not db_model:
            return None

        if config_update.value is not None:
            db_model.value = config_update.value
        if config_update.description is not None:
            db_model.description = config_update.description
        db_model.updated_at = datetime.now()

        db.commit()
        db.refresh(db_model)
        return SystemConfig(
            id=db_model.id,
            key=db_model.key,
            value=db_model.value,
            description=db_model.description,
            created_at=db_model.created_at,
            updated_at=db_model.updated_at,
        )

    @staticmethod
    def get_all(db: Session) -> List[SystemConfig]:
        """获取所有系统配置"""
        db_models = db.query(SystemConfigModel).all()
        return [
            SystemConfig(
                id=model.id,
                key=model.key,
                value=model.value,
                description=model.description,
                created_at=model.created_at,
                updated_at=model.updated_at,
            )
            for model in db_models
        ]


# ==================== AnnotationResult Analysis ====================


class AnnotationResultAnalysisCRUD:
    """标注结果分析 CRUD 操作"""

    @staticmethod
    def get_project_annotation_stats(
        db: Session, project_id: int
    ) -> dict:
        """获取项目的标注结果统计信息

        返回结构:
        {
            "total_datasets": int,
            "total_items": int,
            "total_annotations": int,
            "completion_rate": float,  # 完整标注率：完成所有配置标注的QA对占比
            "configs_stats": [
                {
                    "config_id": int,
                    "config_name": str,
                    "annotation_type": str,
                    "total_annotations": int,
                    "coverage": float,  # 覆盖率（有多少QA对被标注）
                    "stats": dict  # 按类型统计的数据
                }
            ],
            "notes_summary": [
                {
                    "config_name": str,
                    "notes": List[str],
                    "count": int
                }
            ]
        }
        """
        # 1. 获取项目下所有数据集
        project = db.query(ProjectModel).filter(ProjectModel.id == project_id).first()
        if not project:
            return None

        datasets = project.datasets
        dataset_ids = [d.id for d in datasets]

        # 2. 获取项目下所有标注配置
        configs = ProjectAnnotationConfigCRUD.get_configs_by_project(db, project_id)

        # 3. 统计QA对总数
        total_items = 0
        for dataset_id in dataset_ids:
            total_items += QAPairCRUD.count(db, dataset_id=dataset_id)

        # 4. 按配置统计标注结果
        configs_stats = []
        all_notes = []
        # 用于跟踪每个配置标注的QA对集合
        config_annotated_items = []

        for config in configs:
            # 获取该配置的所有标注结果
            results = AnnotationResultCRUD.get_all(
                db=db,
                skip=0,
                limit=1000000,
                annotation_config_id=config.id
            )

            # 过滤出属于项目数据集的结果
            filtered_results = [r for r in results if r.dataset_id in dataset_ids]

            if not filtered_results:
                # 即使没有标注结果，也记录空集合，用于后续计算完成率
                config_annotated_items.append(set())
                continue

            # 统计覆盖率
            annotated_items = set(r.dataset_item_id for r in filtered_results)
            config_annotated_items.append(annotated_items)
            coverage = len(annotated_items) / total_items if total_items > 0 else 0

            # 按标注类型进行统计分析
            stats = AnnotationResultAnalysisCRUD._analyze_by_type(
                filtered_results, config.annotation_type, config
            )

            # 收集notes
            notes_list = [r.notes for r in filtered_results if r.notes]
            if notes_list:
                all_notes.append({
                    "config_name": config.name,
                    "notes": notes_list,
                    "count": len(notes_list)
                })

            configs_stats.append({
                "config_id": config.id,
                "config_name": config.name,
                "annotation_type": config.annotation_type,
                "total_annotations": len(filtered_results),
                "coverage": coverage,
                "stats": stats
            })

        total_annotations = sum(s["total_annotations"] for s in configs_stats)

        # 计算已标注的QA对数量（至少被标注过1次）
        if config_annotated_items and total_items > 0:
            # 找出所有配置标注集合的并集（即至少被1个配置标注过的QA对）
            annotated_items = set.union(*config_annotated_items) if len(config_annotated_items) > 0 else set()
            annotated_count = len(annotated_items)

            # 计算完成率：完成所有配置标注的QA对数量
            # 找出所有配置标注集合的交集（即被所有配置都标注过的QA对）
            fully_annotated_items = set.intersection(*config_annotated_items) if len(config_annotated_items) > 0 else set()
            fully_annotated_count = len(fully_annotated_items)
            completion_rate = fully_annotated_count / total_items
        else:
            annotated_count = 0
            fully_annotated_count = 0
            completion_rate = 0

        return {
            "total_datasets": len(datasets),
            "total_items": total_items,
            "annotated_items_count": annotated_count,  # 已标注的QA对数量（至少1个配置）
            "fully_annotated_count": fully_annotated_count,  # 已完整标注的QA对数量（所有配置）
            "completion_rate": completion_rate,
            "configs_stats": configs_stats,
            "notes_summary": all_notes
        }

    @staticmethod
    def _analyze_by_type(results: List, annotation_type: str, config) -> dict:
        """按标注类型进行统计分析"""
        if annotation_type == "score":
            return AnnotationResultAnalysisCRUD._analyze_score(results, config)
        elif annotation_type in ["single_choice", "multi_choice"]:
            return AnnotationResultAnalysisCRUD._analyze_choice(results, config)
        elif annotation_type == "category":
            return AnnotationResultAnalysisCRUD._analyze_category(results, config)
        elif annotation_type == "binary":
            return AnnotationResultAnalysisCRUD._analyze_binary(results, config)
        elif annotation_type == "text":
            return AnnotationResultAnalysisCRUD._analyze_text(results, config)
        else:
            return {"type": annotation_type, "count": len(results)}

    @staticmethod
    def _analyze_score(results: List, config) -> dict:
        """分析评分标注"""
        scores = []
        for r in results:
            if r.value.score:
                scores.append(r.value.score.score)

        if not scores:
            return {"type": "score", "count": 0}

        return {
            "type": "score",
            "count": len(scores),
            "average": sum(scores) / len(scores),
            "min": min(scores),
            "max": max(scores),
            "distribution": AnnotationResultAnalysisCRUD._get_score_distribution(
                scores, config.config.min_score, config.config.max_score
            )
        }

    @staticmethod
    def _get_score_distribution(scores: List, min_score: int, max_score: int) -> dict:
        """生成分数分布"""
        distribution = {}
        for score in scores:
            key = str(int(score))
            distribution[key] = distribution.get(key, 0) + 1
        return distribution

    @staticmethod
    def _analyze_choice(results: List, config) -> dict:
        """分析选择题标注"""
        option_counts = {}
        for r in results:
            if r.value.choice:
                for option_id in r.value.choice.selected_options:
                    option_counts[option_id] = option_counts.get(option_id, 0) + 1

        # 获取选项标签
        option_labels = {}
        if config.config.options:
            for opt in config.config.options:
                option_labels[opt.option_id] = opt.label

        return {
            "type": "choice",
            "count": len(results),
            "option_distribution": option_counts,
            "option_labels": option_labels
        }

    @staticmethod
    def _analyze_category(results: List, config) -> dict:
        """分析分类标注"""
        category_counts = {}
        for r in results:
            if r.value.category:
                cat = r.value.category.category
                category_counts[cat] = category_counts.get(cat, 0) + 1

        return {
            "type": "category",
            "count": len(results),
            "category_distribution": category_counts
        }

    @staticmethod
    def _analyze_binary(results: List, config) -> dict:
        """分析二元标注"""
        true_count = 0
        false_count = 0
        for r in results:
            if r.value.binary:
                if r.value.binary.value:
                    true_count += 1
                else:
                    false_count += 1

        return {
            "type": "binary",
            "count": len(results),
            "true_count": true_count,
            "false_count": false_count,
            "true_ratio": true_count / len(results) if results else 0
        }

    @staticmethod
    def _analyze_text(results: List, config) -> dict:
        """分析文本标注"""
        lengths = []
        word_counts = []
        for r in results:
            if r.value.text and r.value.text.text:
                text = r.value.text.text
                lengths.append(len(text))
                word_counts.append(len(text.split()))

        if not lengths:
            return {"type": "text", "count": 0}

        return {
            "type": "text",
            "count": len(results),
            "avg_length": sum(lengths) / len(lengths),
            "max_length": max(lengths),
            "min_length": min(lengths),
            "avg_words": sum(word_counts) / len(word_counts) if word_counts else 0
        }


# ==================== LlmAnalysisCache CRUD ====================


class LlmAnalysisCacheCRUD:
    """LLM 分析报告缓存 CRUD 操作"""

    @staticmethod
    def get_by_project(
        db: Session, project_id: int, language: str | None = None
    ) -> Optional[dict]:
        """获取项目分析报告缓存（可按语言筛选）"""
        query = db.query(LlmAnalysisCacheModel).filter(
            LlmAnalysisCacheModel.project_id == project_id
        )
        if language:
            query = query.filter(LlmAnalysisCacheModel.language == language)
        db_model = query.order_by(LlmAnalysisCacheModel.updated_at.desc()).first()
        if not db_model:
            return None
        return {
            "analysis": db_model.analysis_text,
            "model_name": db_model.model_name,
            "notes_count": db_model.notes_count,
            "language": db_model.language,
            "created_at": db_model.created_at,
            "updated_at": db_model.updated_at,
        }

    @staticmethod
    def save(
        db: Session,
        project_id: int,
        analysis_text: str,
        model_name: str,
        notes_count: int,
        language: str = "zh",
    ) -> LlmAnalysisCacheModel:
        """保存分析报告缓存（如果已有则更新，否则创建）"""
        db_model = (
            db.query(LlmAnalysisCacheModel)
            .filter(
                LlmAnalysisCacheModel.project_id == project_id,
                LlmAnalysisCacheModel.language == language,
            )
            .first()
        )
        if db_model:
            db_model.analysis_text = analysis_text
            db_model.model_name = model_name
            db_model.notes_count = notes_count
            db_model.language = language
            db_model.updated_at = datetime.now()
        else:
            db_model = LlmAnalysisCacheModel(
                project_id=project_id,
                analysis_text=analysis_text,
                model_name=model_name,
                notes_count=notes_count,
                language=language,
            )
            db.add(db_model)
        db.commit()
        db.refresh(db_model)
        return db_model
