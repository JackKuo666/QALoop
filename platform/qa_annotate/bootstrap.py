"""应用启动时的数据库初始化辅助函数"""

from pathlib import Path

from qa_annotate.config import settings
from qa_annotate.database.base import SessionLocal
from qa_annotate.database.crud import LlmAnalysisCacheCRUD, SystemConfigCRUD
from qa_annotate.database.models import ProjectModel

_LLM_CONFIG_SPECS = (
    ("llm_base_url", "LLM_BASE_URL", "LLM API Base URL"),
    ("llm_model_name", "LLM_MODEL_NAME", "LLM Model Name"),
)

_SEED_DIR = Path(__file__).resolve().parent.parent / "seed"
_DEMO_ANALYSIS_FILES = {
    "zh": _SEED_DIR / "llm-analysis-2026-06-15_zh.md",
    "en": _SEED_DIR / "llm-analysis-2026-06-15_en.md",
}
_DEMO_ANALYSIS_NOTES_COUNT = 4


def ensure_llm_config() -> None:
    """写入 LLM 默认配置；API Key 优先从环境变量同步。"""
    db = SessionLocal()
    try:
        for key, setting_name, description in _LLM_CONFIG_SPECS:
            if SystemConfigCRUD.get_by_key(db, key=key):
                continue
            value = getattr(settings, setting_name)
            SystemConfigCRUD.set_value(db, key=key, value=value, description=description)
            print(f"已初始化 LLM 配置: {key}={value}")

        if settings.LLM_API_KEY:
            SystemConfigCRUD.set_value(
                db,
                key="llm_api_key",
                value=settings.LLM_API_KEY,
                description="LLM API Key",
            )
            print("已从环境变量同步 LLM API Key")
    finally:
        db.close()


def seed_demo_llm_analysis() -> None:
    """从 seed 目录下的示例 Markdown 预置中英文 LLM 分析报告。"""
    db = SessionLocal()
    try:
        project = db.query(ProjectModel).order_by(ProjectModel.id).first()
        if not project:
            print("无项目数据，跳过 Demo LLM 分析报告导入")
            return

        for language, path in _DEMO_ANALYSIS_FILES.items():
            if not path.exists():
                print(f"未找到 {path.name}，跳过")
                continue
            if LlmAnalysisCacheCRUD.get_by_project(
                db, project_id=project.id, language=language
            ):
                continue

            LlmAnalysisCacheCRUD.save(
                db=db,
                project_id=project.id,
                analysis_text=path.read_text(encoding="utf-8"),
                model_name=settings.LLM_MODEL_NAME,
                notes_count=_DEMO_ANALYSIS_NOTES_COUNT,
                language=language,
            )
            print(f"已导入 Demo LLM 分析报告: project={project.id} lang={language}")
    finally:
        db.close()
