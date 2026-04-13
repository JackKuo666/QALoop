"""数据集相关的API接口"""

import json
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from qa_annotate.api.auth import get_current_active_user, get_current_superuser
from qa_annotate.database.base import get_db
from qa_annotate.database.crud import (
    AnnotationResultCRUD,
    DatasetAnnotationConfigCRUD,
    DatasetCRUD,
    ProjectAnnotationConfigCRUD,
    ProjectCRUD,
    QAPairCRUD,
    UserCRUD,
)
from qa_annotate.schema.annotation import AnnotationConfig
from qa_annotate.schema.dataset import Dataset, QAPair
from qa_annotate.schema.task import EvaluationDimension, TaskInfo
from qa_annotate.schema.user import User

router = APIRouter(prefix="/datasets", tags=["datasets"])


async def import_dataset_from_file(
    file: UploadFile,
    db: Session,
    current_user: User,
    dataset_name: Optional[str] = None,
    dataset_description: Optional[str] = None,
    dataset_version: Optional[str] = None,
    dataset_category: Optional[str] = None,
    dataset_status: Optional[str] = None,
    dataset_tags: Optional[str] = None,
    dataset_source: Optional[str] = None,
    dataset_source_url: Optional[str] = None,
    project_id: Optional[int] = None,
    annotator_id: Optional[int] = None,
) -> dict:
    """从JSONL文件导入数据集的辅助函数

    返回格式：
    {
        "dataset_id": int,
        "dataset_name": str,
        "created": bool,
        "imported_count": int,
        "failed_count": int,
        "total_lines": int,
        "errors": List[str]
    }
    """
    # 检查文件类型
    if not file.filename or not file.filename.endswith(".jsonl"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="只支持.jsonl格式的文件"
        )

    # 读取文件内容
    try:
        content = await file.read()
        text_content = content.decode("utf-8")
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"读取文件失败: {str(e)}"
        )

    # 解析JSONL文件
    lines = text_content.strip().split("\n")
    if not lines or not lines[0].strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="文件为空或格式不正确"
        )

    dataset_info = {}
    qa_start_index = 0

    # 如果提供了参数中的元数据，优先使用参数数据
    if dataset_name:
        dataset_info["name"] = dataset_name
        if dataset_description:
            dataset_info["description"] = dataset_description
        if dataset_version:
            dataset_info["version"] = dataset_version
        if dataset_category:
            dataset_info["category"] = dataset_category
        if dataset_status:
            dataset_info["status"] = dataset_status
        if dataset_tags:
            dataset_info["tags"] = [
                tag.strip() for tag in dataset_tags.split(",") if tag.strip()
            ]
        if dataset_source:
            dataset_info["source"] = dataset_source
        if dataset_source_url:
            dataset_info["source_url"] = dataset_source_url
    else:
        # 如果没有提供参数元数据，检查第一行是否是数据集元数据
        try:
            first_line_data = json.loads(lines[0].strip())
            if (
                isinstance(first_line_data, dict)
                and first_line_data.get("__type__") == "dataset"
            ):
                dataset_info = first_line_data.copy()
                # 移除类型标记
                dataset_info.pop("__type__", None)
                qa_start_index = 1
        except (json.JSONDecodeError, AttributeError):
            # 第一行不是数据集元数据，所有行都是QA对
            pass

    # 如果没有数据集信息，使用文件名作为数据集名称
    if "name" not in dataset_info or not dataset_info.get("name"):
        dataset_name_from_file = file.filename.replace(".jsonl", "").replace(
            ".json", ""
        )
        dataset_info["name"] = dataset_name_from_file
        if "description" not in dataset_info:
            dataset_info["description"] = f"从文件 {file.filename} 导入"

    # 验证数据集信息
    if "name" not in dataset_info or not dataset_info.get("name"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="数据集名称不能为空（请提供数据集名称，或在文件第一行提供数据集元数据）",
        )

    # 创建新数据集（总是创建新数据集，即使同名已存在）
    final_dataset_name = dataset_info["name"]
    dataset_data = {
        "name": final_dataset_name,
        "description": dataset_info.get("description"),
        "version": dataset_info.get("version"),
        "status": dataset_info.get("status", "active"),
        "category": dataset_info.get("category"),
        "tags": dataset_info.get("tags"),
        "source": dataset_info.get("source", "imported"),
        "source_url": dataset_info.get("source_url"),
        "project_id": project_id,
        "metadata": {
            k: v
            for k, v in dataset_info.items()
            if k
            not in [
                "name",
                "description",
                "version",
                "status",
                "category",
                "tags",
                "source",
                "source_url",
            ]
        },
    }
    dataset = Dataset(**dataset_data)
    dataset.creator_id = current_user.id
    dataset.creator = current_user.username

    # 处理标注者信息
    if annotator_id is not None:
        dataset.annotator_id = annotator_id
        # 从数据库获取标注者用户名
        annotator_user = UserCRUD.get_by_id(db, user_id=annotator_id)
        if annotator_user:
            dataset.annotator_name = annotator_user.username
        else:
            dataset.annotator_name = None
    elif "annotator_id" in dataset_info:
        dataset.annotator_id = dataset_info.get("annotator_id")
        if dataset.annotator_id:
            annotator_user = UserCRUD.get_by_id(db, user_id=dataset.annotator_id)
            if annotator_user:
                dataset.annotator_name = annotator_user.username
            else:
                dataset.annotator_name = None
        else:
            dataset.annotator_name = None

    created_dataset = DatasetCRUD.create(db=db, dataset=dataset)
    dataset_id = created_dataset.id

    # 导入QA对
    imported_count = 0
    failed_count = 0
    errors = []

    for line_num, line in enumerate(lines[qa_start_index:], start=qa_start_index + 1):
        line = line.strip()
        if not line:
            continue

        try:
            # 解析JSON对象
            data = json.loads(line)

            # 验证必需字段
            if "question" not in data or "answer" not in data:
                failed_count += 1
                errors.append(f"第{line_num}行: 缺少必需字段 'question' 或 'answer'")
                continue

            # 创建QAPair对象
            qa_pair_data = {
                "dataset_id": dataset_id,
                "question": str(data["question"]),
                "answer": str(data["answer"]),
            }

            # 添加额外字段（如果有）
            for key, value in data.items():
                if key not in ["id", "dataset_id", "question", "answer"]:
                    qa_pair_data[key] = value

            qa_pair = QAPair(**qa_pair_data)

            # 保存到数据库
            QAPairCRUD.create(db=db, qa_pair=qa_pair)
            imported_count += 1

        except json.JSONDecodeError as e:
            failed_count += 1
            errors.append(f"第{line_num}行: JSON解析错误 - {str(e)}")
        except Exception as e:
            failed_count += 1
            errors.append(f"第{line_num}行: 导入失败 - {str(e)}")

    return {
        "dataset_id": dataset_id,
        "dataset_name": final_dataset_name,
        "created": True,  # 总是创建新数据集
        "imported_count": imported_count,
        "failed_count": failed_count,
        "total_lines": len([line for line in lines[qa_start_index:] if line.strip()]),
        "errors": errors[:10],  # 只返回前10个错误，避免响应过大
    }


