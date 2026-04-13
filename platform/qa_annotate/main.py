"""FastAPI 应用主入口"""

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.types import Scope

from qa_annotate.api.analysis import router as analysis_router
from qa_annotate.api.annotation import annotation_result_router
from qa_annotate.api.annotation import router as annotation_router
from qa_annotate.api.auth import get_optional_user
from qa_annotate.api.dataset import router as dataset_router
from qa_annotate.api.project import router as project_router
from qa_annotate.api.seed_question import router as seed_question_router
from qa_annotate.api.system_config import router as system_config_router
from qa_annotate.api.user import router as user_router
from qa_annotate.config import settings
from qa_annotate.database.base import init_db


class NoCachedStaticFiles(StaticFiles):
    """带缓存头的静态文件服务"""

    def file_response(
        self,
        full_path: str,
        stat_result: os.stat_result,
        scope: Scope,
        status_code: int = 200,
    ) -> Response:
        response = super().file_response(full_path, stat_result, scope, status_code)
        # 禁用缓存
        response.headers["Cache-Control"] = "no-cache"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时执行
    init_db()
    yield
    # 关闭时执行（如果需要清理资源，可以在这里添加）


# 创建 FastAPI 应用
# 生产环境禁用文档
docs_url = None if settings.is_production else "/docs"
redoc_url = None if settings.is_production else "/redoc"

app = FastAPI(
    title="QA 标注系统 API",
    description="QA对数据集标注系统 API 接口",
    version="0.1.0",
    lifespan=lifespan,
    docs_url=docs_url,
    redoc_url=redoc_url,
)

# 注册路由（添加/api前缀）
app.include_router(user_router, prefix="/api")
app.include_router(dataset_router, prefix="/api")
app.include_router(annotation_router, prefix="/api")
app.include_router(annotation_result_router, prefix="/api")
app.include_router(project_router, prefix="/api")
app.include_router(seed_question_router, prefix="/api")
app.include_router(system_config_router, prefix="/api")
app.include_router(analysis_router, prefix="/api")

# 挂载静态文件（带1分钟缓存）
app.mount("/static", NoCachedStaticFiles(directory="qa_annotate/static"), name="static")


@app.get("/")
async def root(user=Depends(get_optional_user)):
    """根据用户登录状态和权限返回不同页面"""
    # 根据用户状态返回不同页面
    if user is None:
        # 未登录，返回 auth.html
        return RedirectResponse(url="/auth")
    elif user.is_superuser:
        # 超级用户，返回 manager.html
        return RedirectResponse(url="/manager")
    else:
        # 普通用户，返回 user.html
        return RedirectResponse(url="/user")


@app.get("/{path}")
async def html(path: str):
    """返回 html 目录中的文件"""
    if not path.endswith(".html"):
        path = path + ".html"
    html_dir = Path(__file__).parent / "html"
    file_path = (html_dir / path).resolve()
    # 防止目录穿越攻击，只允许访问html目录下的文件
    html_dir_resolved = html_dir.resolve()
    if not str(file_path).startswith(str(html_dir_resolved)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")
    return FileResponse(str(file_path))


@app.get("/api/health")
async def health_check():
    """健康检查接口"""
    return {"status": "healthy"}


def main():
    """启动应用的入口函数"""
    import uvicorn

    from qa_annotate.config import settings

    uvicorn.run(
        "qa_annotate.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.RELOAD,
        reload_dirs=["qa_annotate"],
    )
