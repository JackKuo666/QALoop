"""项目相关的API接口"""

import csv
import io
import json
import re
import zipfile
from datetime import datetime
from typing import List, Optional
from urllib.parse import quote

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from qa_annotate.api.annotation import simplify_annotation_value
from qa_annotate.api.auth import get_current_superuser
from qa_annotate.api.dataset import (
    get_dataset_configs_with_inheritance,
    import_dataset_from_file,
)
from qa_annotate.database.base import get_db
from qa_annotate.database.crud import (
    AnnotationResultCRUD,
    DatasetCRUD,
    ProjectAnnotationConfigCRUD,
    ProjectCRUD,
    QAPairCRUD,
)
from qa_annotate.schema.annotation import AnnotationConfig, BinaryConfig
from qa_annotate.schema.dataset import Dataset
from qa_annotate.schema.project import Project
from qa_annotate.schema.user import User

router = APIRouter(prefix="/projects", tags=["projects"])


def sanitize_filename(name: str) -> str:
    """清理文件名，移除或替换不合法字符"""
    # 移除或替换Windows/Linux不支持的字符
    invalid_chars = r'[<>:"/\\|?*]'
    sanitized = re.sub(invalid_chars, "_", name)
    # 移除前后空格和点
    sanitized = sanitized.strip(". ")
    # 限制长度
    if len(sanitized) > 200:
        sanitized = sanitized[:200]
    return sanitized if sanitized else "dataset"


def generate_dataset_export(
    dataset_id: int, format: str, db: Session
) -> tuple[bytes, str]:
    """生成单个数据集的导出内容

    返回: (文件内容字节, 文件名)
    """
    dataset = DatasetCRUD.get_by_id(db, dataset_id=dataset_id)
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"数据集 ID {dataset_id} 不存在",
        )

    # 获取所有标注结果
    annotation_results = AnnotationResultCRUD.get_all(
        db=db,
        skip=0,
        limit=100000,
        dataset_id=dataset_id,
        annotator_id=None,
    )

    # 获取所有QA对
    qa_pairs = QAPairCRUD.get_by_dataset(
        db=db, dataset_id=dataset_id, skip=0, limit=100000
    )

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
        export_data = {
            "dataset_name": dataset.name,
            "dataset_version": dataset.version,
            "export_time": datetime.now().isoformat(),
            "total_items": len(qa_pairs),
            "total_annotations": len(filtered_results),
            "data": [],
        }

        for qa_pair in qa_pairs:
            item_data = {
                "question": qa_pair.question,
                "answer": qa_pair.answer,
                "annotations": [],
            }

            # 只包含有效配置的标注结果
            for result in filtered_results:
                if result.dataset_item_id == qa_pair.id:
                    config = config_dict.get(result.annotation_config_id)
                    annotation_type = config.annotation_type if config else None

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
                    annotation_data = {
                        k: v for k, v in annotation_data.items() if v is not None
                    }
                    item_data["annotations"].append(annotation_data)

            export_data["data"].append(item_data)

        json_str = json.dumps(export_data, ensure_ascii=False, indent=2)
        filename = f"{sanitize_filename(dataset.name)}.json"
        return json_str.encode("utf-8"), filename

    else:  # CSV格式
        output = io.StringIO()
        writer = csv.writer(output)

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

        # 只包含有效配置的标注结果
        for result in filtered_results:
            qa_pair = qa_dict.get(result.dataset_item_id)
            config = config_dict.get(result.annotation_config_id)

            value_type = None
            value_data = ""

            if result.value.score:
                value_type = "score"
                value_data = f"{result.value.score.score}"
                if result.value.score.reason:
                    value_data += f" (理由: {result.value.score.reason})"
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

        csv_bytes = output.getvalue().encode("utf-8-sig")
        filename = f"{sanitize_filename(dataset.name)}.csv"
        return csv_bytes, filename