def apply_project_inheritance(
    db: Session, dataset: Dataset, include_configs: bool = False
) -> Dataset:
    """应用项目继承逻辑到数据集

    - display_extra_fields: 如果数据集未设置，则使用项目的display_extra_fields
    - 标注配置: 如果数据集没有配置，则继承项目关联的标注配置；如果数据集已有配置，则不继承
    """
    if not dataset.project_id:
        return dataset

    # 获取项目信息
    project = ProjectCRUD.get_by_id(db, project_id=dataset.project_id)
    if not project:
        return dataset

    # 继承display_extra_fields
    if not dataset.display_extra_fields and project.display_extra_fields:
        dataset.display_extra_fields = project.display_extra_fields

    # 如果需要包含配置，则处理标注配置继承
    if include_configs:
        # 获取数据集自己的配置
        dataset_configs = DatasetAnnotationConfigCRUD.get_configs_by_dataset(
            db=db, dataset_id=dataset.id
        )

        # 如果数据集没有配置，则继承项目的配置
        if not dataset_configs:
            project_configs = ProjectAnnotationConfigCRUD.get_configs_by_project(
                db=db, project_id=dataset.project_id
            )
            # 将继承的配置添加到dataset对象（如果Dataset支持annotation_configs字段）
            if hasattr(dataset, "annotation_configs"):
                dataset.annotation_configs = project_configs
        else:
            # 数据集已有配置，不继承项目的配置
            if hasattr(dataset, "annotation_configs"):
                dataset.annotation_configs = dataset_configs

    return dataset


