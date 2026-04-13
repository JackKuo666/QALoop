#!/usr/bin/env python
"""创建超级用户脚本"""

import argparse
import getpass
import sys
from pathlib import Path

# 添加项目根目录到路径（脚本在 scripts 目录下，需要指向上一级目录）
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 在添加路径后再导入项目模块
from qa_annotate.database.base import SessionLocal, init_db  # noqa: E402
from qa_annotate.database.crud import UserCRUD  # noqa: E402
from qa_annotate.schema.user import UserCreate, UserUpdate  # noqa: E402
from qa_annotate.utils.password import hash_password  # noqa: E402


def create_superuser(
    username=None, password=None, full_name=None, update_existing=False
):
    """创建超级用户

    Args:
        username: 用户名（如果为None则从命令行输入）
        password: 密码（如果为None则从命令行输入）
        full_name: 全名（可选）
        update_existing: 如果用户已存在，是否将其提升为超级用户

    Returns:
        bool: 是否成功
    """
    # 初始化数据库（确保表存在）
    init_db()

    # 获取数据库会话
    db = SessionLocal()

    try:
        # 获取用户输入
        print("=" * 50)
        print("创建超级用户")
        print("=" * 50)

        # 获取用户名
        if username is None:
            username = input("请输入用户名: ").strip()
        else:
            print(f"用户名: {username}")

        if not username:
            print("错误: 用户名不能为空")
            return False

        # 检查用户名是否已存在
        existing_user = UserCRUD.get_by_username(db, username=username)
        if existing_user:
            if update_existing:
                # 将现有用户提升为超级用户
                print(f"用户 '{username}' 已存在，正在将其提升为超级用户...")
                user_update = UserUpdate(is_superuser=True, is_active=True)
                updated_user = UserCRUD.update(
                    db=db, user_id=existing_user.id, user_update=user_update
                )

                print("\n" + "=" * 50)
                print("用户已成功提升为超级用户！")
                print("=" * 50)
                print(f"用户ID: {updated_user.id}")
                print(f"用户名: {updated_user.username}")
                print(f"全名: {updated_user.full_name or '(未设置)'}")
                print(f"是否激活: {updated_user.is_active}")
                print(f"是否超级用户: {updated_user.is_superuser}")
                print("=" * 50)
                return True
            else:
                print(f"错误: 用户名 '{username}' 已存在")
                print("提示: 使用 --update 参数可以将现有用户提升为超级用户")
                return False

        # 获取密码
        is_interactive = password is None
        if password is None:
            password = getpass.getpass("请输入密码: ")
        else:
            print("密码: ***")

        if not password:
            print("错误: 密码不能为空")
            return False

        if len(password) < 6:
            print("错误: 密码长度至少为6位")
            return False

        # 确认密码（仅在交互模式下）
        if is_interactive:
            password_confirm = getpass.getpass("请再次输入密码: ")
            if password != password_confirm:
                print("错误: 两次输入的密码不一致")
                return False

        # 获取全名（可选）
        if full_name is None:
            full_name = input("请输入全名（可选，直接回车跳过）: ").strip()
            if not full_name:
                full_name = None

        # 对密码进行SHA-256哈希
        password_hash = hash_password(password)

        # 创建超级用户
        user_create = UserCreate(
            username=username,
            password=password_hash,  # 存储哈希值
            full_name=full_name,
            is_active=True,
            is_superuser=True,
        )

        user = UserCRUD.create(db=db, user=user_create)

        print("\n" + "=" * 50)
        print("超级用户创建成功！")
        print("=" * 50)
        print(f"用户ID: {user.id}")
        print(f"用户名: {user.username}")
        print(f"全名: {user.full_name or '(未设置)'}")
        print(f"是否激活: {user.is_active}")
        print(f"是否超级用户: {user.is_superuser}")
        print("=" * 50)

        return True

    except KeyboardInterrupt:
        print("\n\n操作已取消")
        return False
    except Exception as e:
        print(f"\n错误: 创建超级用户失败 - {str(e)}")
        import traceback

        traceback.print_exc()
        return False
    finally:
        db.close()


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="创建或更新超级用户",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 交互式创建超级用户（从项目根目录运行）
  python scripts/create_superuser.py

  # 使用命令行参数创建
  python scripts/create_superuser.py --username admin --password admin123

  # 将现有用户提升为超级用户
  python scripts/create_superuser.py --username existing_user --update
        """,
    )

    parser.add_argument("--username", "-u", type=str, help="用户名")

    parser.add_argument(
        "--password",
        "-p",
        type=str,
        help="密码（不推荐在命令行中使用，建议留空以交互式输入）",
    )

    parser.add_argument("--full-name", "-n", type=str, dest="full_name", help="全名")

    parser.add_argument(
        "--update", action="store_true", help="如果用户已存在，将其提升为超级用户"
    )

    args = parser.parse_args()

    success = create_superuser(
        username=args.username,
        password=args.password,
        full_name=args.full_name,
        update_existing=args.update,
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
