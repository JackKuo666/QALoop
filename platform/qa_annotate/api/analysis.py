"""标注结果分析API"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from qa_annotate.api.auth import get_current_superuser
from qa_annotate.database.base import get_db
from qa_annotate.database.crud import AnnotationResultAnalysisCRUD, LlmAnalysisCacheCRUD
from qa_annotate.schema.annotation import ProjectAnnotationAnalysis
from qa_annotate.schema.user import User
from qa_annotate.services.llm_service import (
    build_notes_analysis_prompt,
    call_llm_chat,
    get_llm_config,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analysis", tags=["analysis"])


class LlmAnalysisResponse(BaseModel):
    analysis: str
    model_name: str
    notes_count: int


class CachedAnalysisResponse(BaseModel):
    analysis: str
    model_name: str
    notes_count: int
    created_at: str | None = None
    updated_at: str | None = None


class LlmTestResponse(BaseModel):
    success: bool
    message: str
    model_name: str | None = None


@router.get(
    "/projects/{project_id}/annotation-stats",
    response_model=ProjectAnnotationAnalysis,
)
def get_project_annotation_stats(
    project_id: int,
    db: Session = Depends(get_db),
):
    """获取项目的标注结果统计分析

    返回项目下所有数据集的标注结果统计，包括：
    - 总体统计：数据集数、QA对数、标注数、完成率
    - 按配置统计：每个标注配置的详细统计
    - Notes汇总：所有标注理由
    """
    stats = AnnotationResultAnalysisCRUD.get_project_annotation_stats(db, project_id)

    if not stats:
        raise HTTPException(status_code=404, detail="项目不存在")

    return stats


@router.post(
    "/projects/{project_id}/analyze-notes", response_model=LlmAnalysisResponse
)
async def analyze_notes_with_llm(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
    lang: str = Query("zh", description="Output language: zh or en"),
):
    """使用 LLM 分析标注备注

    需要 superuser 权限。
    """
    # 获取 LLM 配置
    llm_config = get_llm_config(db)
    api_key = llm_config.get("api_key")
    base_url = llm_config.get("base_url")
    model_name = llm_config.get("model_name")

    if not api_key or not base_url or not model_name:
        raise HTTPException(
            status_code=400,
            detail="请先在系统配置中配置 LLM API Key、Base URL 和 Model Name",
        )

    # 获取统计数据和 notes
    stats = AnnotationResultAnalysisCRUD.get_project_annotation_stats(db, project_id)
    if not stats:
        raise HTTPException(status_code=404, detail="项目不存在")

    # stats 是 dict
    notes_summary = stats.get("notes_summary", []) if isinstance(stats, dict) else []
    if not notes_summary or len(notes_summary) == 0:
        raise HTTPException(status_code=400, detail="暂无标注备注可供分析")

    # 计算总备注数
    total_notes = sum(
        item["count"] if isinstance(item, dict) else item.count
        for item in notes_summary
    )
    notes_data = [
        {
            "config_name": item["config_name"] if isinstance(item, dict) else item.config_name,
            "count": item["count"] if isinstance(item, dict) else item.count,
            "notes": item["notes"] if isinstance(item, dict) else item.notes,
        }
        for item in notes_summary
    ]

    # 构造 prompt（传入完整统计信息 + 备注）
    stats_dict = stats if isinstance(stats, dict) else {}
    system_prompt, user_message = build_notes_analysis_prompt(notes_data, stats=stats_dict, language=lang)

    # 调用 LLM
    try:
        analysis = await call_llm_chat(
            api_key=api_key,
            base_url=base_url,
            model_name=model_name,
            system_prompt=system_prompt,
            user_message=user_message,
        )
    except Exception as e:
        logger.error(f"LLM API 调用失败: {e}")
        raise HTTPException(
            status_code=502, detail=f"LLM API 调用失败: {e}"
        ) from e

    # 保存到缓存
    try:
        LlmAnalysisCacheCRUD.save(
            db=db,
            project_id=project_id,
            analysis_text=analysis,
            model_name=model_name,
            notes_count=total_notes,
            language=lang,
        )
    except Exception as e:
        logger.warning(f"保存分析缓存失败（不影响返回结果）: {e}")

    return LlmAnalysisResponse(
        analysis=analysis,
        model_name=model_name,
        notes_count=total_notes,
    )


@router.get("/projects/{project_id}/cached-analysis")
def get_cached_analysis(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    """获取项目缓存的 LLM 分析报告

    需要 superuser 权限。
    """
    cached = LlmAnalysisCacheCRUD.get_by_project(db, project_id)
    if not cached:
        raise HTTPException(status_code=404, detail="暂无缓存的分析报告")

    return CachedAnalysisResponse(
        analysis=cached["analysis"],
        model_name=cached["model_name"],
        notes_count=cached["notes_count"],
        created_at=cached["created_at"].isoformat() if cached["created_at"] else None,
        updated_at=cached["updated_at"].isoformat() if cached["updated_at"] else None,
    )


@router.post("/test-llm-connection", response_model=LlmTestResponse)
async def test_llm_connection(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
    lang: str = Query("zh", description="Output language: zh or en"),
):
    """测试 LLM API 连接是否正常"""
    llm_config = get_llm_config(db)
    api_key = llm_config.get("api_key")
    base_url = llm_config.get("base_url")
    model_name = llm_config.get("model_name")

    not_configured_msg = (
        "请先配置 LLM API Key、Base URL 和 Model Name"
        if lang == "zh"
        else "Please configure LLM API Key, Base URL and Model Name first"
    )
    if not api_key or not base_url or not model_name:
        return LlmTestResponse(
            success=False,
            message=not_configured_msg,
        )

    if lang == "zh":
        test_message = "请回复「连接成功」四个字。"
        success_prefix = "连接成功，模型回复："
        fail_prefix = "连接失败："
    else:
        test_message = 'Please reply with the words "Connection successful".'
        success_prefix = "Connection successful, model replied: "
        fail_prefix = "Connection failed: "

    try:
        reply = await call_llm_chat(
            api_key=api_key,
            base_url=base_url,
            model_name=model_name,
            system_prompt="You are a helpful assistant.",
            user_message=test_message,
        )
        return LlmTestResponse(
            success=True,
            message=f"{success_prefix}{reply[:100]}",
            model_name=model_name,
        )
    except Exception as e:
        logger.error(f"LLM 连接测试失败: {e}")
        return LlmTestResponse(
            success=False,
            message=f"{fail_prefix}{e}",
            model_name=model_name,
        )