def build_task_info(db: Session, dataset: Dataset) -> TaskInfo:
    """构建任务信息

    从数据集和关联的项目中提取完整的任务信息，包括：
    - 数据集基本信息
    - 目标标注数量（计算得出）
    - 项目信息（如果数据集属于项目）
    - 评估目的和完成时间（从项目 metadata 获取）
    - 评估维度（从项目 annotation_configs 获取）

    Args:
        db: 数据库会话
        dataset: 数据集对象

    Returns:
        完整的任务信息
    """
    # 计算目标标注数量
    target_count = DatasetCRUD.get_items_count(db, dataset.id)

    # 初始化任务信息
    task_info = TaskInfo(
        dataset_id=dataset.id,
        dataset_name=dataset.name,
        task_description=dataset.description,
        category=dataset.category,
        target_annotation_count=target_count,
        project_id=dataset.project_id,
        project_name=None,
        evaluation_purpose=None,
        deadline=None,
        evaluation_dimensions=[],
    )

    # 如果数据集属于项目，获取项目信息
    if dataset.project_id:
        project = ProjectCRUD.get_by_id(db, project_id=dataset.project_id)
        if project:
            task_info.project_name = project.name

            # 如果数据集的描述为空，从项目获取
            if not task_info.task_description and project.description:
                task_info.task_description = project.description

            # 如果数据集的分类为空，从项目获取
            if not task_info.category and project.category:
                task_info.category = project.category

            # 从项目 metadata 中获取评估目的和完成时间
            if project.metadata:
                task_info.evaluation_purpose = project.metadata.get(
                    "evaluation_purpose"
                )
                deadline = project.metadata.get("deadline")
                if deadline:
                    # 确保 deadline 是字符串格式（ISO 8601）
                    if isinstance(deadline, str):
                        task_info.deadline = deadline
                    else:
                        # 如果是 datetime 对象，转换为字符串
                        task_info.deadline = deadline.isoformat()

            # 获取评估维度（从项目的 annotation_configs）
            configs = ProjectAnnotationConfigCRUD.get_configs_by_project(
                db, project_id=project.id
            )
            task_info.evaluation_dimensions = [
                EvaluationDimension(name=config.name, description=config.description)
                for config in configs
            ]

    # 计算标注进度
    annotated_count = 0
    progress_rate = 0.0

    if target_count > 0:
        # 获取标注配置（考虑项目继承）
        configs = get_dataset_configs_with_inheritance(
            db=db, dataset_id=dataset.id, include_inherited=True
        )

        if configs:
            # 获取所有标注结果
            all_results = AnnotationResultCRUD.get_all(
                db=db, dataset_id=dataset.id, skip=0, limit=100000
            )

            # 统计已标注的QA对数量（考虑必填配置）
            valid_config_ids = set(c.id for c in configs)
            required_configs = [c for c in configs if c.required]

            if required_configs:
                # 有必填配置：所有必填配置都已标注
                required_config_ids = set(c.id for c in required_configs)
                items_configs = {}
                for result in all_results:
                    if result.annotation_config_id not in valid_config_ids:
                        continue
                    item_id = result.dataset_item_id
                    if item_id not in items_configs:
                        items_configs[item_id] = set()
                    items_configs[item_id].add(result.annotation_config_id)

                annotated_count = sum(
                    1
                    for item_id, config_ids in items_configs.items()
                    if required_config_ids.issubset(config_ids)
                )
            else:
                # 没有必填配置：至少一个配置有标注结果
                items_with_results = set(
                    r.dataset_item_id
                    for r in all_results
                    if r.annotation_config_id in valid_config_ids
                )
                annotated_count = len(items_with_results)

            progress_rate = (
                (annotated_count / target_count * 100) if target_count > 0 else 0.0
            )

    task_info.annotated_count = annotated_count
    task_info.progress_rate = round(progress_rate, 2)

    return task_info


@router.post("/", response_model=Dataset, status_code=status.HTTP_201_CREATED)
def create_dataset(
    dataset: Dataset,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    """创建数据集（需要超级用户权限）"""
    # 如果提供了ID，检查是否已存在
    if dataset.id is not None:
        existing = DatasetCRUD.get_by_id(db, dataset_id=dataset.id)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"数据集 ID {dataset.id} 已存在",
            )

    # 设置创建者信息
    if not dataset.creator_id:
        dataset.creator_id = current_user.id
    if not dataset.creator:
        dataset.creator = current_user.username

    # 处理标注者信息：如果提供了 annotator_id，自动获取用户名
    if dataset.annotator_id is not None:
        annotator_user = UserCRUD.get_by_id(db, user_id=dataset.annotator_id)
        if annotator_user:
            dataset.annotator_name = annotator_user.username
        else:
            dataset.annotator_name = None
    elif dataset.annotator_id is None and dataset.annotator_name:
        # 如果只提供了 annotator_name 但没有 annotator_id，尝试通过用户名查找
        annotator_user = UserCRUD.get_by_username(db, username=dataset.annotator_name)
        if annotator_user:
            dataset.annotator_id = annotator_user.id

    created = DatasetCRUD.create(db=db, dataset=dataset)
    return apply_project_inheritance(db, created)


