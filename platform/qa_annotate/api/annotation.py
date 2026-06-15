"""标注配置相关的API接口"""

import csv
import io
import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from qa_annotate.api.auth import get_current_active_user, get_current_superuser
from qa_annotate.api.dataset import get_dataset_configs_with_inheritance
from qa_annotate.database.base import get_db
from qa_annotate.database.crud import (
    AnnotationConfigCRUD,
    AnnotationResultCRUD,
    DatasetAnnotationConfigCRUD,
    QAPairCRUD,
)
from qa_annotate.schema.annotation import (
    AnnotationConfig,
    AnnotationResult,
    AnnotationType,
    BinaryConfig,
)
from qa_annotate.schema.dataset import Dataset
from qa_annotate.schema.user import User


def simplify_annotation_value(
    value_dict: Dict[str, Any],
    annotation_type: Optional[str] = None,
    config: Optional[Any] = None,
) -> Any:
    """根据标注类型简化标注值格式，移除不必要的嵌套和null字段"""

    # 根据类型简化格式
    if annotation_type == "binary" and "binary" in value_dict and value_dict["binary"]:
        binary_data = value_dict["binary"]
        if isinstance(binary_data, dict):
            # 二元标注：将布尔值替换为label，如果有confidence也保留
            value = binary_data.get("value")
            confidence = binary_data.get("confidence")

            # 获取label
            label = None
            if (
                config
                and annotation_type == "binary"
                and isinstance(config.config, BinaryConfig)
            ):
                binary_config = config.config
                if value is True:
                    label = binary_config.true_label or "是"
                elif value is False:
                    label = binary_config.false_label or "否"

            # 如果没有获取到label，使用默认值
            if label is None:
                label = "是" if value is True else "否"

            if confidence is not None:
                return {"value": label, "confidence": confidence}
            elif value is not None:
                return label
        return binary_data

    elif annotation_type == "text" and "text" in value_dict and value_dict["text"]:
        text_data = value_dict["text"]
        if isinstance(text_data, dict):
            # 文本标注：如果有tags，返回对象；否则直接返回文本
            text_value = text_data.get("text")
            tags = text_data.get("tags")
            if tags:
                return {"text": text_value, "tags": tags}
            elif text_value is not None:
                return text_value
        return text_data

    elif annotation_type == "score" and "score" in value_dict and value_dict["score"]:
        score_data = value_dict["score"]
        if isinstance(score_data, dict):
            # 评分配注：返回分数，如果有dimension也保留（reason已迁移到notes字段）
            result = {"score": score_data["score"]}
            if "dimension" in score_data and score_data["dimension"]:
                result["dimension"] = score_data["dimension"]
            # 如果只有score，直接返回分数值
            if len(result) == 1:
                return result["score"]
            return result
        return score_data

    elif (
        annotation_type == "category"
        and "category" in value_dict
        and value_dict["category"]
    ):
        category_data = value_dict["category"]
        if isinstance(category_data, dict):
            # 分类标注：如果有sub_category，返回对象；否则直接返回分类
            category_value = category_data.get("category")
            sub_category = category_data.get("sub_category")
            if sub_category:
                return {"category": category_value, "sub_category": sub_category}
            elif category_value is not None:
                return category_value
        return category_data

    elif (
        annotation_type in ["single_choice", "multi_choice"]
        and "choice" in value_dict
        and value_dict["choice"]
    ):
        choice_data = value_dict["choice"]
        if isinstance(choice_data, dict) and "selected_options" in choice_data:
            # 选择题标注：直接返回选项列表
            options = choice_data["selected_options"]
            # 如果是单选且只有一个选项，直接返回选项值
            if annotation_type == "single_choice" and len(options) == 1:
                return options[0]
            return options
        return choice_data

    # 如果没有匹配的类型，使用通用清理逻辑
    cleaned = {}
    for key, val in value_dict.items():
        if val is None:
            continue

        if isinstance(val, dict):
            cleaned_sub = simplify_annotation_value(val, annotation_type, config)
            if cleaned_sub is not None:  # 只添加非None值
                cleaned[key] = cleaned_sub
        elif isinstance(val, list):
            if val:  # 只添加非空列表
                cleaned[key] = val
        else:
            cleaned[key] = val

    # 如果清理后只有一个键，且该键的值不是字典，可以考虑进一步简化
    if len(cleaned) == 1:
        return list(cleaned.values())[0]

    return cleaned if cleaned else None


