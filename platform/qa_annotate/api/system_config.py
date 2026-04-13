"""系统配置相关的API接口"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from qa_annotate.api.auth import get_current_superuser
from qa_annotate.database.base import get_db
from qa_annotate.database.crud import SystemConfigCRUD
from qa_annotate.schema.system_config import (
    SystemConfig,
    SystemConfigBase,
    SystemConfigUpdate,
)
from qa_annotate.schema.user import User

router = APIRouter(prefix="/system-configs", tags=["system-configs"])


@router.get("/", response_model=List[SystemConfig])
def list_system_configs(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    """获取所有系统配置（仅管理员）"""
    return SystemConfigCRUD.get_all(db)


@router.get("/{key}", response_model=SystemConfig)
def get_system_config(
    key: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    """根据键获取系统配置（仅管理员）"""
    config = SystemConfigCRUD.get_by_key(db, key=key)
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"配置键 '{key}' 不存在",
        )
    return config


@router.put("/{key}", response_model=SystemConfig)
def update_system_config(
    key: str,
    config_update: SystemConfigUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    """更新系统配置（仅管理员）"""
    existing_config = SystemConfigCRUD.get_by_key(db, key=key)
    if existing_config:
        # 更新现有配置
        updated_config = SystemConfigCRUD.update(
            db, key=key, config_update=config_update
        )
        if not updated_config:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="更新配置失败",
            )
        return updated_config
    else:
        # 创建新配置
        if config_update.value is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="配置值不能为空",
            )
        return SystemConfigCRUD.set_value(
            db,
            key=key,
            value=config_update.value,
            description=config_update.description or f"系统配置: {key}",
        )


@router.post("/", response_model=SystemConfig, status_code=status.HTTP_201_CREATED)
def create_system_config(
    config: SystemConfigBase,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    """创建系统配置（仅管理员）"""
    # 检查配置键是否已存在
    existing_config = SystemConfigCRUD.get_by_key(db, key=config.key)
    if existing_config:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"配置键 '{config.key}' 已存在",
        )

    return SystemConfigCRUD.set_value(
        db,
        key=config.key,
        value=config.value,
        description=config.description,
    )


@router.delete("/{key}", status_code=status.HTTP_204_NO_CONTENT)
def delete_system_config(
    key: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
):
    """删除系统配置（仅管理员）"""
    # 注意：SystemConfigCRUD 目前没有 delete 方法，如果需要删除功能，需要在 CRUD 中添加
    # 这里先返回 501 Not Implemented
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="删除系统配置功能暂未实现",
    )