@router.get("/", response_model=List[Dataset])
def list_datasets(
    skip: int = 0,
    limit: int = 100,
    name_search: Optional[str] = None,
    include_configs: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    """获取数据集列表（需要超级用户权限）"""
    datasets = DatasetCRUD.get_all(
        db=db, skip=skip, limit=limit, name_search=name_search
    )
    return [
        apply_project_inheritance(db, dataset, include_configs=include_configs)
        for dataset in datasets
    ]


@router.get("/{dataset_id}", response_model=Dataset)
def get_dataset(
    dataset_id: int,
    include_configs: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    """根据ID获取数据集（需要超级用户权限）"""
    dataset = DatasetCRUD.get_by_id(db, dataset_id=dataset_id)
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"数据集 ID {dataset_id} 不存在",
        )
    return apply_project_inheritance(db, dataset, include_configs=include_configs)


@router.put("/{dataset_id}", response_model=Dataset)
def update_dataset(
    dataset_id: int,
    dataset: Dataset,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    """更新数据集（需要超级用户权限）"""
    # 检查数据集是否存在
    existing = DatasetCRUD.get_by_id(db, dataset_id=dataset_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"数据集 ID {dataset_id} 不存在",
        )

    # 确保ID一致
    dataset.id = dataset_id

    # 处理标注者信息：如果提供了 annotator_id，自动获取用户名
    if dataset.annotator_id is not None:
        annotator_user = UserCRUD.get_by_id(db, user_id=dataset.annotator_id)
        if annotator_user:
            dataset.annotator_name = annotator_user.username
        else:
            dataset.annotator_name = None
    elif dataset.annotator_id is None and dataset.annotator_name:
        # 如果只提供了 annotator_name 但没有 annotator_id，尝试通过用户名查找
        annotator_user = UserCRUD.get_by_username(db, username=dataset.annotator_name)
        if annotator_user:
            dataset.annotator_id = annotator_user.id

    updated = DatasetCRUD.update(db=db, dataset_id=dataset_id, dataset=dataset)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"数据集 ID {dataset_id} 不存在",
        )
    return apply_project_inheritance(db, updated)


@router.delete("/{dataset_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_dataset(
    dataset_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    """删除数据集（需要超级用户权限）"""
    success = DatasetCRUD.delete(db=db, dataset_id=dataset_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"数据集 ID {dataset_id} 不存在",
        )
    return None


@router.get("/{dataset_id}/items", response_model=List[QAPair])
def list_dataset_items(
    dataset_id: int,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    """获取数据集的所有QA对（需要超级用户权限）"""
    # 检查数据集是否存在
    dataset = DatasetCRUD.get_by_id(db, dataset_id=dataset_id)
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"数据集 ID {dataset_id} 不存在",
        )

    return QAPairCRUD.get_by_dataset(
        db=db, dataset_id=dataset_id, skip=skip, limit=limit
    )


@router.post(
    "/{dataset_id}/items", response_model=QAPair, status_code=status.HTTP_201_CREATED
)
def create_dataset_item(
    dataset_id: int,
    qa_pair: QAPair,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    """创建数据集的QA对（需要超级用户权限）"""
    # 检查数据集是否存在
    dataset = DatasetCRUD.get_by_id(db, dataset_id=dataset_id)
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"数据集 ID {dataset_id} 不存在",
        )

    # 确保dataset_id一致
    qa_pair.dataset_id = dataset_id

    return QAPairCRUD.create(db=db, qa_pair=qa_pair)


@router.get("/{dataset_id}/items/{item_id}", response_model=QAPair)
def get_dataset_item(
    dataset_id: int,
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    """获取数据集的单个QA对（需要超级用户权限）"""
    qa_pair = QAPairCRUD.get_by_id(db, qa_pair_id=item_id)
    if not qa_pair:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"QA对 ID {item_id} 不存在"
        )

    if qa_pair.dataset_id != dataset_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"QA对 ID {item_id} 不属于数据集 ID {dataset_id}",
        )

    return qa_pair


@router.put("/{dataset_id}/items/{item_id}", response_model=QAPair)
def update_dataset_item(
    dataset_id: int,
    item_id: int,
    qa_pair: QAPair,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    """更新数据集的QA对（需要超级用户权限）"""
    # 检查QA对是否存在
    existing = QAPairCRUD.get_by_id(db, qa_pair_id=item_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"QA对 ID {item_id} 不存在"
        )

    if existing.dataset_id != dataset_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"QA对 ID {item_id} 不属于数据集 ID {dataset_id}",
        )

    # 确保ID和dataset_id一致
    qa_pair.id = item_id
    qa_pair.dataset_id = dataset_id

    updated = QAPairCRUD.update(db=db, qa_pair_id=item_id, qa_pair=qa_pair)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"QA对 ID {item_id} 不存在"
        )
    return updated