router = APIRouter(prefix="/annotation-configs", tags=["annotation-configs"])

# 标注结果路由（普通用户可访问）
annotation_result_router = APIRouter(
    prefix="/annotation-results", tags=["annotation-results"]
)


@router.post("/", response_model=AnnotationConfig, status_code=status.HTTP_201_CREATED)
def create_annotation_config(
    config: AnnotationConfig,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    """创建标注配置（需要超级用户权限）"""
    # 如果提供了ID，检查是否已存在
    if config.id is not None:
        existing = AnnotationConfigCRUD.get_by_id(db, config_id=config.id)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"标注配置 ID {config.id} 已存在",
            )

    return AnnotationConfigCRUD.create(db=db, config=config)


@router.get("/", response_model=List[AnnotationConfig])
def list_annotation_configs(
    skip: int = 0,
    limit: int = 100,
    annotation_type: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    """获取标注配置列表（需要超级用户权限）"""
    return AnnotationConfigCRUD.get_all(
        db=db, skip=skip, limit=limit, annotation_type=annotation_type
    )


@router.get("/types", response_model=List[str])
def get_annotation_types(current_user: User = Depends(get_current_superuser)):
    """获取所有可用的标注类型（需要超级用户权限）"""
    return [t.value for t in AnnotationType]


@router.get("/{config_id}", response_model=AnnotationConfig)
def get_annotation_config(
    config_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    """根据ID获取标注配置（需要超级用户权限）"""
    config = AnnotationConfigCRUD.get_by_id(db, config_id=config_id)
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"标注配置 ID {config_id} 不存在",
        )
    return config


@router.put("/{config_id}", response_model=AnnotationConfig)
def update_annotation_config(
    config_id: int,
    config: AnnotationConfig,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    """更新标注配置（需要超级用户权限）"""
    # 检查配置是否存在
    existing = AnnotationConfigCRUD.get_by_id(db, config_id=config_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"标注配置 ID {config_id} 不存在",
        )

    # 检查是否存在标注结果
    results_count = AnnotationResultCRUD.count(db=db, annotation_config_id=config_id)
    if results_count > 0:
        # 获取关联的数据集信息
        datasets = DatasetAnnotationConfigCRUD.get_datasets_by_config(
            db=db, annotation_config_id=config_id
        )
        dataset_count = len(datasets)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"该标注配置存在 {results_count} 条标注结果，关联了 {dataset_count} 个数据集，不允许编辑。请先删除相关标注结果后再进行操作。",
        )

    # 确保ID一致
    config.id = config_id

    updated = AnnotationConfigCRUD.update(db=db, config_id=config_id, config=config)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"标注配置 ID {config_id} 不存在",
        )
    return updated


@router.delete("/{config_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_annotation_config(
    config_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    """删除标注配置（硬删除，需要超级用户权限）"""
    # 检查配置是否存在
    existing = AnnotationConfigCRUD.get_by_id(db, config_id=config_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"标注配置 ID {config_id} 不存在",
        )

    # 检查是否存在标注结果
    results_count = AnnotationResultCRUD.count(db=db, annotation_config_id=config_id)
    if results_count > 0:
        # 获取关联的数据集信息
        datasets = DatasetAnnotationConfigCRUD.get_datasets_by_config(
            db=db, annotation_config_id=config_id
        )
        dataset_count = len(datasets)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"该标注配置存在 {results_count} 条标注结果，关联了 {dataset_count} 个数据集，不允许删除。请先删除相关标注结果后再进行操作。",
        )

    success = AnnotationConfigCRUD.delete(db=db, config_id=config_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"标注配置 ID {config_id} 不存在",
        )
    return None