@router.post("/", response_model=Project, status_code=status.HTTP_201_CREATED)
def create_project(
    project: Project,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    """创建项目（需要超级用户权限）"""
    # 如果提供了ID，检查是否已存在
    if project.id is not None:
        existing = ProjectCRUD.get_by_id(db, project_id=project.id)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"项目 ID {project.id} 已存在",
            )

    # 验证必填字段
    if not project.description or not project.description.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="任务描述不能为空",
        )

    # 确保metadata字段存在
    if project.metadata is None:
        project.metadata = {}

    # 验证评估目的
    evaluation_purpose = (
        project.metadata.get("evaluation_purpose") if project.metadata else None
    )
    if not evaluation_purpose or not str(evaluation_purpose).strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="评估目的不能为空",
        )

    # 验证完成时间
    deadline = project.metadata.get("deadline") if project.metadata else None
    if not deadline:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="要求完成时间不能为空",
        )

    deadline_str = str(deadline).strip()
    # 检查是否包含时间部分（必须包含冒号，表示有小时:分钟）
    if ":" not in deadline_str:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="要求完成时间必须包含具体时间（格式：YYYY-MM-DDTHH:mm 或 YYYY-MM-DD HH:mm）",
        )

    # 尝试解析时间格式
    try:
        # 支持两种格式：YYYY-MM-DDTHH:mm 和 YYYY-MM-DD HH:mm
        if "T" in deadline_str:
            datetime.strptime(deadline_str, "%Y-%m-%dT%H:%M")
        else:
            datetime.strptime(deadline_str, "%Y-%m-%d %H:%M")
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="要求完成时间格式错误，请使用格式：YYYY-MM-DDTHH:mm 或 YYYY-MM-DD HH:mm",
        )

    # 统一转换为 ISO 8601 格式（YYYY-MM-DDTHH:mm）
    if "T" not in deadline_str:
        deadline_str = deadline_str.replace(" ", "T")
    project.metadata["deadline"] = deadline_str

    # 设置创建者信息
    if not project.creator_id:
        project.creator_id = current_user.id
    if not project.creator:
        project.creator = current_user.username

    return ProjectCRUD.create(db=db, project=project)


@router.get("/", response_model=List[Project])
def list_projects(
    skip: int = 0,
    limit: int = 100,
    name_search: Optional[str] = None,
    category: Optional[str] = None,
    status: Optional[str] = None,
    order_by: Optional[str] = "created_at",
    order: Optional[str] = "desc",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    """获取项目列表（需要超级用户权限）"""
    return ProjectCRUD.get_all(
        db=db,
        skip=skip,
        limit=limit,
        name_search=name_search,
        category=category,
        status=status,
        order_by=order_by,
        order=order,
    )


@router.get("/{project_id}", response_model=Project)
def get_project(
    project_id: int,
    include_datasets: bool = False,
    include_configs: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    """根据ID获取项目（需要超级用户权限）"""
    project = ProjectCRUD.get_by_id(db, project_id=project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"项目 ID {project_id} 不存在",
        )

    # 如果需要包含数据集和配置，则加载
    if include_datasets or include_configs:
        from qa_annotate.database.models import ProjectModel

        db_project = (
            db.query(ProjectModel).filter(ProjectModel.id == project_id).first()
        )
        if include_datasets:
            project.datasets = [d.to_pydantic() for d in db_project.datasets]
        if include_configs:
            project.annotation_configs = [
                c.to_pydantic() for c in db_project.annotation_configs
            ]

    return project


@router.put("/{project_id}", response_model=Project)
def update_project(
    project_id: int,
    project: Project,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    """更新项目（需要超级用户权限）"""
    # 检查项目是否存在
    existing = ProjectCRUD.get_by_id(db, project_id=project_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"项目 ID {project_id} 不存在",
        )

    # 验证必填字段
    if not project.description or not project.description.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="任务描述不能为空",
        )

    # 确保metadata字段存在
    if project.metadata is None:
        project.metadata = {}

    # 验证评估目的
    evaluation_purpose = (
        project.metadata.get("evaluation_purpose") if project.metadata else None
    )
    if not evaluation_purpose or not str(evaluation_purpose).strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="评估目的不能为空",
        )

    # 验证完成时间
    deadline = project.metadata.get("deadline") if project.metadata else None
    if not deadline:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="要求完成时间不能为空",
        )

    deadline_str = str(deadline).strip()
    # 检查是否包含时间部分（必须包含冒号，表示有小时:分钟）
    if ":" not in deadline_str:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="要求完成时间必须包含具体时间（格式：YYYY-MM-DDTHH:mm 或 YYYY-MM-DD HH:mm）",
        )

    # 尝试解析时间格式
    try:
        # 支持两种格式：YYYY-MM-DDTHH:mm 和 YYYY-MM-DD HH:mm
        if "T" in deadline_str:
            datetime.strptime(deadline_str, "%Y-%m-%dT%H:%M")
        else:
            datetime.strptime(deadline_str, "%Y-%m-%d %H:%M")
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="要求完成时间格式错误，请使用格式：YYYY-MM-DDTHH:mm 或 YYYY-MM-DD HH:mm",
        )

    # 统一转换为 ISO 8601 格式（YYYY-MM-DDTHH:mm）
    if "T" not in deadline_str:
        deadline_str = deadline_str.replace(" ", "T")
    project.metadata["deadline"] = deadline_str

    # 确保ID一致
    project.id = project_id

    updated = ProjectCRUD.update(db=db, project_id=project_id, project=project)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"项目 ID {project_id} 不存在",
        )
    return updated


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    """删除项目（需要超级用户权限，数据集的project_id会设为NULL）"""
    success = ProjectCRUD.delete(db=db, project_id=project_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"项目 ID {project_id} 不存在",
        )
    return None