@router.delete("/{dataset_id}/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_dataset_item(
    dataset_id: int,
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    """删除数据集的QA对（需要超级用户权限）"""
    # 检查QA对是否存在
    existing = QAPairCRUD.get_by_id(db, qa_pair_id=item_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"QA对 ID {item_id} 不存在"
        )

    if existing.dataset_id != dataset_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"QA对 ID {item_id} 不属于数据集 ID {dataset_id}",
        )

    success = QAPairCRUD.delete(db=db, qa_pair_id=item_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"QA对 ID {item_id} 不存在"
        )
    return None


@router.get("/{dataset_id}/stats")
def get_dataset_stats(
    dataset_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    """获取数据集的统计信息（需要超级用户权限）"""
    # 检查数据集是否存在
    dataset = DatasetCRUD.get_by_id(db, dataset_id=dataset_id)
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"数据集 ID {dataset_id} 不存在",
        )

    items_count = QAPairCRUD.count(db=db, dataset_id=dataset_id)
    configs_count = DatasetAnnotationConfigCRUD.count_configs_by_dataset(
        db=db, dataset_id=dataset_id
    )

    return {
        "dataset_id": dataset_id,
        "items_count": items_count,
        "configs_count": configs_count,
    }


def get_dataset_configs_with_inheritance(
    db: Session, dataset_id: int, include_inherited: bool = True
) -> List:
    """获取数据集关联的所有标注配置（考虑项目继承）

    如果include_inherited=True，且数据集没有自己的配置，则返回从项目继承的配置
    如果数据集已有配置，则不继承项目的配置

    Args:
        db: 数据库会话
        dataset_id: 数据集ID
        include_inherited: 是否包含继承的配置

    Returns:
        标注配置列表
    """
    # 检查数据集是否存在
    dataset = DatasetCRUD.get_by_id(db, dataset_id=dataset_id)
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"数据集 ID {dataset_id} 不存在",
        )

    # 获取数据集自己的配置
    dataset_configs = DatasetAnnotationConfigCRUD.get_configs_by_dataset(
        db=db, dataset_id=dataset_id
    )

    # 如果数据集已有配置，直接返回，不继承项目的配置
    if dataset_configs:
        return dataset_configs

    # 如果数据集没有配置，且需要包含继承的配置，且数据集属于某个项目
    if include_inherited and dataset.project_id:
        project_configs = ProjectAnnotationConfigCRUD.get_configs_by_project(
            db=db, project_id=dataset.project_id
        )
        return project_configs

    return dataset_configs


@router.get("/{dataset_id}/annotation-progress")
def get_dataset_annotation_progress(
    dataset_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    """获取数据集的标注进展（需要超级用户权限）"""
    # 检查数据集是否存在
    dataset = DatasetCRUD.get_by_id(db, dataset_id=dataset_id)
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"数据集 ID {dataset_id} 不存在",
        )

    # 获取总QA对数量
    total_items = QAPairCRUD.count(db=db, dataset_id=dataset_id)

    # 获取所有标注配置（考虑项目继承）
    configs = get_dataset_configs_with_inheritance(
        db=db, dataset_id=dataset_id, include_inherited=True
    )

    # 获取所有标注结果
    all_results = AnnotationResultCRUD.get_all(
        db=db, dataset_id=dataset_id, skip=0, limit=100000
    )

    # 统计每个配置的标注情况
    config_progress = []
    for config in configs:
        # 统计该配置的标注结果数量
        config_results = [r for r in all_results if r.annotation_config_id == config.id]
        annotated_items = len(set(r.dataset_item_id for r in config_results))
        progress_rate = (annotated_items / total_items * 100) if total_items > 0 else 0

        config_progress.append(
            {
                "config_id": config.id,
                "config_name": config.name,
                "annotated_items": annotated_items,
                "total_items": total_items,
                "progress_rate": round(progress_rate, 2),
            }
        )

    # 统计总体标注情况
    # 如果有必填配置：所有必填配置都已标注的QA对数量
    # 如果没有必填配置：至少一个配置有标注结果的QA对数量
    # 只统计当前有效配置的标注结果，过滤掉已取消配置的标注结果
    valid_config_ids = set(c.id for c in configs)
    required_configs = [c for c in configs if c.required]

    if required_configs:
        # 有必填配置：检查每个QA对是否所有必填配置都有标注结果
        required_config_ids = set(c.id for c in required_configs)
        # 按QA对分组标注结果，只保留属于当前有效配置的结果
        items_configs = {}
        for result in all_results:
            # 过滤掉已取消配置的标注结果
            if result.annotation_config_id not in valid_config_ids:
                continue
            item_id = result.dataset_item_id
            if item_id not in items_configs:
                items_configs[item_id] = set()
            items_configs[item_id].add(result.annotation_config_id)
        # 统计所有必填配置都有标注结果的QA对
        annotated_items_count = sum(
            1
            for item_id, config_ids in items_configs.items()
            if required_config_ids.issubset(config_ids)
        )
    else:
        # 没有必填配置：至少一个配置有标注结果（只统计有效配置）
        items_with_results = set(
            r.dataset_item_id
            for r in all_results
            if r.annotation_config_id in valid_config_ids
        )
        annotated_items_count = len(items_with_results)

    overall_progress_rate = (
        (annotated_items_count / total_items * 100) if total_items > 0 else 0
    )

    return {
        "dataset_id": dataset_id,
        "total_items": total_items,
        "annotated_items": annotated_items_count,
        "overall_progress_rate": round(overall_progress_rate, 2),
        "config_progress": config_progress,
    }


