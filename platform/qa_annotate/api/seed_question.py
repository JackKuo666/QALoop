"""种子问题相关的API接口"""

import csv
import io
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from qa_annotate.api.auth import get_current_active_user, get_current_superuser
from qa_annotate.database.base import get_db
from qa_annotate.database.crud import QuestionTypeCRUD, SeedQuestionCRUD
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
from qa_annotate.schema.user import User

router = APIRouter(prefix="/seed-questions", tags=["seed-questions"])


# ==================== 普通用户接口 ====================


@router.post("/", response_model=SeedQuestion, status_code=status.HTTP_201_CREATED)
def create_seed_question(
    seed_question: SeedQuestionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """创建种子问题（所有登录用户可访问）"""
    return SeedQuestionCRUD.create(
        db=db, seed_question=seed_question, creator_id=current_user.id
    )


@router.get("/", response_model=List[SeedQuestion])
def list_seed_questions(
    skip: int = 0,
    limit: int = 100,
    type: Optional[str] = None,
    subtype: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取种子问题列表（只能看到自己创建的）"""
    return SeedQuestionCRUD.get_all(
        db=db,
        skip=skip,
        limit=limit,
        creator_id=current_user.id,  # 只返回当前用户创建的
        type=type,
        subtype=subtype,
        search=search,
    )


@router.get("/{question_id}", response_model=SeedQuestion)
def get_seed_question(
    question_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取单个种子问题（只能获取自己创建的）"""
    seed_question = SeedQuestionCRUD.get_by_id(db, question_id=question_id)
    if not seed_question:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"种子问题 ID {question_id} 不存在",
        )

    # 检查权限：只能查看自己创建的
    if seed_question.creator_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只能查看自己创建的种子问题",
        )

    return seed_question


@router.put("/{question_id}", response_model=SeedQuestion)
def update_seed_question(
    question_id: int,
    seed_question_update: SeedQuestionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """更新种子问题（只能更新自己创建的）"""
    # 检查种子问题是否存在
    existing = SeedQuestionCRUD.get_by_id(db, question_id=question_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"种子问题 ID {question_id} 不存在",
        )

    # 检查权限：只能更新自己创建的
    if existing.creator_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只能更新自己创建的种子问题",
        )

    updated = SeedQuestionCRUD.update(
        db=db, question_id=question_id, seed_question=seed_question_update
    )
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"种子问题 ID {question_id} 不存在",
        )

    return updated


@router.delete("/{question_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_seed_question(
    question_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """删除种子问题（只能删除自己创建的）"""
    # 检查种子问题是否存在
    existing = SeedQuestionCRUD.get_by_id(db, question_id=question_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"种子问题 ID {question_id} 不存在",
        )

    # 检查权限：只能删除自己创建的
    if existing.creator_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只能删除自己创建的种子问题",
        )

    success = SeedQuestionCRUD.delete(db=db, question_id=question_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"种子问题 ID {question_id} 不存在",
        )

    return None


@router.post("/import", status_code=status.HTTP_200_OK)
async def import_seed_questions_from_csv(
    file: UploadFile = File(..., description="CSV文件"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """批量导入种子问题（从CSV文件）"""
    # 检查文件类型
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="只支持.csv格式的文件"
        )

    # 读取文件内容
    try:
        content = await file.read()
        # 尝试使用utf-8-sig解码（支持Excel导出的CSV）
        try:
            text_content = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            text_content = content.decode("utf-8")
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"读取文件失败: {str(e)}"
        )

    # 解析CSV文件
    try:
        csv_reader = csv.DictReader(io.StringIO(text_content))
        rows = list(csv_reader)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"解析CSV文件失败: {str(e)}"
        )

    if not rows:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="CSV文件为空或格式不正确"
        )

    # 验证必需的列
    required_columns = [
        "种子问题",
        "类型",
        "亚类",
        "物种/领域",
        "模型",
        "日期",
        "是否核验",
    ]
    for col in required_columns:
        if col not in csv_reader.fieldnames:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"CSV文件缺少必需的列: {col}",
            )

    imported_count = 0
    failed_count = 0
    errors = []
    seed_questions_to_create = []

    for row_num, row in enumerate(rows, start=2):  # 从第2行开始（第1行是标题）
        try:
            # 提取必需字段
            question = row.get("种子问题", "").strip()
            type_name = row.get("类型", "").strip()
            subtype = row.get("亚类", "").strip()
            species_or_domain = row.get("物种/领域", "").strip()
            model = row.get("模型", "").strip()
            date_str = row.get("日期", "").strip()
            verified_str = row.get("是否核验", "").strip()

            # 验证必需字段
            if not question:
                errors.append(f"第{row_num}行: 种子问题不能为空")
                failed_count += 1
                continue

            if not type_name:
                errors.append(f"第{row_num}行: 类型不能为空")
                failed_count += 1
                continue

            if not subtype:
                errors.append(f"第{row_num}行: 亚类不能为空")
                failed_count += 1
                continue

            if not species_or_domain:
                errors.append(f"第{row_num}行: 物种/领域不能为空")
                failed_count += 1
                continue

            if not model:
                errors.append(f"第{row_num}行: 模型不能为空")
                failed_count += 1
                continue

            if not date_str:
                errors.append(f"第{row_num}行: 日期不能为空")
                failed_count += 1
                continue

            # 处理日期字段（格式：YYYYMMDD或YYYY-MM-DD）
            date_value = None
            try:
                # 尝试解析YYYYMMDD格式
                if len(date_str) == 8 and date_str.isdigit():
                    date_value = datetime.strptime(date_str, "%Y%m%d").date()
                else:
                    # 尝试其他常见格式
                    date_value = datetime.strptime(date_str, "%Y-%m-%d").date()
            except ValueError:
                errors.append(
                    f"第{row_num}行: 日期格式不正确，应为YYYYMMDD或YYYY-MM-DD"
                )
                failed_count += 1
                continue

            # 处理是否核验字段（是/否 -> True/False）
            if not verified_str:
                errors.append(f"第{row_num}行: 是否核验不能为空")
                failed_count += 1
                continue

            verified_str_lower = verified_str.lower()
            if verified_str_lower in ["是", "yes", "true", "1"]:
                is_verified = True
            elif verified_str_lower in ["否", "no", "false", "0"]:
                is_verified = False
            else:
                errors.append(
                    f"第{row_num}行: 是否核验格式不正确，应为：是/否/yes/no/true/false/1/0"
                )
                failed_count += 1
                continue

            # 创建SeedQuestionCreate对象
            seed_question = SeedQuestionCreate(
                question=question,
                type=type_name,
                subtype=subtype,
                species_or_domain=species_or_domain,
                model=model,
                date=date_value,
                is_verified=is_verified,
            )

            seed_questions_to_create.append(seed_question)

        except Exception as e:
            errors.append(f"第{row_num}行: 处理失败 - {str(e)}")
            failed_count += 1
            continue

    # 批量创建种子问题
    if seed_questions_to_create:
        try:
            created_questions = SeedQuestionCRUD.create_batch(
                db=db,
                seed_questions=seed_questions_to_create,
                creator_id=current_user.id,
            )
            imported_count = len(created_questions)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"批量创建种子问题失败: {str(e)}",
            )

    return {
        "imported_count": imported_count,
        "failed_count": failed_count,
        "total_rows": len(rows),
        "errors": errors[:50],  # 最多返回50个错误
    }


