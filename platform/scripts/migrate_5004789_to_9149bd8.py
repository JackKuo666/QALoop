#!/usr/bin/env python
"""数据库迁移脚本

从 commit 5004789ff44222d41da931d4423cfb5d0e41e053
迁移到 commit 9149bd803663748f157986544eca876543b326dc

主要变更：
1. annotation_results 表：
   - dataset_id, dataset_item_id, annotation_config_id 添加外键约束
   - annotator_id 从 String 类型改为 Integer 类型，并添加外键约束
2. datasets 表：
   - creator_id 从 String 类型改为 Integer 类型，并添加外键约束
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
from sqlalchemy.orm import Session  # noqa: E402

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


def get_table_record_counts(engine: Engine) -> dict[str, int]:
    """获取所有用户表的记录数量

    Returns:
        dict: {表名: 记录数量}
    """
    counts = {}

    with engine.connect() as conn:
        inspector = inspect(engine)
        table_names = inspector.get_table_names()

        # 排除系统表
        system_tables = {"sqlite_sequence", "sqlite_master"}
        user_tables = [t for t in table_names if t not in system_tables]

        for table_name in user_tables:
            try:
                result = conn.execute(text(f'SELECT COUNT(*) FROM "{table_name}"'))
                count = result.scalar()
                counts[table_name] = count
            except Exception as e:
                logger.warning(f"获取 {table_name} 表记录数量失败: {e}")
                counts[table_name] = -1  # 使用 -1 表示无法获取

    return counts


def validate_data_integrity(
    engine: Engine, before_counts: dict[str, int] | None = None
) -> tuple[bool, list[str]]:
    """校验数据是否丢失

    检查所有表的必填字段（NOT NULL）是否有 NULL 值，以及迁移涉及的特殊字段类型是否正确。
    如果提供了迁移前的记录数量，会比较迁移前后的记录数量。

    Args:
        engine: 数据库引擎
        before_counts: 迁移前的记录数量字典 {表名: 数量}

    Returns:
        tuple: (是否通过校验, 错误信息列表)
    """
    logger.info("开始校验数据是否丢失...")
    errors = []

    with engine.connect() as conn:
        inspector = inspect(engine)
        table_names = inspector.get_table_names()

        # 排除系统表
        system_tables = {"sqlite_sequence", "sqlite_master"}
        user_tables = [t for t in table_names if t not in system_tables]

        logger.info(f"发现 {len(user_tables)} 个用户表，开始校验...")

        # 获取迁移后的记录数量
        after_counts = get_table_record_counts(engine)

        for table_name in user_tables:
            logger.info(f"校验 {table_name} 表...")

            try:
                # 获取当前表的记录数量
                current_count = after_counts.get(table_name, 0)
                logger.info(f"  {table_name} 表当前记录数: {current_count}")

                # 如果提供了迁移前的数量，比较记录数量
                if before_counts is not None and table_name in before_counts:
                    before_count = before_counts[table_name]
                    if before_count >= 0:  # 如果迁移前能获取到数量
                        if current_count < before_count:
                            errors.append(
                                f"{table_name} 表记录数量减少: 迁移前 {before_count} 条, "
                                f"迁移后 {current_count} 条, 丢失 {before_count - current_count} 条"
                            )
                        elif current_count > before_count:
                            logger.warning(
                                f"{table_name} 表记录数量增加: 迁移前 {before_count} 条, "
                                f"迁移后 {current_count} 条（可能是正常的）"
                            )
                        else:
                            logger.info(
                                f"  {table_name} 表记录数量一致: {before_count} 条"
                            )

                # 获取表的列信息
                columns = inspector.get_columns(table_name)
                not_null_columns = [
                    col["name"]
                    for col in columns
                    if not col.get("nullable", True)
                    and not col.get("primary_key", False)
                ]

                # 检查 NOT NULL 字段是否有 NULL 值
                if not_null_columns:
                    # 构建 WHERE 条件（使用双引号包裹列名以确保安全）
                    null_conditions = " OR ".join(
                        [f'"{col}" IS NULL' for col in not_null_columns]
                    )
                    # 使用参数化查询的表名（SQLite 不支持表名参数化，但表名来自元数据，相对安全）
                    result = conn.execute(
                        text(f"""
                            SELECT COUNT(*) FROM "{table_name}"
                            WHERE {null_conditions}
                        """)
                    )
                    null_count = result.scalar()
                    if null_count > 0:
                        errors.append(
                            f"{table_name} 表有 {null_count} 条记录的必填字段为 NULL（可能数据丢失）"
                        )

                # 特殊字段类型检查（迁移涉及的字段）
                if table_name == "annotation_results":
                    # 检查 annotator_id 类型（应该是 INTEGER 或 NULL）
                    if any(col["name"] == "annotator_id" for col in columns):
                        result = conn.execute(
                            text("""
                                SELECT COUNT(*) FROM annotation_results
                                WHERE annotator_id IS NOT NULL
                                  AND typeof(annotator_id) != 'integer'
                            """)
                        )
                        invalid_type_count = result.scalar()
                        if invalid_type_count > 0:
                            errors.append(
                                f"annotation_results 表有 {invalid_type_count} 条记录的 annotator_id 类型不正确"
                            )

                elif table_name == "datasets":
                    # 检查 creator_id 类型（应该是 INTEGER 或 NULL）
                    if any(col["name"] == "creator_id" for col in columns):
                        result = conn.execute(
                            text("""
                                SELECT COUNT(*) FROM datasets
                                WHERE creator_id IS NOT NULL
                                  AND typeof(creator_id) != 'integer'
                            """)
                        )
                        invalid_type_count = result.scalar()
                        if invalid_type_count > 0:
                            errors.append(
                                f"datasets 表有 {invalid_type_count} 条记录的 creator_id 类型不正确"
                            )

            except Exception as e:
                logger.warning(f"校验 {table_name} 表时发生错误: {e}")
                errors.append(f"{table_name} 表校验失败: {e}")

    # 打印记录数量统计
    logger.info("=" * 60)
    logger.info("记录数量统计:")
    for table_name in sorted(after_counts.keys()):
        count = after_counts[table_name]
        if before_counts and table_name in before_counts:
            before_count = before_counts[table_name]
            status = "✓" if count == before_count else "✗"
            logger.info(
                f"  {status} {table_name}: {count} 条"
                + (f" (迁移前: {before_count} 条)" if before_count >= 0 else "")
            )
        else:
            logger.info(f"  {table_name}: {count} 条")
    logger.info("=" * 60)

    if errors:
        logger.error("数据丢失校验失败:")
        for error in errors:
            logger.error(f"  - {error}")
        return False, errors
    else:
        logger.info("数据丢失校验通过")
        return True, []


def check_and_clean_foreign_key_violations(
    engine: Engine,
) -> tuple[dict[str, int], int]:
    """检查外键约束、统计并清理违反外键约束的记录

    对于违反外键约束的记录：
    - 如果外键字段允许为 NULL，则设置为 NULL
    - 如果外键字段不允许为 NULL（NOT NULL 约束），则删除该记录

    Returns:
        tuple: (违反约束统计字典 {表名: 违反数量}, 处理的记录总数（设置为 NULL + 删除）)
    """
    logger.info("=" * 60)
    logger.info("开始检查外键约束...")
    logger.info("=" * 60)

    violations_stats = {}
    total_cleaned = 0

    with engine.begin() as conn:
        # 启用外键约束
        enable_foreign_keys(conn)

        # 检查外键约束违反
        logger.info("检查外键约束违反...")
        result = conn.execute(text("PRAGMA foreign_key_check"))
        fk_violations = result.fetchall()

        if not fk_violations:
            logger.info("未发现外键约束违反")
            return {}, 0

        # 统计违反情况
        for violation in fk_violations:
            table_name = violation[0]

            if table_name not in violations_stats:
                violations_stats[table_name] = 0
            violations_stats[table_name] += 1

        # 打印统计信息
        logger.info(f"发现 {len(fk_violations)} 条外键约束违反记录")
        logger.info("=" * 60)
        logger.info("外键约束违反统计:")
        for table_name, count in violations_stats.items():
            logger.info(f"  {table_name}: {count} 条记录")
        logger.info("=" * 60)

        # 清理违反外键约束的记录
        logger.info("开始清理违反外键约束的记录...")

        inspector = inspect(engine)

        # 按表分组处理
        violations_by_table = {}
        for violation in fk_violations:
            table_name = violation[0]
            row_id = violation[1]
            parent_table = violation[3] if len(violation) > 3 else None

            if table_name not in violations_by_table:
                violations_by_table[table_name] = []
            violations_by_table[table_name].append((row_id, parent_table))

        # 对每个表进行清理
        for table_name, violations in violations_by_table.items():
            logger.info(f"清理 {table_name} 表的违反记录...")

            try:
                # 获取表的外键信息和列信息
                fks = inspector.get_foreign_keys(table_name)
                columns = inspector.get_columns(table_name)
                column_info = {col["name"]: col for col in columns}

                # 对于每个违反的记录，找到对应的外键列并清理
                cleaned_count = 0
                deleted_count = 0
                for row_id, parent_table in violations:
                    # 找到指向 parent_table 的外键
                    target_fk = None
                    for fk in fks:
                        if fk["referred_table"] == parent_table:
                            target_fk = fk
                            break

                    if not target_fk and fks:
                        # 如果找不到，使用第一个外键（通常只有一个）
                        target_fk = fks[0]

                    if target_fk and target_fk["constrained_columns"]:
                        fk_column = target_fk["constrained_columns"][0]

                        # 检查该字段是否允许为 NULL
                        fk_column_info = column_info.get(fk_column)
                        is_nullable = (
                            fk_column_info is not None
                            and fk_column_info.get("nullable", True)
                            and not fk_column_info.get("primary_key", False)
                        )

                        try:
                            if is_nullable:
                                # 如果字段允许为 NULL，设置为 NULL
                                conn.execute(
                                    text(f"""
                                        UPDATE "{table_name}"
                                        SET "{fk_column}" = NULL
                                        WHERE rowid = :row_id
                                    """),
                                    {"row_id": row_id},
                                )
                                cleaned_count += 1
                                logger.debug(
                                    f"  已清理 {table_name} 表 rowid={row_id} 的 {fk_column} 字段（设置为 NULL）"
                                )
                            else:
                                # 如果字段不允许为 NULL，删除该记录
                                conn.execute(
                                    text(f"""
                                        DELETE FROM "{table_name}"
                                        WHERE rowid = :row_id
                                    """),
                                    {"row_id": row_id},
                                )
                                deleted_count += 1
                                logger.debug(
                                    f"  已删除 {table_name} 表 rowid={row_id} 的记录（{fk_column} 字段为 NOT NULL）"
                                )
                        except Exception as e:
                            logger.warning(
                                f"  清理 {table_name} 表 rowid={row_id} 失败: {e}"
                            )
                    else:
                        logger.warning(
                            f"  无法找到 {table_name} 表 rowid={row_id} 的外键列"
                        )

                total_cleaned += cleaned_count + deleted_count
                if cleaned_count > 0 or deleted_count > 0:
                    logger.info(
                        f"  {table_name} 表已清理 {cleaned_count} 条记录（设置为 NULL），"
                        f"删除 {deleted_count} 条记录（NOT NULL 约束）"
                    )

            except Exception as e:
                logger.error(f"清理 {table_name} 表时发生错误: {e}")

        logger.info("=" * 60)
        logger.info(f"外键约束清理完成，共处理 {total_cleaned} 条记录")
        logger.info("=" * 60)

    return violations_stats, total_cleaned


def get_user_id_by_username(db: Session, username: str) -> int | None:
    """根据用户名获取用户ID"""
    if not username:
        return None

    result = db.execute(
        text("SELECT id FROM users WHERE username = :username"), {"username": username}
    ).first()

    if result:
        return result[0]
    return None


def migrate_annotation_results(engine: Engine):
    """迁移 annotation_results 表"""
    logger.info("开始迁移 annotation_results 表...")

    with engine.begin() as conn:
        # 禁用外键约束以避免迁移过程中的数据丢失
        disable_foreign_keys(conn)
        # 检查表是否存在
        inspector = inspect(engine)
        if "annotation_results" not in inspector.get_table_names():
            logger.warning("annotation_results 表不存在，跳过迁移")
            enable_foreign_keys(conn)
            return

        # 检查 annotator_id 列的类型
        columns = {
            col["name"]: col for col in inspector.get_columns("annotation_results")
        }

        if "annotator_id" not in columns:
            logger.warning("annotation_results 表没有 annotator_id 列，跳过迁移")
            enable_foreign_keys(conn)
            return

        annotator_id_type = str(columns["annotator_id"]["type"])
        is_string_type = (
            "VARCHAR" in annotator_id_type
            or "TEXT" in annotator_id_type
            or "CHAR" in annotator_id_type
        )

        if not is_string_type:
            logger.info("annotator_id 已经是 Integer 类型，检查外键约束...")
            # 检查是否已有外键约束
            fks = inspector.get_foreign_keys("annotation_results")
            has_fk = any(fk["constrained_columns"] == ["annotator_id"] for fk in fks)
            if has_fk:
                logger.info("annotation_results 表已经迁移完成，跳过")
                enable_foreign_keys(conn)
                return

        # 清理可能存在的旧表（如果之前的迁移失败）
        logger.info("清理可能存在的旧表...")
        conn.execute(text("DROP TABLE IF EXISTS annotation_results_new"))

        # 清理可能存在的旧索引
        for index_name in [
            "ix_annotation_results_dataset_id",
            "ix_annotation_results_dataset_item_id",
            "ix_annotation_results_annotation_config_id",
            "ix_annotation_results_annotator_id",
        ]:
            conn.execute(text(f"DROP INDEX IF EXISTS {index_name}"))

        # 创建新表
        logger.info("创建新的 annotation_results 表...")
        conn.execute(
            text("""
            CREATE TABLE annotation_results_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                dataset_id INTEGER NOT NULL,
                dataset_item_id INTEGER NOT NULL,
                annotation_config_id INTEGER NOT NULL,
                value_json TEXT NOT NULL,
                annotator_id INTEGER,
                annotator_name TEXT,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL,
                duration_seconds REAL,
                confidence REAL,
                notes TEXT,
                custom_fields_json TEXT,
                FOREIGN KEY (dataset_id) REFERENCES datasets(id) ON DELETE CASCADE,
                FOREIGN KEY (dataset_item_id) REFERENCES qa_pairs(id) ON DELETE CASCADE,
                FOREIGN KEY (annotation_config_id) REFERENCES annotation_configs(id) ON DELETE CASCADE,
                FOREIGN KEY (annotator_id) REFERENCES users(id) ON DELETE SET NULL
            )
        """)
        )

        # 创建索引
        logger.info("创建索引...")
        conn.execute(
            text(
                "CREATE INDEX ix_annotation_results_dataset_id ON annotation_results_new(dataset_id)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX ix_annotation_results_dataset_item_id ON annotation_results_new(dataset_item_id)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX ix_annotation_results_annotation_config_id ON annotation_results_new(annotation_config_id)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX ix_annotation_results_annotator_id ON annotation_results_new(annotator_id)"
            )
        )

        # 迁移数据
        logger.info("迁移数据...")
        with Session(engine) as session:
            # 获取所有记录
            result = conn.execute(text("SELECT * FROM annotation_results"))
            rows = result.fetchall()
            column_names = result.keys()

            migrated_count = 0
            skipped_count = 0

            for row in rows:
                row_dict = dict(zip(column_names, row))

                # 处理 annotator_id：如果是字符串，尝试转换为用户ID
                annotator_id = row_dict.get("annotator_id")
                if annotator_id and isinstance(annotator_id, str):
                    # 尝试将字符串转换为整数（如果已经是数字字符串）
                    try:
                        annotator_id = int(annotator_id)
                    except ValueError:
                        # 如果不是数字，尝试通过用户名查找
                        user_id = get_user_id_by_username(session, annotator_id)
                        if user_id:
                            annotator_id = user_id
                        else:
                            logger.warning(
                                f"无法找到用户: {annotator_id}，将 annotator_id 设置为 NULL"
                            )
                            annotator_id = None

                # 插入到新表
                try:
                    conn.execute(
                        text("""
                            INSERT INTO annotation_results_new (
                                id, dataset_id, dataset_item_id, annotation_config_id,
                                value_json, annotator_id, annotator_name,
                                created_at, updated_at, duration_seconds,
                                confidence, notes, custom_fields_json
                            ) VALUES (
                                :id, :dataset_id, :dataset_item_id, :annotation_config_id,
                                :value_json, :annotator_id, :annotator_name,
                                :created_at, :updated_at, :duration_seconds,
                                :confidence, :notes, :custom_fields_json
                            )
                        """),
                        {
                            "id": row_dict["id"],
                            "dataset_id": row_dict["dataset_id"],
                            "dataset_item_id": row_dict["dataset_item_id"],
                            "annotation_config_id": row_dict["annotation_config_id"],
                            "value_json": row_dict.get("value_json", ""),
                            "annotator_id": annotator_id,
                            "annotator_name": row_dict.get("annotator_name"),
                            "created_at": row_dict.get("created_at"),
                            "updated_at": row_dict.get("updated_at"),
                            "duration_seconds": row_dict.get("duration_seconds"),
                            "confidence": row_dict.get("confidence"),
                            "notes": row_dict.get("notes"),
                            "custom_fields_json": row_dict.get("custom_fields_json"),
                        },
                    )
                    migrated_count += 1
                except Exception as e:
                    logger.error(f"迁移记录失败 (id={row_dict['id']}): {e}")
                    skipped_count += 1

            logger.info(
                f"数据迁移完成: {migrated_count} 条成功, {skipped_count} 条失败"
            )

        # 删除旧表
        logger.info("删除旧表...")
        conn.execute(text("DROP TABLE annotation_results"))

        # 重命名新表
        logger.info("重命名新表...")
        conn.execute(
            text("ALTER TABLE annotation_results_new RENAME TO annotation_results")
        )

        # 启用外键约束
        enable_foreign_keys(conn)

        logger.info("annotation_results 表迁移完成")


def migrate_datasets(engine: Engine):
    """迁移 datasets 表"""
    logger.info("开始迁移 datasets 表...")

    with engine.begin() as conn:
        # 禁用外键约束以避免迁移过程中的数据丢失
        disable_foreign_keys(conn)
        # 检查表是否存在
        inspector = inspect(engine)
        if "datasets" not in inspector.get_table_names():
            logger.warning("datasets 表不存在，跳过迁移")
            enable_foreign_keys(conn)
            return

        # 检查 creator_id 列的类型
        columns = {col["name"]: col for col in inspector.get_columns("datasets")}

        if "creator_id" not in columns:
            logger.warning("datasets 表没有 creator_id 列，跳过迁移")
            enable_foreign_keys(conn)
            return

        creator_id_type = str(columns["creator_id"]["type"])
        is_string_type = (
            "VARCHAR" in creator_id_type
            or "TEXT" in creator_id_type
            or "CHAR" in creator_id_type
        )

        if not is_string_type:
            logger.info("creator_id 已经是 Integer 类型，检查外键约束...")
            # 检查是否已有外键约束
            fks = inspector.get_foreign_keys("datasets")
            has_fk = any(fk["constrained_columns"] == ["creator_id"] for fk in fks)
            if has_fk:
                logger.info("datasets 表已经迁移完成，跳过")
                enable_foreign_keys(conn)
                return

        # 清理可能存在的旧表（如果之前的迁移失败）
        logger.info("清理可能存在的旧表...")
        conn.execute(text("DROP TABLE IF EXISTS datasets_new"))

        # 获取所有列信息，构建新表结构
        logger.info("创建新的 datasets 表...")

        # 构建列定义
        column_defs = []
        for col_name, col_info in columns.items():
            col_type = str(col_info["type"])
            nullable = "NULL" if col_info.get("nullable", True) else "NOT NULL"
            default = ""
            if col_info.get("default") is not None:
                default = f" DEFAULT {col_info['default']}"

            # 特殊处理 creator_id：改为 INTEGER
            if col_name == "creator_id":
                col_type = "INTEGER"

            # 处理主键
            if col_info.get("primary_key"):
                column_defs.append(f"{col_name} {col_type} PRIMARY KEY AUTOINCREMENT")
            else:
                column_defs.append(f"{col_name} {col_type} {nullable}{default}")

        # 构建 CREATE TABLE 语句
        create_sql = f"CREATE TABLE datasets_new (\n    {',\n    '.join(column_defs)}"

        # 检查是否已有外键约束
        fks = inspector.get_foreign_keys("datasets")
        existing_fk_columns = set()
        for fk in fks:
            existing_fk_columns.update(fk["constrained_columns"])

        # 添加 creator_id 的外键约束（如果还没有）
        if "creator_id" not in existing_fk_columns:
            create_sql += ",\n    FOREIGN KEY (creator_id) REFERENCES users(id) ON DELETE SET NULL"

        create_sql += "\n)"

        # 创建新表
        conn.execute(text(create_sql))

        # 复制索引
        result = conn.execute(
            text("""
            SELECT sql FROM sqlite_master
            WHERE type='index' AND tbl_name='datasets' AND sql IS NOT NULL
        """)
        )
        for row in result:
            index_sql = row[0]
            if index_sql:
                new_index_sql = index_sql.replace("datasets", "datasets_new")
                conn.execute(text(new_index_sql))

        # 迁移数据
        logger.info("迁移数据...")
        with Session(engine) as session:
            # 获取所有记录
            result = conn.execute(text("SELECT * FROM datasets"))
            rows = result.fetchall()
            column_names = result.keys()

            migrated_count = 0
            skipped_count = 0

            for row in rows:
                row_dict = dict(zip(column_names, row))

                # 处理 creator_id：如果是字符串，尝试转换为用户ID
                creator_id = row_dict.get("creator_id")
                if creator_id and isinstance(creator_id, str):
                    # 尝试将字符串转换为整数（如果已经是数字字符串）
                    try:
                        creator_id = int(creator_id)
                    except ValueError:
                        # 如果不是数字，尝试通过用户名查找
                        user_id = get_user_id_by_username(session, creator_id)
                        if user_id:
                            creator_id = user_id
                        else:
                            logger.warning(
                                f"无法找到用户: {creator_id}，将 creator_id 设置为 NULL"
                            )
                            creator_id = None

                # 构建插入语句（动态获取所有列）
                columns_str = ", ".join(column_names)
                placeholders = ", ".join([f":{col}" for col in column_names])

                # 更新 creator_id
                row_dict["creator_id"] = creator_id

                # 插入到新表
                try:
                    conn.execute(
                        text(
                            f"INSERT INTO datasets_new ({columns_str}) VALUES ({placeholders})"
                        ),
                        row_dict,
                    )
                    migrated_count += 1
                except Exception as e:
                    logger.error(
                        f"迁移记录失败 (id={row_dict.get('id', 'unknown')}): {e}"
                    )
                    skipped_count += 1

            logger.info(
                f"数据迁移完成: {migrated_count} 条成功, {skipped_count} 条失败"
            )

        # 删除旧表
        logger.info("删除旧表...")
        conn.execute(text("DROP TABLE datasets"))

        # 重命名新表
        logger.info("重命名新表...")
        conn.execute(text("ALTER TABLE datasets_new RENAME TO datasets"))

        # 启用外键约束
        enable_foreign_keys(conn)

        logger.info("datasets 表迁移完成")


def add_foreign_keys_to_annotation_results(engine: Engine):
    """为 annotation_results 表添加外键约束（如果还没有）"""
    logger.info("检查 annotation_results 表的外键约束...")

    inspector = inspect(engine)

    if "annotation_results" not in inspector.get_table_names():
        logger.warning("annotation_results 表不存在，跳过")
        return

    fks = inspector.get_foreign_keys("annotation_results")
    fk_columns = set()
    for fk in fks:
        fk_columns.update(fk["constrained_columns"])

    # 检查是否需要添加外键
    needs_fk = {
        "dataset_id": "datasets",
        "dataset_item_id": "qa_pairs",
        "annotation_config_id": "annotation_configs",
    }

    for col, ref_table in needs_fk.items():
        if col not in fk_columns:
            logger.info(f"为 {col} 添加外键约束...")
            # SQLite 不支持直接添加外键，需要重建表
            # 这里假设表已经通过 migrate_annotation_results 迁移过了
            logger.warning(
                f"{col} 的外键约束应该在表创建时添加，如果缺失可能需要重新迁移"
            )


def main():
    """主函数"""
    logger.info("=" * 60)
    logger.info("开始数据库迁移")
    logger.info(f"数据库路径: {DB_PATH}")
    logger.info("=" * 60)

    # 检查数据库文件是否存在
    if not DB_PATH.exists():
        logger.error(f"数据库文件不存在: {DB_PATH}")
        sys.exit(1)

    # 备份数据库
    logger.info("备份数据库...")
    backup_path = backup_database()
    logger.info(f"备份完成: {backup_path}")

    # 记录迁移前的记录数量
    logger.info("记录迁移前的数据统计...")
    before_counts = get_table_record_counts(engine)
    logger.info("迁移前记录数量统计:")
    for table_name in sorted(before_counts.keys()):
        count = before_counts[table_name]
        if count >= 0:
            logger.info(f"  {table_name}: {count} 条")
        else:
            logger.warning(f"  {table_name}: 无法获取数量")
    logger.info("=" * 60)

    migration_success = False
    try:
        # 迁移 annotation_results 表
        migrate_annotation_results(engine)

        # 迁移 datasets 表
        migrate_datasets(engine)

        # 检查外键约束
        add_foreign_keys_to_annotation_results(engine)

        # 数据丢失校验
        logger.info("=" * 60)
        logger.info("开始数据丢失校验...")
        logger.info("=" * 60)

        is_valid, errors = validate_data_integrity(engine, before_counts)

        if not is_valid:
            logger.error("=" * 60)
            logger.error("数据丢失校验失败！")
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

        # 检查外键约束、统计并清理违反外键约束的记录
        violations_stats, processed_count = check_and_clean_foreign_key_violations(
            engine
        )

        migration_success = True

        logger.info("=" * 60)
        logger.info("数据库迁移完成！")
        logger.info("数据丢失校验通过！")
        if violations_stats:
            logger.info(f"外键约束违反统计: {sum(violations_stats.values())} 条记录")
            logger.info(
                f"已处理 {processed_count} 条违反外键约束的记录（设置为 NULL 或删除）"
            )
        else:
            logger.info("未发现外键约束违反")
        logger.info("=" * 60)

        # 用户确认
        logger.info("=" * 60)
        logger.info("迁移和校验已完成，请确认是否接受此次迁移")
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