@router.get("/{dataset_id}/configs", response_model=List[AnnotationConfig])
def get_dataset_configs(
    dataset_id: int,
    include_inherited: bool = True,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    """获取数据集关联的所有标注配置（需要超级用户权限）

    如果include_inherited=True，且数据集没有自己的配置，则返回从项目继承的配置
    如果数据集已有配置，则不继承项目的配置
    """
    # 使用统一的辅助函数获取配置（考虑项目继承）
    return get_dataset_configs_with_inheritance(
        db=db, dataset_id=dataset_id, include_inherited=include_inherited
    )


@router.post("/{dataset_id}/import", status_code=status.HTTP_200_OK)
async def import_dataset_from_jsonl(
    dataset_id: int,
    file: UploadFile = File(..., description="JSONL文件"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    """从JSONL文件导入QA对到数据集（需要超级用户权限）"""
    # 检查数据集是否存在
    dataset = DatasetCRUD.get_by_id(db, dataset_id=dataset_id)
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"数据集 ID {dataset_id} 不存在",
        )

    # 检查文件类型
    if not file.filename.endswith(".jsonl"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="只支持.jsonl格式的文件"
        )

    # 读取文件内容
    try:
        content = await file.read()
        text_content = content.decode("utf-8")
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"读取文件失败: {str(e)}"
        )

    # 解析JSONL文件
    lines = text_content.strip().split("\n")
    imported_count = 0
    failed_count = 0
    errors = []

    for line_num, line in enumerate(lines, start=1):
        line = line.strip()
        if not line:
            continue

        try:
            # 解析JSON对象
            data = json.loads(line)

            # 验证必需字段
            if "question" not in data or "answer" not in data:
                failed_count += 1
                errors.append(f"第{line_num}行: 缺少必需字段 'question' 或 'answer'")
                continue

            # 创建QAPair对象
            qa_pair_data = {
                "dataset_id": dataset_id,
                "question": str(data["question"]),
                "answer": str(data["answer"]),
            }

            # 添加额外字段（如果有）
            for key, value in data.items():
                if key not in ["id", "dataset_id", "question", "answer"]:
                    qa_pair_data[key] = value

            qa_pair = QAPair(**qa_pair_data)

            # 保存到数据库
            QAPairCRUD.create(db=db, qa_pair=qa_pair)
            imported_count += 1

        except json.JSONDecodeError as e:
            failed_count += 1
            errors.append(f"第{line_num}行: JSON解析错误 - {str(e)}")
        except Exception as e:
            failed_count += 1
            errors.append(f"第{line_num}行: 导入失败 - {str(e)}")

    return {
        "dataset_id": dataset_id,
        "imported_count": imported_count,
        "failed_count": failed_count,
        "total_lines": len([line for line in lines if line.strip()]),
        "errors": errors[:10],  # 只返回前10个错误，避免响应过大
    }


@router.post("/import", status_code=status.HTTP_201_CREATED)
async def import_dataset(
    file: UploadFile = File(..., description="JSONL文件"),
    name: Optional[str] = Form(
        None, description="数据集名称（如果提供，将覆盖文件中的元数据）"
    ),
    description: Optional[str] = Form(None, description="数据集描述"),
    version: Optional[str] = Form(None, description="数据集版本"),
    category: Optional[str] = Form(None, description="数据集分类"),
    status: Optional[str] = Form(None, description="数据集状态"),
    tags: Optional[str] = Form(None, description="数据集标签（逗号分隔）"),
    source: Optional[str] = Form(None, description="数据来源"),
    source_url: Optional[str] = Form(None, description="数据来源URL"),
    annotator_id: Optional[int] = Form(None, description="标注者ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    """从JSONL文件导入完整数据集（包括数据集信息和QA对，需要超级用户权限）

    JSONL文件格式：
    1. 第一行（可选）：数据集元数据，格式为 {"__type__": "dataset", "name": "...", "description": "...", ...}
    2. 后续行：QA对，每行一个JSON对象，必须包含question和answer字段

    如果提供了表单中的元数据字段，将优先使用表单中的元数据，而不是文件中的元数据。
    如果第一行不是数据集元数据且未提供表单元数据，则使用文件名作为数据集名称。
    """
    return await import_dataset_from_file(
        file=file,
        db=db,
        current_user=current_user,
        dataset_name=name,
        dataset_description=description,
        dataset_version=version,
        dataset_category=category,
        dataset_status=status,
        dataset_tags=tags,
        dataset_source=source,
        dataset_source_url=source_url,
        annotator_id=annotator_id,
    )


# ==================== 普通用户标注接口 ====================


def check_dataset_access_permission(dataset: Dataset, current_user: User) -> None:
    """检查用户是否有权限访问数据集

    规则：
    - 管理员（is_superuser=True）可以访问所有数据集
    - 普通用户只能访问分配给自己的数据集（annotator_id == current_user.id）

    如果没有权限，抛出 HTTPException
    """
    # 管理员可以访问所有数据集
    if current_user.is_superuser:
        return

    # 普通用户只能访问分配给自己的数据集
    if dataset.annotator_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="该数据集尚未分配给任何用户，无权访问",
        )

    if dataset.annotator_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权访问此数据集，该数据集已分配给其他用户",
        )


@router.get("/annotation/{dataset_id}/info", response_model=Dataset)
def get_dataset_info_for_annotation(
    dataset_id: int,
    include_configs: bool = True,  # 标注时默认包含配置
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取数据集信息（普通用户可访问，用于标注）"""
    dataset = DatasetCRUD.get_by_id(db, dataset_id=dataset_id)
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"数据集 ID {dataset_id} 不存在",
        )

    # 检查权限
    check_dataset_access_permission(dataset, current_user)

    return apply_project_inheritance(db, dataset, include_configs=include_configs)


@router.get("/annotation/{dataset_id}/items", response_model=List[QAPair])
def list_dataset_items_for_annotation(
    dataset_id: int,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取数据集的QA对列表（普通用户可访问，用于标注）"""
    # 检查数据集是否存在
    dataset = DatasetCRUD.get_by_id(db, dataset_id=dataset_id)
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"数据集 ID {dataset_id} 不存在",
        )

    # 检查权限
    check_dataset_access_permission(dataset, current_user)

    return QAPairCRUD.get_by_dataset(
        db=db, dataset_id=dataset_id, skip=skip, limit=limit
    )


@router.get("/annotation/{dataset_id}/items/{item_id}", response_model=QAPair)
def get_dataset_item_for_annotation(
    dataset_id: int,
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取单个QA对（普通用户可访问，用于标注）"""
    qa_pair = QAPairCRUD.get_by_id(db, qa_pair_id=item_id)
    if not qa_pair:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"QA对 ID {item_id} 不存在"
        )

    if qa_pair.dataset_id != dataset_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"QA对 ID {item_id} 不属于数据集 ID {dataset_id}",
        )

    # 检查数据集权限
    dataset = DatasetCRUD.get_by_id(db, dataset_id=dataset_id)
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"数据集 ID {dataset_id} 不存在",
        )

    # 检查权限
    check_dataset_access_permission(dataset, current_user)

    return qa_pair