@router.post("/{config_id}/associate/{dataset_id}", status_code=status.HTTP_200_OK)
def associate_config_to_dataset(
    config_id: int,
    dataset_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    """将标注配置关联到数据集（需要超级用户权限）"""
    success = DatasetAnnotationConfigCRUD.associate(
        db=db, dataset_id=dataset_id, annotation_config_id=config_id
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="关联失败，请检查数据集和标注配置是否存在",
        )
    return {"message": "关联成功"}


@router.delete("/{config_id}/associate/{dataset_id}", status_code=status.HTTP_200_OK)
def disassociate_config_from_dataset(
    config_id: int,
    dataset_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    """取消标注配置与数据集的关联（需要超级用户权限）"""
    success = DatasetAnnotationConfigCRUD.disassociate(
        db=db, dataset_id=dataset_id, annotation_config_id=config_id
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="取消关联失败，请检查数据集和标注配置是否存在或是否已关联",
        )
    return {"message": "取消关联成功"}


@router.get("/{config_id}/datasets", response_model=List[Dataset])
def get_datasets_by_config(
    config_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    """获取使用指定标注配置的所有数据集（需要超级用户权限）"""
    datasets = DatasetAnnotationConfigCRUD.get_datasets_by_config(
        db=db, annotation_config_id=config_id
    )
    return datasets


@router.get("/{config_id}/results-count")
def get_config_results_count(
    config_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    """获取指定标注配置的标注结果统计信息（需要超级用户权限）"""
    # 检查配置是否存在
    config = AnnotationConfigCRUD.get_by_id(db, config_id=config_id)
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"标注配置 ID {config_id} 不存在",
        )

    # 统计标注结果数量
    results_count = AnnotationResultCRUD.count(db=db, annotation_config_id=config_id)

    # 获取关联的数据集
    datasets = DatasetAnnotationConfigCRUD.get_datasets_by_config(
        db=db, annotation_config_id=config_id
    )
    dataset_count = len(datasets)

    return {
        "count": results_count,
        "dataset_count": dataset_count,
        "datasets": [
            {"id": d.id, "name": d.name, "version": d.version} for d in datasets
        ],
    }


@router.delete("/{config_id}/results", status_code=status.HTTP_200_OK)
def clear_config_results(
    config_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    """清除指定标注配置的所有标注结果（需要超级用户权限）"""
    # 检查配置是否存在
    config = AnnotationConfigCRUD.get_by_id(db, config_id=config_id)
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"标注配置 ID {config_id} 不存在",
        )

    # 删除所有标注结果
    deleted_count = AnnotationResultCRUD.delete_by_config(
        db=db, annotation_config_id=config_id
    )

    return {
        "message": f"已清除 {deleted_count} 条标注结果",
        "deleted_count": deleted_count,
    }


@router.put("/{dataset_id}/configs", status_code=status.HTTP_200_OK)
def set_dataset_configs(
    dataset_id: int,
    config_ids: List[int],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    """设置数据集关联的标注配置（会替换现有关联，需要超级用户权限）"""
    success = DatasetAnnotationConfigCRUD.set_dataset_configs(
        db=db, dataset_id=dataset_id, annotation_config_ids=config_ids
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="设置失败，请检查数据集和标注配置是否存在",
        )
    return {"message": "设置成功"}


# ==================== 普通用户标注结果接口 ====================


@annotation_result_router.get("/", response_model=List[AnnotationResult])
def list_annotation_results(
    skip: int = 0,
    limit: int = 100,
    dataset_id: Optional[int] = None,
    dataset_item_id: Optional[int] = None,
    annotation_config_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取标注结果列表（普通用户可访问，只能看到自己的标注）"""
    return AnnotationResultCRUD.get_all(
        db=db,
        skip=skip,
        limit=limit,
        dataset_id=dataset_id,
        dataset_item_id=dataset_item_id,
        annotation_config_id=annotation_config_id,
        annotator_id=current_user.id,  # 只返回当前用户的标注
    )


@annotation_result_router.get("/{result_id}", response_model=AnnotationResult)
def get_annotation_result(
    result_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取单个标注结果（普通用户可访问，只能查看自己的标注）"""
    result = AnnotationResultCRUD.get_by_id(db, result_id=result_id)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"标注结果 ID {result_id} 不存在",
        )

    # 检查是否是当前用户的标注
    if result.annotator_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="无权访问此标注结果"
        )

    return result


@annotation_result_router.post(
    "/", response_model=AnnotationResult, status_code=status.HTTP_201_CREATED
)
def create_annotation_result(
    result: AnnotationResult,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """创建标注结果（普通用户可访问）"""
    # 自动设置标注者信息
    result.annotator_id = current_user.id
    result.annotator_name = current_user.username

    # 检查是否已存在相同的标注结果（同一用户、同一数据集项、同一配置）
    existing_results = AnnotationResultCRUD.get_all(
        db=db,
        dataset_id=result.dataset_id,
        dataset_item_id=result.dataset_item_id,
        annotation_config_id=result.annotation_config_id,
        annotator_id=current_user.id,
    )

    if existing_results:
        # 如果已存在，更新现有结果而不是创建新的
        existing_result = existing_results[0]
        result.id = existing_result.id
        return AnnotationResultCRUD.update(
            db=db, result_id=existing_result.id, result=result
        )

    return AnnotationResultCRUD.create(db=db, result=result)


@annotation_result_router.put("/{result_id}", response_model=AnnotationResult)
def update_annotation_result(
    result_id: int,
    result: AnnotationResult,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """更新标注结果（普通用户可访问，只能更新自己的标注）"""
    # 检查标注结果是否存在
    existing = AnnotationResultCRUD.get_by_id(db, result_id=result_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"标注结果 ID {result_id} 不存在",
        )

    # 检查是否是当前用户的标注
    if existing.annotator_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="无权修改此标注结果"
        )

    # 确保ID和标注者信息一致
    result.id = result_id
    result.annotator_id = current_user.id
    result.annotator_name = current_user.username

    updated = AnnotationResultCRUD.update(db=db, result_id=result_id, result=result)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"标注结果 ID {result_id} 不存在",
        )
    return updated


@annotation_result_router.delete("/{result_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_annotation_result(
    result_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """删除标注结果（普通用户可访问，只能删除自己的标注）"""
    # 检查标注结果是否存在
    existing = AnnotationResultCRUD.get_by_id(db, result_id=result_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"标注结果 ID {result_id} 不存在",
        )

    # 检查是否是当前用户的标注
    if existing.annotator_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="无权删除此标注结果"
        )

    success = AnnotationResultCRUD.delete(db=db, result_id=result_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"标注结果 ID {result_id} 不存在",
        )
    return None


@annotation_result_router.get(
    "/datasets/{dataset_id}/results", response_model=List[AnnotationResult]
)
def get_dataset_annotation_results(
    dataset_id: int,
    skip: int = 0,
    limit: int = 1000,
    dataset_item_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取数据集的所有标注结果（普通用户可访问，只能看到自己的标注）"""
    return AnnotationResultCRUD.get_all(
        db=db,
        skip=skip,
        limit=limit,
        dataset_id=dataset_id,
        dataset_item_id=dataset_item_id,
        annotator_id=current_user.id,  # 只返回当前用户的标注
    )


@annotation_result_router.get("/datasets/{dataset_id}/export")
def export_dataset_annotation_results(
    dataset_id: int,
    format: str = Query(
        "json", pattern="^(json|csv)$", description="导出格式：json 或 csv"
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    """导出数据集的标注结果（需要超级用户权限）

    支持两种格式：
    - json: JSON格式，包含完整的标注结果和QA对信息
    - csv: CSV格式，扁平化的标注结果
    """
    # 检查数据集是否存在
    from qa_annotate.database.crud import DatasetCRUD

    dataset = DatasetCRUD.get_by_id(db, dataset_id=dataset_id)
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"数据集 ID {dataset_id} 不存在",
        )

    # 获取所有标注结果（不限制用户，因为这是管理员功能）
    annotation_results = AnnotationResultCRUD.get_all(
        db=db,
        skip=0,
        limit=100000,  # 设置一个较大的限制
        dataset_id=dataset_id,
        annotator_id=None,  # 获取所有用户的标注
    )

    # 获取所有QA对
    qa_pairs = QAPairCRUD.get_by_dataset(
        db=db, dataset_id=dataset_id, skip=0, limit=100000
    )

    # 创建QA对字典以便快速查找
    qa_dict = {qa.id: qa for qa in qa_pairs}

    # 获取所有标注配置（考虑项目继承）
    configs = get_dataset_configs_with_inheritance(
        db=db, dataset_id=dataset_id, include_inherited=True
    )
    config_dict = {config.id: config for config in configs}
    # 只统计当前有效配置的标注结果，过滤掉已取消配置的标注结果
    valid_config_ids = set(c.id for c in configs)
    filtered_results = [
        r for r in annotation_results if r.annotation_config_id in valid_config_ids
    ]

    if format == "json":
        # JSON格式导出
        export_data = {
            "dataset_name": dataset.name,
            "dataset_version": dataset.version,
            "export_time": datetime.now().isoformat(),
            "total_items": len(qa_pairs),
            "total_annotations": len(filtered_results),
            "data": [],
        }

        # 按QA对组织数据
        for qa_pair in qa_pairs:
            item_data = {
                "question": qa_pair.question,
                "answer": qa_pair.answer,
                "annotations": [],
            }

            # 添加该QA对的所有标注结果（只包含有效配置的结果）
            for result in filtered_results:
                if result.dataset_item_id == qa_pair.id:
                    config = config_dict.get(result.annotation_config_id)
                    annotation_type = config.annotation_type if config else None

                    # 根据标注类型简化标注值格式，传入config以获取label
                    value_dict = result.value.model_dump()
                    simplified_value = simplify_annotation_value(
                        value_dict, annotation_type, config
                    )

                    annotation_data = {
                        "config_name": config.name if config else None,
                        "annotation_type": annotation_type,
                        "value": simplified_value,
                        "annotator_name": result.annotator_name,
                        "notes": result.notes,  # 标注理由
                        "confidence": result.confidence,  # 置信度
                    }
                    # 移除None值
                    annotation_data = {
                        k: v for k, v in annotation_data.items() if v is not None
                    }
                    item_data["annotations"].append(annotation_data)

            export_data["data"].append(item_data)

        # 转换为JSON字符串
        json_str = json.dumps(export_data, ensure_ascii=False, indent=2)

        # 创建响应
        return StreamingResponse(
            io.BytesIO(json_str.encode("utf-8")),
            media_type="application/json",
            headers={
                "Content-Disposition": f'attachment; filename="dataset_{dataset_id}_annotations_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json"'
            },
        )

    else:  # CSV格式
        # 准备CSV数据
        output = io.StringIO()
        writer = csv.writer(output)

        # 写入表头（移除ID字段）
        headers = [
            "question",
            "answer",
            "config_name",
            "annotation_type",
            "annotator_name",
            "value_type",
            "value_data",
            "notes",  # 标注理由
            "confidence",  # 置信度
        ]
        writer.writerow(headers)

        # 写入数据（只包含有效配置的结果）
        for result in filtered_results:
            qa_pair = qa_dict.get(result.dataset_item_id)
            config = config_dict.get(result.annotation_config_id)

            # 提取标注值
            value_type = None
            value_data = ""

            if result.value.score:
                value_type = "score"
                value_data = f"{result.value.score.score}"
                # 理由现在统一保存在 notes 字段中，不再从 score.reason 获取
            elif result.value.text:
                value_type = "text"
                value_data = result.value.text.text
            elif result.value.category:
                value_type = "category"
                value_data = result.value.category.category
            elif result.value.choice:
                value_type = "choice"
                value_data = ", ".join(result.value.choice.selected_options)
            elif result.value.binary:
                value_type = "binary"
                # 获取label
                binary_value = result.value.binary.value
                if (
                    config
                    and config.annotation_type == "binary"
                    and isinstance(config.config, BinaryConfig)
                ):
                    binary_config = config.config
                    if binary_value is True:
                        value_data = binary_config.true_label or "是"
                    elif binary_value is False:
                        value_data = binary_config.false_label or "否"
                    else:
                        value_data = str(binary_value)
                else:
                    value_data = "是" if binary_value is True else "否"

            row = [
                qa_pair.question if qa_pair else "",
                qa_pair.answer if qa_pair else "",
                config.name if config else "",
                config.annotation_type if config else "",
                result.annotator_name or "",
                value_type or "",
                value_data,
                result.notes or "",  # 标注理由
                result.confidence if result.confidence is not None else "",  # 置信度
            ]
            writer.writerow(row)

        # 转换为字节流
        csv_bytes = output.getvalue().encode(
            "utf-8-sig"
        )  # 使用utf-8-sig以支持Excel打开

        # 创建响应
        return StreamingResponse(
            io.BytesIO(csv_bytes),
            media_type="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="dataset_{dataset_id}_annotations_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv"'
            },
        )