@router.get("/options/types")
def get_question_type_options(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取类型和亚类选项（从数据库读取）"""
    grouped = QuestionTypeCRUD.get_all_grouped(db=db)
    return grouped


# ==================== 管理员接口 ====================


@router.get("/admin/all", response_model=List[SeedQuestionWithCreator])
def list_all_seed_questions(
    skip: int = 0,
    limit: int = 100,
    type: Optional[str] = None,
    subtype: Optional[str] = None,
    search: Optional[str] = None,
    creator_id: Optional[int] = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_superuser),
):
    """获取所有种子问题（管理员，包含创建者全名）"""
    return SeedQuestionCRUD.get_all_with_creator(
        db=db,
        skip=skip,
        limit=limit,
        creator_id=creator_id,
        type=type,
        subtype=subtype,
        search=search,
    )


@router.get("/admin/export")
def export_all_seed_questions(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_superuser),
):
    """导出所有种子问题（CSV格式，管理员）"""
    # 获取所有种子问题
    all_questions = SeedQuestionCRUD.export_all(db=db)

    # 创建CSV内容
    output = io.StringIO()
    writer = csv.writer(output)

    # 写入标题行
    writer.writerow(
        [
            "ID",
            "种子问题",
            "类型",
            "亚类",
            "物种/领域",
            "模型",
            "日期",
            "是否核验",
            "创建者全名",
            "创建时间",
            "更新时间",
        ]
    )

    # 写入数据行
    for question in all_questions:
        writer.writerow(
            [
                question.id,
                question.question,
                question.type,
                question.subtype,
                question.species_or_domain or "",
                question.model or "",
                question.date.strftime("%Y-%m-%d") if question.date else "",
                "是" if question.is_verified else "否",
                question.creator_full_name or f"用户ID:{question.creator_id}",
                question.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                question.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
            ]
        )

    # 设置响应头
    output.seek(0)
    csv_content = output.getvalue()
    csv_bytes = csv_content.encode("utf-8-sig")  # 使用utf-8-sig以支持Excel打开
    return StreamingResponse(
        io.BytesIO(csv_bytes),
        media_type="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=seed_questions_export.csv"
        },
    )


@router.post(
    "/admin/types", response_model=QuestionType, status_code=status.HTTP_201_CREATED
)
def create_question_type(
    question_type: QuestionTypeCreate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_superuser),
):
    """创建类型/亚类（管理员）"""
    # 检查是否已存在
    existing = QuestionTypeCRUD.get_by_type_subtype(
        db=db, type=question_type.type, subtype=question_type.subtype
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"类型 '{question_type.type}' 和亚类 '{question_type.subtype}' 已存在",
        )

    return QuestionTypeCRUD.create(db=db, question_type=question_type)


@router.get("/admin/types", response_model=List[QuestionType])
def list_question_types(
    skip: int = 0,
    limit: int = 1000,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_superuser),
):
    """获取所有类型/亚类（管理员）"""
    return QuestionTypeCRUD.get_all(db=db, skip=skip, limit=limit)


@router.put("/admin/types/{type_id}", response_model=QuestionType)
def update_question_type(
    type_id: int,
    question_type_update: QuestionTypeUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_superuser),
):
    """更新类型/亚类（管理员）"""
    # 检查是否存在
    existing = QuestionTypeCRUD.get_by_id(db, type_id=type_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"类型 ID {type_id} 不存在",
        )

    updated = QuestionTypeCRUD.update(
        db=db, type_id=type_id, question_type_update=question_type_update
    )
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="更新失败，可能是类型和亚类组合已存在",
        )

    return updated


@router.delete("/admin/types/{type_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_question_type(
    type_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_superuser),
):
    """删除类型/亚类（管理员）"""
    # 检查是否存在
    existing = QuestionTypeCRUD.get_by_id(db, type_id=type_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"类型 ID {type_id} 不存在",
        )

    success = QuestionTypeCRUD.delete(db=db, type_id=type_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"类型 ID {type_id} 不存在",
        )

    return None