@router.get("/annotation/{dataset_id}/configs", response_model=List[AnnotationConfig])
def get_dataset_configs_for_annotation(
    dataset_id: int,
    include_inherited: bool = True,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取数据集关联的所有标注配置（普通用户可访问，用于标注）

    如果include_inherited=True，且数据集没有自己的配置，则返回从项目继承的配置
    如果数据集已有配置，则不继承项目的配置
    """
    # 检查数据集是否存在
    dataset = DatasetCRUD.get_by_id(db, dataset_id=dataset_id)
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"数据集 ID {dataset_id} 不存在",
        )

    # 检查权限
    check_dataset_access_permission(dataset, current_user)

    # 使用统一的辅助函数获取配置（考虑项目继承）
    return get_dataset_configs_with_inheritance(
        db=db, dataset_id=dataset_id, include_inherited=include_inherited
    )


@router.get("/annotation/{dataset_id}/stats")
def get_dataset_stats_for_annotation(
    dataset_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取数据集的统计信息（普通用户可访问，用于标注）"""
    # 检查数据集是否存在
    dataset = DatasetCRUD.get_by_id(db, dataset_id=dataset_id)
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"数据集 ID {dataset_id} 不存在",
        )

    # 检查权限
    check_dataset_access_permission(dataset, current_user)

    items_count = QAPairCRUD.count(db=db, dataset_id=dataset_id)
    configs_count = DatasetAnnotationConfigCRUD.count_configs_by_dataset(
        db=db, dataset_id=dataset_id
    )

    return {
        "dataset_id": dataset_id,
        "items_count": items_count,
        "configs_count": configs_count,
    }