@router.get("/{project_id}/datasets", response_model=List[Dataset])
def list_project_datasets(
    project_id: int,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    """获取项目下的所有数据集（需要超级用户权限）"""
    # 检查项目是否存在
    project = ProjectCRUD.get_by_id(db, project_id=project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"项目 ID {project_id} 不存在",
        )

    return ProjectCRUD.get_datasets_by_project(
        db=db, project_id=project_id, skip=skip, limit=limit
    )


@router.post(
    "/{project_id}/datasets/{dataset_id}",
    status_code=status.HTTP_200_OK,
)
def add_dataset_to_project(
    project_id: int,
    dataset_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    """将数据集添加到项目（需要超级用户权限）"""
    # 检查项目是否存在
    project = ProjectCRUD.get_by_id(db, project_id=project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"项目 ID {project_id} 不存在",
        )

    # 检查数据集是否存在

    dataset = DatasetCRUD.get_by_id(db, dataset_id=dataset_id)
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"数据集 ID {dataset_id} 不存在",
        )

    success = ProjectCRUD.add_dataset_to_project(
        db=db, project_id=project_id, dataset_id=dataset_id
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="无法将数据集添加到项目",
        )

    return {"message": "数据集已添加到项目"}


@router.delete(
    "/{project_id}/datasets/{dataset_id}",
    status_code=status.HTTP_200_OK,
)
def remove_dataset_from_project(
    project_id: int,
    dataset_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    """从项目移除数据集（需要超级用户权限）"""
    # 检查项目是否存在
    project = ProjectCRUD.get_by_id(db, project_id=project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"项目 ID {project_id} 不存在",
        )

    success = ProjectCRUD.remove_dataset_from_project(
        db=db, project_id=project_id, dataset_id=dataset_id
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="无法从项目移除数据集（数据集可能不属于该项目）",
        )

    return {"message": "数据集已从项目移除"}


@router.get("/{project_id}/configs", response_model=List[AnnotationConfig])
def get_project_configs(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    """获取项目关联的所有标注配置（需要超级用户权限）"""
    # 检查项目是否存在
    project = ProjectCRUD.get_by_id(db, project_id=project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"项目 ID {project_id} 不存在",
        )

    return ProjectAnnotationConfigCRUD.get_configs_by_project(
        db=db, project_id=project_id
    )


@router.post(
    "/{project_id}/configs/{config_id}",
    status_code=status.HTTP_200_OK,
)
def add_config_to_project(
    project_id: int,
    config_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    """将标注配置添加到项目（需要超级用户权限）"""
    # 检查项目是否存在
    project = ProjectCRUD.get_by_id(db, project_id=project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"项目 ID {project_id} 不存在",
        )

    success = ProjectAnnotationConfigCRUD.associate(
        db=db, project_id=project_id, annotation_config_id=config_id
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="无法将标注配置添加到项目（配置可能不存在或已删除）",
        )

    return {"message": "标注配置已添加到项目"}


@router.delete(
    "/{project_id}/configs/{config_id}",
    status_code=status.HTTP_200_OK,
)
def remove_config_from_project(
    project_id: int,
    config_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    """从项目移除标注配置（需要超级用户权限）"""
    # 检查项目是否存在
    project = ProjectCRUD.get_by_id(db, project_id=project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"项目 ID {project_id} 不存在",
        )

    success = ProjectAnnotationConfigCRUD.disassociate(
        db=db, project_id=project_id, annotation_config_id=config_id
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="无法从项目移除标注配置（配置可能不属于该项目）",
        )

    return {"message": "标注配置已从项目移除"}


@router.post(
    "/{project_id}/configs/{config_id}/move",
    status_code=status.HTTP_200_OK,
)
def move_config_order(
    project_id: int,
    config_id: int,
    direction: str = Query(..., description="移动方向: 'up' 上移, 'down' 下移"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    """调整配置在项目中的顺序（需要超级用户权限）

    direction: "up" 表示上移（order减1），"down" 表示下移（order加1）
    """
    # 检查项目是否存在
    project = ProjectCRUD.get_by_id(db, project_id=project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"项目 ID {project_id} 不存在",
        )

    # 获取所有配置及其顺序
    configs = ProjectAnnotationConfigCRUD.get_configs_by_project(
        db=db, project_id=project_id
    )

    # 找到当前配置的索引
    current_index = None
    for i, config in enumerate(configs):
        if config.id == config_id:
            current_index = i
            break

    if current_index is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"配置 ID {config_id} 不属于项目 ID {project_id}",
        )

    # 确定要交换的配置
    if direction == "up":
        if current_index == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="已经是第一个，无法上移",
            )
        swap_config_id = configs[current_index - 1].id
    elif direction == "down":
        if current_index == len(configs) - 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="已经是最后一个，无法下移",
            )
        swap_config_id = configs[current_index + 1].id
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="direction 必须是 'up' 或 'down'",
        )

    # 交换顺序
    success = ProjectAnnotationConfigCRUD.swap_config_order(
        db=db,
        project_id=project_id,
        config_id1=config_id,
        config_id2=swap_config_id,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="调整顺序失败",
        )

    return {"message": "顺序调整成功"}


@router.get("/{project_id}/stats")
def get_project_stats(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    """获取项目的统计信息（需要超级用户权限）"""
    # 检查项目是否存在
    project = ProjectCRUD.get_by_id(db, project_id=project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"项目 ID {project_id} 不存在",
        )

    datasets_count = ProjectCRUD.count_datasets_by_project(db=db, project_id=project_id)
    configs_count = ProjectAnnotationConfigCRUD.count_configs_by_project(
        db=db, project_id=project_id
    )

    return {
        "project_id": project_id,
        "datasets_count": datasets_count,
        "configs_count": configs_count,
    }


@router.post("/import")
async def import_project(
    files: List[UploadFile] = File(..., description="JSONL文件列表"),
    project_id: Optional[int] = Form(
        None, description="项目ID（如果提供，则导入到现有项目；否则创建新项目）"
    ),
    project_name: Optional[str] = Form(
        None, description="项目名称（创建新项目时必填）"
    ),
    project_description: Optional[str] = Form(
        None, description="项目描述（创建新项目时必填）"
    ),
    project_version: Optional[str] = Form(None, description="项目版本"),
    project_status: Optional[str] = Form(None, description="项目状态"),
    project_tags: Optional[str] = Form(None, description="项目标签（逗号分隔）"),
    project_category: Optional[str] = Form(None, description="项目分类"),
    project_source: Optional[str] = Form(None, description="项目数据来源"),
    project_source_url: Optional[str] = Form(None, description="项目数据来源URL"),
    project_evaluation_purpose: Optional[str] = Form(
        None, description="评估目的（保存在metadata中，创建新项目时必填）"
    ),
    project_deadline: Optional[str] = Form(
        None,
        description="完成时间（保存在metadata中，格式：YYYY-MM-DDTHH:mm，创建新项目时必填）",
    ),
    dataset_name_prefix: Optional[str] = Form(
        None, description="数据集名称前缀（默认为项目名称）"
    ),
    dataset_name_mapping: Optional[str] = Form(
        None,
        description="数据集名称映射（JSON格式，键为文件名，值为数据集名称）",
    ),
    annotator_id: Optional[int] = Form(None, description="标注者ID"),
    response: Response = Response(),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    """从多个JSONL文件导入项目（需要超级用户权限）

    支持两种模式：
    1. 创建新项目：提供项目名称和其他元数据，创建新项目并导入数据集
    2. 导入到现有项目：提供project_id，将数据集导入到现有项目

    数据集命名规则：
    - 如果提供了dataset_name_mapping，使用映射中的名称
    - 否则使用 {dataset_name_prefix}_{filename} 格式
    - 如果未提供dataset_name_prefix，使用项目名称作为前缀
    """
    # 验证文件
    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="至少需要上传一个文件"
        )

    for file in files:
        if not file.filename or not file.filename.endswith(".jsonl"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"文件 {file.filename} 不是.jsonl格式",
            )

    # 解析数据集名称映射
    name_mapping = {}
    if dataset_name_mapping:
        try:
            name_mapping = json.loads(dataset_name_mapping)
            if not isinstance(name_mapping, dict):
                raise ValueError("dataset_name_mapping必须是JSON对象")
        except (json.JSONDecodeError, ValueError) as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"数据集名称映射格式错误: {str(e)}",
            )

    # 处理项目
    if project_id:
        # 导入到现有项目
        project = ProjectCRUD.get_by_id(db, project_id=project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"项目 ID {project_id} 不存在",
            )
        final_project_id = project_id
        project_name_for_prefix = project.name
    else:
        # 创建新项目
        if not project_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="创建新项目时，项目名称不能为空",
            )

        # 验证必填字段
        if not project_description or not project_description.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="创建新项目时，任务描述不能为空",
            )

        if not project_evaluation_purpose or not project_evaluation_purpose.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="创建新项目时，评估目的不能为空",
            )

        if not project_deadline or not project_deadline.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="创建新项目时，要求完成时间不能为空",
            )

        # 验证完成时间格式必须包含具体时间（YYYY-MM-DDTHH:mm 或 YYYY-MM-DD HH:mm）
        deadline_stripped = project_deadline.strip()
        # 检查是否包含时间部分（必须包含冒号，表示有小时:分钟）
        if ":" not in deadline_stripped:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="要求完成时间必须包含具体时间（格式：YYYY-MM-DDTHH:mm 或 YYYY-MM-DD HH:mm）",
            )

        # 尝试解析时间格式
        try:
            # 支持两种格式：YYYY-MM-DDTHH:mm 和 YYYY-MM-DD HH:mm
            if "T" in deadline_stripped:
                datetime.strptime(deadline_stripped, "%Y-%m-%dT%H:%M")
            else:
                datetime.strptime(deadline_stripped, "%Y-%m-%d %H:%M")
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="要求完成时间格式错误，请使用格式：YYYY-MM-DDTHH:mm 或 YYYY-MM-DD HH:mm",
            )

        # 检查项目名称是否已存在
        existing_project = ProjectCRUD.get_by_name(db, name=project_name)
        if existing_project:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"项目名称 '{project_name}' 已存在",
            )

        # 构建元数据
        metadata = {}
        metadata["evaluation_purpose"] = project_evaluation_purpose.strip()
        # 统一转换为 ISO 8601 格式（YYYY-MM-DDTHH:mm）
        if "T" in deadline_stripped:
            metadata["deadline"] = deadline_stripped
        else:
            # 将空格替换为 T
            metadata["deadline"] = deadline_stripped.replace(" ", "T")

        # 构建项目数据
        project_data = {
            "name": project_name,
            "description": project_description,
            "version": project_version,
            "status": project_status or "active",
            "category": project_category,
            "tags": (
                [tag.strip() for tag in project_tags.split(",") if tag.strip()]
                if project_tags
                else None
            ),
            "source": project_source,
            "source_url": project_source_url,
            "metadata": metadata if metadata else None,
        }
        project = Project(**project_data)
        project.creator_id = current_user.id
        project.creator = current_user.username
        created_project = ProjectCRUD.create(db=db, project=project)
        final_project_id = created_project.id
        project_name_for_prefix = project_name

    # 确定数据集名称前缀
    prefix = dataset_name_prefix or project_name_for_prefix

    # 导入每个文件
    results = []
    total_imported = 0
    total_failed = 0
    all_errors = []

    for file in files:
        # 确定数据集名称
        filename_without_ext = file.filename.replace(".jsonl", "").replace(".json", "")
        if file.filename in name_mapping:
            dataset_name = name_mapping[file.filename]
        else:
            dataset_name = f"{prefix}_{filename_without_ext}"

        try:
            # 导入数据集
            result = await import_dataset_from_file(
                file=file,
                db=db,
                current_user=current_user,
                dataset_name=dataset_name,
                project_id=final_project_id,
                annotator_id=annotator_id,
            )

            # 确保数据集已添加到项目（通过project_id已经关联，但为了保险起见）
            if result["dataset_id"]:
                ProjectCRUD.add_dataset_to_project(
                    db=db, project_id=final_project_id, dataset_id=result["dataset_id"]
                )

            results.append(
                {
                    "filename": file.filename,
                    "dataset_name": result["dataset_name"],
                    "dataset_id": result["dataset_id"],
                    "imported_count": result["imported_count"],
                    "failed_count": result["failed_count"],
                    "total_lines": result["total_lines"],
                    "errors": result["errors"],
                    "success": True,
                }
            )
            total_imported += result["imported_count"]
            total_failed += result["failed_count"]
            if result["errors"]:
                all_errors.extend(
                    [f"{file.filename}: {err}" for err in result["errors"]]
                )

        except Exception as e:
            results.append(
                {
                    "filename": file.filename,
                    "dataset_name": dataset_name,
                    "success": False,
                    "error": str(e),
                }
            )
            all_errors.append(f"{file.filename}: {str(e)}")

    # 根据是否创建了新项目设置HTTP状态码
    if project_id is None:
        # 创建了新项目，返回201 Created
        response.status_code = status.HTTP_201_CREATED
    else:
        # 导入到现有项目，返回200 OK
        response.status_code = status.HTTP_200_OK

    return {
        "project_id": final_project_id,
        "project_name": project_name_for_prefix,
        "created": project_id is None,
        "total_files": len(files),
        "successful_files": len([r for r in results if r.get("success", False)]),
        "failed_files": len([r for r in results if not r.get("success", False)]),
        "total_imported": total_imported,
        "total_failed": total_failed,
        "file_results": results,
        "errors": all_errors[:50],  # 只返回前50个错误
    }


