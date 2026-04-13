#!/usr/bin/env python
"""数据库迁移脚本 - 添加项目表支持

确保项目表和相关关联表存在，如果不存在则创建。
这个脚本可以安全地多次运行（幂等性）。

主要变更：
1. 创建 projects 表（如果不存在）
2. 创建 project_annotation_config_association 关联表（如果不存在）
3. 为 project_annotation_config_association 表添加 order 字段（如果不存在，用于配置排序）
4. 为 datasets 表添加 project_id 外键列（如果不存在）
5. 为 datasets 表添加 annotator_id 和 annotator_name 字段（如果不存在）
6. 确保所有外键约束正确
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
    """备份数据库"""
    from datetime import datetime

    backup_path = (
        DB_PATH.parent
        / f"annotations_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    )
    shutil.copy2(DB_PATH, backup_path)
    logger.info(f"数据库已备份到: {backup_path}")
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
    """从备份恢复数据库"""
    logger.warning("=" * 60)
    logger.warning("开始从备份恢复数据库...")
    logger.warning(f"备份路径: {backup_path}")
    logger.warning("=" * 60)

    if not backup_path.exists():
        logger.error(f"备份文件不存在: {backup_path}")
        return False

    try:
        shutil.copy2(backup_path, DB_PATH)
        logger.info("数据库已从备份恢复")
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


def create_projects_table(engine: Engine):
    """创建 projects 表（如果不存在）"""
    logger.info("检查 projects 表...")

    inspector = inspect(engine)

    if table_exists(inspector, "projects"):
        logger.info("projects 表已存在，跳过创建")
        return False

    logger.info("创建 projects 表...")

    with engine.begin() as conn:
        disable_foreign_keys(conn)

        conn.execute(
            text("""
            CREATE TABLE projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR NOT NULL,
                description TEXT,
                version VARCHAR,
                status VARCHAR DEFAULT 'active',
                tags_json JSON,
                category VARCHAR,
                creator VARCHAR,
                creator_id INTEGER,
                source VARCHAR,
                source_url TEXT,
                metadata_json JSON,
                display_extra_fields_json JSON,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (creator_id) REFERENCES users(id) ON DELETE SET NULL
            )
        """)
        )

        # 创建索引
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_projects_id ON projects(id)"))
        conn.execute(
            text("CREATE INDEX IF NOT EXISTS ix_projects_name ON projects(name)")
        )
        conn.execute(
            text("CREATE INDEX IF NOT EXISTS ix_projects_version ON projects(version)")
        )
        conn.execute(
            text("CREATE INDEX IF NOT EXISTS ix_projects_status ON projects(status)")
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_projects_category ON projects(category)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_projects_creator_id ON projects(creator_id)"
            )
        )

        enable_foreign_keys(conn)

    logger.info("projects 表创建完成")
    return True


def create_project_annotation_config_association_table(engine: Engine):
    """创建 project_annotation_config_association 关联表（如果不存在）"""
    logger.info("检查 project_annotation_config_association 表...")

    inspector = inspect(engine)
    table_name = "project_annotation_config_association"

    if table_exists(inspector, table_name):
        logger.info(f"{table_name} 表已存在，跳过创建")
        return False

    logger.info(f"创建 {table_name} 表...")

    with engine.begin() as conn:
        disable_foreign_keys(conn)

        conn.execute(
            text(f"""
            CREATE TABLE {table_name} (
                project_id INTEGER NOT NULL,
                annotation_config_id INTEGER NOT NULL,
                "order" INTEGER NOT NULL DEFAULT 0,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (project_id, annotation_config_id),
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
                FOREIGN KEY (annotation_config_id) REFERENCES annotation_configs(id) ON DELETE CASCADE
            )
        """)
        )

        enable_foreign_keys(conn)

    logger.info(f"{table_name} 表创建完成")
    return True


def add_order_to_project_annotation_config_association(engine: Engine):
    """为 project_annotation_config_association 表添加 order 列（如果不存在）"""
    logger.info("检查 project_annotation_config_association 表的 order 列...")

    inspector = inspect(engine)
    table_name = "project_annotation_config_association"

    if not table_exists(inspector, table_name):
        logger.warning(f"{table_name} 表不存在，跳过添加 order 列")
        return False

    if column_exists(inspector, table_name, "order"):
        logger.info(f"{table_name} 表的 order 列已存在，跳过添加")
        return False

    logger.info(f"为 {table_name} 表添加 order 列...")

    with engine.begin() as conn:
        disable_foreign_keys(conn)

        try:
            # SQLite 3.25.0+ 支持 ALTER TABLE ADD COLUMN
            conn.execute(
                text(f"""
                ALTER TABLE {table_name}
                ADD COLUMN "order" INTEGER NOT NULL DEFAULT 0
            """)
            )

            # 为现有记录设置order值（按created_at排序）
            # 注意：使用子查询为每个项目的配置按创建时间设置顺序
            conn.execute(
                text(f"""
                UPDATE {table_name}
                SET "order" = (
                    SELECT COUNT(*) - 1
                    FROM {table_name} AS t2
                    WHERE t2.project_id = {table_name}.project_id
                    AND (t2.created_at < {table_name}.created_at
                         OR (t2.created_at = {table_name}.created_at
                             AND t2.annotation_config_id < {table_name}.annotation_config_id))
                )
            """)
            )

            logger.info("已通过 ALTER TABLE 添加 order 列，并为现有记录设置了顺序")
        except Exception as e:
            logger.warning(f"无法通过 ALTER TABLE 添加列: {e}")
            logger.info("需要重建表以添加 order 列")
            logger.warning("这是一个复杂操作，建议手动处理或使用完整的表重建迁移")
            enable_foreign_keys(conn)
            return False

        enable_foreign_keys(conn)

    return True


def add_project_id_to_datasets(engine: Engine):
    """为 datasets 表添加 project_id 列（如果不存在）"""
    logger.info("检查 datasets 表的 project_id 列...")

    inspector = inspect(engine)

    if not table_exists(inspector, "datasets"):
        logger.warning("datasets 表不存在，跳过添加 project_id 列")
        return False

    if column_exists(inspector, "datasets", "project_id"):
        logger.info("datasets 表的 project_id 列已存在，跳过添加")
        return False

    logger.info("为 datasets 表添加 project_id 列...")

    with engine.begin() as conn:
        disable_foreign_keys(conn)

        # SQLite 不支持直接添加外键列，需要重建表
        # 但为了简化，我们只添加列，不添加外键约束（因为 SQLite 的限制）
        # 如果需要外键约束，应该在创建表时添加

        # 检查是否可以通过 ALTER TABLE 添加（SQLite 3.25.0+ 支持）
        try:
            conn.execute(
                text("""
                ALTER TABLE datasets
                ADD COLUMN project_id INTEGER
            """)
            )

            # 创建索引
            conn.execute(
                text("""
                CREATE INDEX IF NOT EXISTS ix_datasets_project_id
                ON datasets(project_id)
            """)
            )

            logger.info("已通过 ALTER TABLE 添加 project_id 列")
        except Exception as e:
            logger.warning(f"无法通过 ALTER TABLE 添加列: {e}")
            logger.info("需要重建 datasets 表以添加 project_id 列")
            logger.warning("这是一个复杂操作，建议手动处理或使用完整的表重建迁移")

        enable_foreign_keys(conn)

    return True


def add_annotator_fields_to_datasets(engine: Engine):
    """为 datasets 表添加标注者字段（annotator_id 和 annotator_name）"""
    logger.info("检查 datasets 表的标注者字段...")

    inspector = inspect(engine)

    if not table_exists(inspector, "datasets"):
        logger.warning("datasets 表不存在，跳过添加标注者字段")
        return False

    changes_made = False

    with engine.begin() as conn:
        disable_foreign_keys(conn)

        # 检查并添加 annotator_id 列
        if not column_exists(inspector, "datasets", "annotator_id"):
            logger.info("添加 annotator_id 列...")
            try:
                conn.execute(
                    text("""
                    ALTER TABLE datasets
                    ADD COLUMN annotator_id INTEGER
                """)
                )
                logger.info("annotator_id 列已添加")
                changes_made = True
            except Exception as e:
                logger.warning(f"无法通过 ALTER TABLE 添加 annotator_id 列: {e}")
        else:
            logger.info("annotator_id 列已存在，跳过")

        # 检查并添加 annotator_name 列
        if not column_exists(inspector, "datasets", "annotator_name"):
            logger.info("添加 annotator_name 列...")
            try:
                conn.execute(
                    text("""
                    ALTER TABLE datasets
                    ADD COLUMN annotator_name VARCHAR
                """)
                )
                logger.info("annotator_name 列已添加")
                changes_made = True
            except Exception as e:
                logger.warning(f"无法通过 ALTER TABLE 添加 annotator_name 列: {e}")
        else:
            logger.info("annotator_name 列已存在，跳过")

        # 检查并添加索引
        if column_exists(inspector, "datasets", "annotator_id"):
            # 检查索引是否存在
            indexes = inspector.get_indexes("datasets")
            index_names = [idx["name"] for idx in indexes]
            if "ix_datasets_annotator_id" not in index_names:
                logger.info("添加 annotator_id 索引...")
                try:
                    conn.execute(
                        text("""
                        CREATE INDEX IF NOT EXISTS ix_datasets_annotator_id
                        ON datasets(annotator_id)
                    """)
                    )
                    logger.info("annotator_id 索引已添加")
                    changes_made = True
                except Exception as e:
                    logger.warning(f"无法创建 annotator_id 索引: {e}")
            else:
                logger.info("annotator_id 索引已存在")

        enable_foreign_keys(conn)

    if changes_made:
        logger.info("数据集标注者字段迁移完成")
    else:
        logger.info("数据集标注者字段已是最新，无需迁移")

    return changes_made


def validate_migration(engine: Engine) -> tuple[bool, list[str]]:
    """验证迁移结果"""
    logger.info("验证迁移结果...")

    errors = []
    inspector = inspect(engine)

    # 检查 projects 表是否存在
    if not table_exists(inspector, "projects"):
        errors.append("projects 表不存在")
    else:
        logger.info("✓ projects 表存在")

        # 检查关键列
        required_columns = ["id", "name", "created_at", "updated_at"]
        columns = {col["name"] for col in inspector.get_columns("projects")}
        for col in required_columns:
            if col not in columns:
                errors.append(f"projects 表缺少列: {col}")
            else:
                logger.info(f"  ✓ projects 表有 {col} 列")

    # 检查关联表是否存在
    if not table_exists(inspector, "project_annotation_config_association"):
        errors.append("project_annotation_config_association 表不存在")
    else:
        logger.info("✓ project_annotation_config_association 表存在")
        # 检查 order 列
        if column_exists(inspector, "project_annotation_config_association", "order"):
            logger.info("  ✓ project_annotation_config_association 表有 order 列")
        else:
            logger.warning(
                "  ⚠ project_annotation_config_association 表没有 order 列（需要添加）"
            )

    # 检查 datasets 表的 project_id 列
    if table_exists(inspector, "datasets"):
        if column_exists(inspector, "datasets", "project_id"):
            logger.info("✓ datasets 表有 project_id 列")
        else:
            logger.warning("datasets 表没有 project_id 列（可能需要手动添加）")

        # 检查标注者字段
        if column_exists(inspector, "datasets", "annotator_id"):
            logger.info("✓ datasets 表有 annotator_id 列")
        else:
            logger.warning("datasets 表没有 annotator_id 列（可能需要手动添加）")

        if column_exists(inspector, "datasets", "annotator_name"):
            logger.info("✓ datasets 表有 annotator_name 列")
        else:
            logger.warning("datasets 表没有 annotator_name 列（可能需要手动添加）")

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
    logger.info("开始数据库迁移 - 添加项目表支持")
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
        # 创建 projects 表
        if create_projects_table(engine):
            changes_made = True

        # 创建关联表
        if create_project_annotation_config_association_table(engine):
            changes_made = True

        # 为关联表添加 order 列（如果表已存在但缺少该列）
        if add_order_to_project_annotation_config_association(engine):
            changes_made = True

        # 为 datasets 表添加 project_id 列
        if add_project_id_to_datasets(engine):
            changes_made = True

        # 为 datasets 表添加标注者字段
        if add_annotator_fields_to_datasets(engine):
            changes_made = True

        if not changes_made:
            logger.info("=" * 60)
            logger.info("所有表结构已是最新，无需迁移")
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
