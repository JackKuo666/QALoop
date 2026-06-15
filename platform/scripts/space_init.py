#!/usr/bin/env python
"""Hugging Face Space 启动初始化：导入 Demo 数据、建表并创建管理员账号。"""

import codecs
import os
import re
import sqlite3
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from qa_annotate.bootstrap import ensure_llm_config, seed_demo_llm_analysis  # noqa: E402
from qa_annotate.config import settings  # noqa: E402
from qa_annotate.database.base import SessionLocal, init_db  # noqa: E402
from qa_annotate.database.crud import UserCRUD  # noqa: E402
from qa_annotate.schema.user import UserCreate, UserUpdate  # noqa: E402
from qa_annotate.utils.password import hash_password  # noqa: E402


def _project_count(db_path: Path) -> int:
    if not db_path.exists():
        return 0
    with sqlite3.connect(db_path) as conn:
        try:
            return conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
        except sqlite3.OperationalError:
            return 0


def _sanitize_seed_sql(sql: str) -> str:
    """部分 sqlite3 .dump 会输出 Oracle 的 unistr()，标准 SQLite 不支持。"""

    def replace_unistr(match: re.Match[str]) -> str:
        decoded = codecs.decode(match.group(1), "unicode_escape")
        return "'" + decoded.replace("'", "''") + "'"

    return re.sub(r"unistr\('((?:[^'\\]|\\.)*)'\)", replace_unistr, sql)


def seed_demo_database() -> None:
    if os.environ.get("SEED_DEMO_DATA", "true").lower() not in ("1", "true", "yes"):
        print("SEED_DEMO_DATA 已关闭，跳过示例数据导入")
        return

    seed_path = project_root / "seed" / "demo.sql"
    if not seed_path.exists():
        print("未找到 seed/demo.sql，跳过示例数据导入")
        return

    db_path = settings.db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if _project_count(db_path) > 0:
        print("数据库已有项目数据，跳过示例数据导入")
        return

    sql = _sanitize_seed_sql(seed_path.read_text(encoding="utf-8"))
    with sqlite3.connect(db_path) as conn:
        conn.executescript(sql)
    print(f"已从 seed/demo.sql 导入 Demo 示例数据: {db_path}")


def ensure_superuser() -> None:
    username = os.environ.get("ADMIN_USERNAME", "admin").strip()
    password = os.environ.get("ADMIN_PASSWORD", "123456")
    if not username:
        print("ADMIN_USERNAME 为空，跳过管理员初始化")
        return

    db = SessionLocal()
    try:
        existing = UserCRUD.get_by_username(db, username=username)
        if existing:
            if not existing.is_superuser or not existing.is_active:
                UserCRUD.update(
                    db,
                    user_id=existing.id,
                    user_update=UserUpdate(is_superuser=True, is_active=True),
                )
                print(f"已将用户 '{username}' 提升为超级用户")
            else:
                print(f"超级用户 '{username}' 已存在，跳过创建")
            return

        user_create = UserCreate(
            username=username,
            password=hash_password(password),
            is_active=True,
            is_superuser=True,
        )
        UserCRUD.create(db=db, user=user_create)
        print(f"超级用户 '{username}' 创建成功")
    finally:
        db.close()


def main() -> None:
    seed_demo_database()
    init_db()
    ensure_superuser()
    ensure_llm_config()
    seed_demo_llm_analysis()


if __name__ == "__main__":
    main()
