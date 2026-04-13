#!/usr/bin/env python
"""初始化问题类型脚本 - 从CSV文件导入类型/亚类数据到数据库"""

import argparse
import sys
from pathlib import Path

# 添加项目根目录到路径（脚本在 scripts 目录下，需要指向上一级目录）
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 在添加路径后再导入项目模块
from qa_annotate.database.base import SessionLocal, init_db  # noqa: E402
from qa_annotate.database.crud import QuestionTypeCRUD  # noqa: E402


def init_question_types(csv_path: str = None, clear_existing: bool = False):
    """从CSV文件导入类型/亚类数据

    Args:
        csv_path: CSV文件路径（如果为None则使用默认路径）
        clear_existing: 是否清空现有数据

    Returns:
        bool: 是否成功
    """
    # 初始化数据库（确保表存在）
    init_db()

    # 获取数据库会话
    db = SessionLocal()

    try:
        # 确定CSV文件路径
        if csv_path is None:
            csv_path = project_root / "data" / "shared" / "种子问题_纵向类型维度.csv"

        csv_file = Path(csv_path)
        if not csv_file.exists():
            print(f"错误: CSV文件不存在: {csv_file}")
            return False

        print("=" * 50)
        print("初始化问题类型")
        print("=" * 50)
        print(f"CSV文件路径: {csv_file}")

        # 如果指定清空现有数据
        if clear_existing:
            print("\n警告: 将清空所有现有问题类型数据...")
            existing_count = QuestionTypeCRUD.count(db)
            if existing_count > 0:
                # 删除所有现有数据
                all_types = QuestionTypeCRUD.get_all(db, skip=0, limit=10000)
                for qtype in all_types:
                    QuestionTypeCRUD.delete(db, qtype.id)
                print(f"已删除 {existing_count} 条现有数据")

        # 导入数据
        print("\n开始导入数据...")
        result = QuestionTypeCRUD.import_from_csv(db, str(csv_file))

        print("\n" + "=" * 50)
        print("导入完成！")
        print("=" * 50)
        print(f"成功导入: {result['imported_count']} 条")
        print(f"跳过（已存在）: {result['skipped_count']} 条")
        if result["errors"]:
            print(f"错误: {len(result['errors'])} 条")
            for error in result["errors"][:10]:  # 只显示前10个错误
                print(f"  - {error}")
        print("=" * 50)

        return True

    except KeyboardInterrupt:
        print("\n\n操作已取消")
        return False
    except Exception as e:
        print(f"\n错误: 导入失败 - {str(e)}")
        import traceback

        traceback.print_exc()
        return False
    finally:
        db.close()


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="从CSV文件导入问题类型/亚类数据到数据库",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 使用默认CSV文件路径导入
  python scripts/init_question_types.py

  # 指定CSV文件路径
  python scripts/init_question_types.py --csv-path /path/to/file.csv

  # 清空现有数据后导入
  python scripts/init_question_types.py --clear
        """,
    )

    parser.add_argument(
        "--csv-path",
        type=str,
        help="CSV文件路径（默认: data/shared/种子问题_纵向类型维度.csv）",
    )

    parser.add_argument(
        "--clear",
        action="store_true",
        help="清空现有数据后再导入",
    )

    args = parser.parse_args()

    success = init_question_types(
        csv_path=args.csv_path,
        clear_existing=args.clear,
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
