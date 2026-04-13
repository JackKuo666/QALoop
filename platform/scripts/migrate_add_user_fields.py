#!/usr/bin/env python
"""数据库迁移脚本 - 为用户表添加单位、团队、物种字段

确保用户表包含以下新字段：
1. organization (VARCHAR) - 单位（崖州湾实验室、之江实验室）
2. team (VARCHAR) - 团队
3. species (VARCHAR) - 物种

这个脚本可以安全地多次运行（幂等性）。

主要变更：
1. 为 users 表添加 organization 列（如果不存在）
2. 为 users 表添加 team 列（如果不存在）
3. 为 users 表添加 species 列（如果不存在）
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 注意：以下导入必须在 sys.path.insert 之后，因为需要导入项目模块
import logging  # noqa: E402
import shutil  # noqa: E402

from sqlalchemy import inspect, text  # noqa: E402
from sqlalchemy.engine import Engine  # noqa: E402

from qa_annotate.database.base import DB_PATH, engine  # noqa: E402

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def backup_database():
    """备份数据库（SQLite）"""
    from datetime import datetime

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = DB_PATH.parent / f"annotations_backup_{timestamp}.db"
    shutil.copy2(DB_PATH, backup_path)
    logger.info(f"SQLite 数据库已备份到: {backup_path}")
    return backup_path


def disable_foreign_keys(conn):
    """禁用外键约束"""
    conn.execute(text("PRAGMA foreign_keys = OFF"))
    logger.info("已禁用外键约束")


def enable_foreign_keys(conn):
    """启用外键约束"""
    conn.execute(text("PRAGMA foreign_keys = ON"))
    logger.info("已启用外键约束")


def restore_from_backup(backup_path: Path):
    """从备份恢复数据库（SQLite）"""
    logger.warning("=" * 60)
    logger.warning("开始从备份恢复数据库...")
    logger.warning(f"备份路径: {backup_path}")
    logger.warning("=" * 60)

    if not backup_path.exists():
        logger.error(f"备份文件不存在: {backup_path}")
        return False

    try:
        shutil.copy2(backup_path, DB_PATH)
        logger.info("SQLite 数据库已从备份恢复")
        return True
    except Exception as e:
        logger.error(f"恢复数据库失败: {e}")
        return False


def table_exists(inspector: inspect, table_name: str) -> bool:
    """检查表是否存在"""
    return table_name in inspector.get_table_names()


def column_exists(inspector: inspect, table_name: str, column_name: str) -> bool:
    """检查列是否存在"""
    if not table_exists(inspector, table_name):
        return False
    columns = inspector.get_columns(table_name)
    return any(col["name"] == column_name for col in columns)


def add_user_fields(engine: Engine):
    """为用户表添加新字段（organization、team、species）"""
    logger.info("检查 users 表的新字段...")

    inspector = inspect(engine)

    if not table_exists(inspector, "users"):
        logger.error("users 表不存在，无法添加字段")
        return False

    changes_made = False

    with engine.begin() as conn:
        disable_foreign_keys(conn)

        # 添加 organization 列
        if not column_exists(inspector, "users", "organization"):
            logger.info("添加 organization 列...")
            try:
                conn.execute(
                    text("""
                    ALTER TABLE users
                    ADD COLUMN organization VARCHAR
                """)
                )
                logger.info("organization 列已添加")
                changes_made = True
            except Exception as e:
                logger.warning(f"无法通过 ALTER TABLE 添加 organization 列: {e}")
                logger.error("添加 organization 列失败")
        else:
            logger.info("organization 列已存在，跳过")

        # 添加 team 列
        if not column_exists(inspector, "users", "team"):
            logger.info("添加 team 列...")
            try:
                conn.execute(
                    text("""
                    ALTER TABLE users
                    ADD COLUMN team VARCHAR
                """)
                )
                logger.info("team 列已添加")
                changes_made = True
            except Exception as e:
                logger.warning(f"无法通过 ALTER TABLE 添加 team 列: {e}")
                logger.error("添加 team 列失败")
        else:
            logger.info("team 列已存在，跳过")

        # 添加 species 列
        if not column_exists(inspector, "users", "species"):
            logger.info("添加 species 列...")
            try:
                conn.execute(
                    text("""
                    ALTER TABLE users
                    ADD COLUMN species VARCHAR
                """)
                )
                logger.info("species 列已添加")
                changes_made = True
            except Exception as e:
                logger.warning(f"无法通过 ALTER TABLE 添加 species 列: {e}")
                logger.error("添加 species 列失败")
        else:
            logger.info("species 列已存在，跳过")

        enable_foreign_keys(conn)

    return changes_made


def validate_migration(engine: Engine):
    """验证迁移结果"""
    logger.info("验证迁移结果...")

    inspector = inspect(engine)
    errors = []

    # 检查 users 表是否存在
    if not table_exists(inspector, "users"):
        errors.append("users 表不存在")
        return False, errors

    logger.info("✓ users 表存在")

    # 检查新字段
    required_columns = ["organization", "team", "species"]
    columns = {col["name"] for col in inspector.get_columns("users")}

    for col in required_columns:
        if col not in columns:
            errors.append(f"users 表缺少列: {col}")
        else:
            logger.info(f"  ✓ users 表有 {col} 列")

    if errors:
        logger.error("验证失败:")
        for error in errors:
            logger.error(f"  - {error}")
        return False, errors

    logger.info("验证通过")
    return True, []


def main():
    """主函数"""
    logger.info("=" * 60)
    logger.info("开始数据库迁移 - 为用户表添加单位、团队、物种字段")
    logger.info(f"数据库路径: {DB_PATH}")
    logger.info("=" * 60)

    # 检查数据库文件是否存在
    if not DB_PATH.exists():
        logger.error(f"数据库文件不存在: {DB_PATH}")
        logger.info("如果这是新安装，请先运行应用以初始化数据库")
        sys.exit(1)

    # 备份数据库
    logger.info("备份数据库...")
    backup_path = backup_database()
    logger.info(f"备份完成: {backup_path}")

    migration_success = False
    changes_made = False

    try:
        # 为用户表添加新字段
        if add_user_fields(engine):
            changes_made = True

        if not changes_made:
            logger.info("=" * 60)
            logger.info("所有字段已存在，无需迁移")
            logger.info("=" * 60)
            return

        # 验证迁移
        logger.info("=" * 60)
        logger.info("开始验证迁移结果...")
        logger.info("=" * 60)

        is_valid, errors = validate_migration(engine)

        if not is_valid:
            logger.error("=" * 60)
            logger.error("迁移验证失败！")
            logger.error("=" * 60)
            logger.error("错误详情:")
            for error in errors:
                logger.error(f"  - {error}")
            logger.error("=" * 60)
            logger.error("开始回退到备份...")
            logger.error("=" * 60)

            if restore_from_backup(backup_path):
                logger.error("已成功回退到备份")
            else:
                logger.error("回退失败，请手动恢复数据库")
            sys.exit(1)

        migration_success = True

        logger.info("=" * 60)
        logger.info("数据库迁移完成！")
        logger.info("验证通过！")
        logger.info("=" * 60)

        # 用户确认
        logger.info("=" * 60)
        logger.info("迁移已完成，请确认是否接受此次迁移")
        logger.info(f"备份文件位置: {backup_path}")
        logger.info("=" * 60)

        try:
            user_input = input("确认接受迁移？(y/n): ").strip().lower()
            if user_input in ("y", "yes"):
                logger.info("=" * 60)
                logger.info("用户已确认，迁移完成！")
                logger.info("=" * 60)
            else:
                logger.warning("=" * 60)
                logger.warning("用户已取消，开始回退到备份...")
                logger.warning("=" * 60)

                if restore_from_backup(backup_path):
                    logger.warning("已成功回退到备份")
                    logger.warning("迁移已取消")
                else:
                    logger.error("回退失败，请手动恢复数据库")
                sys.exit(0)

        except (KeyboardInterrupt, EOFError):
            logger.warning("")
            logger.warning("=" * 60)
            logger.warning("用户中断操作，开始回退到备份...")
            logger.warning("=" * 60)

            if restore_from_backup(backup_path):
                logger.warning("已成功回退到备份")
                logger.warning("迁移已取消")
            else:
                logger.error("回退失败，请手动恢复数据库")
            sys.exit(0)

    except Exception as e:
        logger.error("=" * 60)
        logger.error(f"迁移过程中发生异常: {e}", exc_info=True)
        logger.error("=" * 60)

        if not migration_success:
            logger.error("开始回退到备份...")
            if restore_from_backup(backup_path):
                logger.error("已成功回退到备份")
            else:
                logger.error("回退失败，请手动恢复数据库")
        sys.exit(1)


if __name__ == "__main__":
    main()