@router.get("/{project_id}/export-annotations")
def export_project_annotations(
    project_id: int,
    format: str = Query(
        "json", pattern="^(json|csv)$", description="导出格式：json 或 csv"
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    """导出项目下所有数据集的标注结果（需要超级用户权限）

    支持两种格式：
    - json: JSON格式，包含完整的标注结果和QA对信息
    - csv: CSV格式，扁平化的标注结果

    返回一个ZIP文件，包含项目下所有数据集的标注文件，每个文件使用数据集名称命名。
    """
    # 检查项目是否存在
    project = ProjectCRUD.get_by_id(db, project_id=project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"项目 ID {project_id} 不存在",
        )

    # 获取项目下的所有数据集
    datasets = ProjectCRUD.get_datasets_by_project(
        db=db, project_id=project_id, skip=0, limit=10000
    )

    if not datasets:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"项目 ID {project_id} 下没有数据集",
        )

    # 创建ZIP文件
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for dataset in datasets:
            try:
                # 生成每个数据集的导出内容
                content, filename = generate_dataset_export(
                    dataset_id=dataset.id, format=format, db=db
                )
                # 添加到ZIP文件
                zip_file.writestr(filename, content)
            except Exception as e:
                # 如果某个数据集导出失败，记录错误但继续处理其他数据集
                error_filename = f"{sanitize_filename(dataset.name)}_error.txt"
                error_msg = f"导出失败: {str(e)}"
                zip_file.writestr(error_filename, error_msg.encode("utf-8"))

    zip_buffer.seek(0)

    # 生成ZIP文件名
    project_name_sanitized = sanitize_filename(project.name)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_filename = f"{project_name_sanitized}_annotations_{timestamp}.zip"

    # 编码文件名以支持中文字符（RFC 5987标准）
    # 使用ASCII安全的文件名作为fallback，UTF-8编码的文件名作为主要值
    filename_ascii = (
        zip_filename.encode("ascii", "ignore").decode("ascii")
        or f"project_{project_id}_annotations_{timestamp}.zip"
    )
    filename_encoded = quote(zip_filename, safe="")

    # 返回ZIP文件流
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename=\"{filename_ascii}\"; filename*=UTF-8''{filename_encoded}"
        },
    )