# ==================== 任务相关 API ====================


@router.get("/tasks/available", response_model=List[TaskInfo])
def get_available_tasks(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取当前用户可领取的任务列表

    规则：
    1. 只显示 annotator_id 为空的数据集
    2. 如果用户有 species：
       - 显示 category 匹配用户 species 的数据集
       - 或没有 category 的数据集
    3. 如果用户没有 species：
       - 只显示没有 category 的数据集
       - 排除有 category 的数据集，因为用户无法领取它们

    Returns:
        可领取的任务列表，包含完整的项目信息
    """
    # 获取可领取的数据集
    datasets = DatasetCRUD.get_available_datasets(
        db=db, skip=skip, limit=limit, user_species=current_user.species
    )

    # 为每个数据集构建完整的任务信息
    tasks = [build_task_info(db, dataset) for dataset in datasets]

    return tasks


@router.post("/tasks/{dataset_id}/claim", response_model=Dataset)
def claim_task(
    dataset_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """领取任务（将数据集分配给当前用户）

    规则：
    1. 数据集必须没有指定标注者（annotator_id 为空）
    2. 如果数据集有 category，必须匹配用户的 species
    3. 如果数据集没有 category，所有用户都可以领取

    Returns:
        更新后的数据集对象
    """
    # 获取数据集
    dataset = DatasetCRUD.get_by_id(db, dataset_id=dataset_id)
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"数据集 ID {dataset_id} 不存在",
        )

    # 检查分类匹配（在原子更新前进行业务逻辑检查）
    if dataset.category:
        if not current_user.species:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="该任务需要匹配的物种标签，您的账户未设置物种标签",
            )
        if dataset.category != current_user.species:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"该任务需要物种标签 '{dataset.category}'，您的物种标签是 '{current_user.species}'",
            )

    # 使用原子更新领取任务（并发安全）
    # 只有当 annotator_id 为 None 时才会更新，确保不会覆盖其他用户的领取
    updated = DatasetCRUD.claim_dataset(
        db=db,
        dataset_id=dataset_id,
        annotator_id=current_user.id,
        annotator_name=current_user.username,
    )

    if not updated:
        # 原子更新失败，可能是已被其他用户领取或数据集不存在
        # 重新查询以获取最新状态
        dataset = DatasetCRUD.get_by_id(db, dataset_id=dataset_id)
        if not dataset:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"数据集 ID {dataset_id} 不存在",
            )
        if dataset.annotator_id is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="该任务已被其他用户领取",
            )
        # 如果仍然为 None，可能是其他原因导致的更新失败
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="领取任务失败",
        )

    return updated


@router.get("/tasks/my", response_model=List[TaskInfo])
def get_my_tasks(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取分配给当前用户的任务列表

    Returns:
        当前用户已领取的任务列表，包含完整的项目信息
    """
    # 查询分配给当前用户的数据集
    datasets = DatasetCRUD.get_by_annotator(
        db=db, annotator_id=current_user.id, skip=skip, limit=limit
    )

    # 为每个数据集构建完整的任务信息
    tasks = [build_task_info(db, dataset) for dataset in datasets]

    return tasks


@router.post("/tasks/{dataset_id}/release", response_model=Dataset)
def release_task(
    dataset_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """退回任务（将数据集从当前用户释放，使其重新变为可用）

    规则：
    1. 数据集必须属于当前用户（annotator_id == current_user.id）
    2. 退回后，数据集将重新出现在可用任务列表中

    Returns:
        更新后的数据集对象
    """
    # 获取数据集
    dataset = DatasetCRUD.get_by_id(db, dataset_id=dataset_id)
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"数据集 ID {dataset_id} 不存在",
        )

    # 检查任务是否属于当前用户
    if dataset.annotator_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="该任务不属于您，无法退回",
        )

    # 使用原子更新退回任务（并发安全）
    # 只有当 annotator_id 匹配当前用户时才会更新
    updated = DatasetCRUD.release_dataset(
        db=db,
        dataset_id=dataset_id,
        annotator_id=current_user.id,
    )

    if not updated:
        # 原子更新失败，可能是已被其他用户领取或数据集不存在
        # 重新查询以获取最新状态
        dataset = DatasetCRUD.get_by_id(db, dataset_id=dataset_id)
        if not dataset:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"数据集 ID {dataset_id} 不存在",
            )
        if dataset.annotator_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="该任务不属于您，无法退回",
            )
        # 如果仍然失败，可能是其他原因导致的更新失败
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="退回任务失败",
        )

    return updated
