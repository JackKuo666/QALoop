#!/usr/bin/env python
"""数据库备份脚本

支持手动备份和定期自动备份。
可以配置备份频率、保留天数、压缩等选项。
"""

import argparse
import gzip
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path
import logging

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from qa_annotate.database.base import DB_PATH, DB_DIR  # noqa: E402


# 配置日志
def setup_logging(log_file=None, log_level=logging.INFO):
    """设置日志配置"""
    log_format = "%(asctime)s - %(levelname)s - %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    handlers = [logging.StreamHandler(sys.stdout)]
    if log_file:
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))

    logging.basicConfig(
        level=log_level, format=log_format, datefmt=date_format, handlers=handlers
    )


def backup_database(
    backup_dir=None, compress=True, max_backups=30, backup_prefix="annotations_backup"
):
    """备份数据库

    Args:
        backup_dir: 备份目录路径（如果为None，则使用 data/backups）
        compress: 是否压缩备份文件
        max_backups: 保留的最大备份数量（超过此数量会删除最旧的备份）
        backup_prefix: 备份文件前缀

    Returns:
        Path: 备份文件路径，如果失败则返回None
    """
    try:
        # 检查源数据库文件是否存在
        if not DB_PATH.exists():
            logging.error(f"数据库文件不存在: {DB_PATH}")
            return None

        # 确定备份目录
        if backup_dir is None:
            backup_dir = DB_DIR / "backups"
        else:
            backup_dir = Path(backup_dir)

        # 创建备份目录
        backup_dir.mkdir(parents=True, exist_ok=True)

        # 生成备份文件名（包含时间戳）
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"{backup_prefix}_{timestamp}.db"

        if compress:
            backup_filename += ".gz"

        backup_path = backup_dir / backup_filename

        # 执行备份
        logging.info(f"开始备份数据库: {DB_PATH} -> {backup_path}")

        if compress:
            # 使用 gzip 压缩备份
            with open(DB_PATH, "rb") as f_in:
                with gzip.open(backup_path, "wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)
            logging.info(f"数据库已压缩备份到: {backup_path}")
        else:
            # 直接复制文件
            shutil.copy2(DB_PATH, backup_path)
            logging.info(f"数据库已备份到: {backup_path}")

        # 获取备份文件大小
        backup_size = backup_path.stat().st_size
        size_mb = backup_size / (1024 * 1024)
        logging.info(f"备份文件大小: {size_mb:.2f} MB")

        # 清理旧备份
        cleanup_old_backups(backup_dir, max_backups, backup_prefix, compress)

        return backup_path

    except Exception as e:
        logging.error(f"备份失败: {str(e)}", exc_info=True)
        return None


def cleanup_old_backups(backup_dir, max_backups, backup_prefix, compress):
    """清理旧的备份文件

    Args:
        backup_dir: 备份目录
        max_backups: 保留的最大备份数量
        backup_prefix: 备份文件前缀
        compress: 是否压缩（用于匹配文件扩展名）
    """
    try:
        # 获取所有备份文件
        pattern = f"{backup_prefix}_*.db"
        if compress:
            pattern += ".gz"

        backup_files = sorted(
            backup_dir.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True
        )

        # 如果备份数量超过限制，删除最旧的
        if len(backup_files) > max_backups:
            files_to_delete = backup_files[max_backups:]
            total_size = 0
            for file_path in files_to_delete:
                file_size = file_path.stat().st_size
                total_size += file_size
                file_path.unlink()
                logging.info(f"已删除旧备份: {file_path.name}")

            size_mb = total_size / (1024 * 1024)
            logging.info(
                f"已清理 {len(files_to_delete)} 个旧备份，释放空间: {size_mb:.2f} MB"
            )

    except Exception as e:
        logging.warning(f"清理旧备份时出错: {str(e)}")


def cleanup_backups_by_age(backup_dir, days_to_keep, backup_prefix, compress):
    """根据保留天数清理备份文件

    Args:
        backup_dir: 备份目录
        days_to_keep: 保留天数
        backup_prefix: 备份文件前缀
        compress: 是否压缩（用于匹配文件，但函数会同时处理压缩和非压缩文件）
    """
    try:
        cutoff_date = datetime.now() - timedelta(days=days_to_keep)

        # 获取所有备份文件（包括压缩和非压缩的）
        patterns = [
            f"{backup_prefix}_*.db.gz",  # 压缩备份
            f"{backup_prefix}_*.db",  # 非压缩备份
        ]

        backup_files = []
        for pattern in patterns:
            backup_files.extend(backup_dir.glob(pattern))

        deleted_count = 0
        total_size = 0

        for file_path in backup_files:
            # 从文件名中提取时间戳
            try:
                # 文件名格式: backup_prefix_YYYYMMDD_HHMMSS.db[.gz]
                name = file_path.name
                # 去掉扩展名
                if name.endswith(".gz"):
                    name = name[:-3]  # 去掉 .gz
                if name.endswith(".db"):
                    name = name[:-3]  # 去掉 .db

                # 提取时间戳部分
                timestamp_str = name.replace(f"{backup_prefix}_", "")
                file_date = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")

                if file_date < cutoff_date:
                    file_size = file_path.stat().st_size
                    total_size += file_size
                    file_path.unlink()
                    deleted_count += 1
                    logging.info(
                        f"已删除过期备份: {file_path.name} (创建于 {file_date.strftime('%Y-%m-%d %H:%M:%S')})"
                    )
            except (ValueError, IndexError):
                # 如果无法解析文件名，跳过
                logging.warning(f"无法解析备份文件名: {file_path.name}, 跳过")
                continue

        if deleted_count > 0:
            size_mb = total_size / (1024 * 1024)
            logging.info(
                f"已清理 {deleted_count} 个过期备份，释放空间: {size_mb:.2f} MB"
            )

    except Exception as e:
        logging.warning(f"按日期清理备份时出错: {str(e)}")


def run_scheduled_backup(
    interval_hours=24,
    backup_dir=None,
    compress=True,
    max_backups=30,
    backup_prefix="annotations_backup",
    log_file=None,
):
    """运行定期备份任务

    Args:
        interval_hours: 备份间隔（小时）
        backup_dir: 备份目录
        compress: 是否压缩
        max_backups: 保留的最大备份数量
        backup_prefix: 备份文件前缀
        log_file: 日志文件路径
    """
    try:
        import schedule
        import time
    except ImportError:
        logging.error("需要安装 schedule 库才能使用定期备份功能")
        logging.error("请运行: pip install schedule")
        return

    setup_logging(log_file=log_file)

    logging.info("=" * 60)
    logging.info("数据库定期备份服务启动")
    logging.info(f"备份间隔: 每 {interval_hours} 小时")
    logging.info(f"备份目录: {backup_dir or (DB_DIR / 'backups')}")
    logging.info(f"压缩备份: {compress}")
    logging.info(f"最大备份数: {max_backups}")
    logging.info("=" * 60)

    # 立即执行一次备份
    backup_database(backup_dir, compress, max_backups, backup_prefix)

    # 设置定期任务
    schedule.every(interval_hours).hours.do(
        backup_database,
        backup_dir=backup_dir,
        compress=compress,
        max_backups=max_backups,
        backup_prefix=backup_prefix,
    )

    # 运行调度器
    try:
        while True:
            schedule.run_pending()
            time.sleep(60)  # 每分钟检查一次
    except KeyboardInterrupt:
        logging.info("\n定期备份服务已停止")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="数据库备份工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 手动执行一次备份
  python scripts/backup_db.py

  # 指定备份目录
  python scripts/backup_db.py --backup-dir /path/to/backups

  # 不压缩备份
  python scripts/backup_db.py --no-compress

  # 设置保留备份数量
  python scripts/backup_db.py --max-backups 10

  # 启动定期备份服务（每24小时备份一次）
  python scripts/backup_db.py --schedule --interval 24

  # 启动定期备份服务（每12小时备份一次）
  python scripts/backup_db.py --schedule --interval 12
        """,
    )

    parser.add_argument(
        "--backup-dir",
        "-d",
        type=str,
        default=None,
        help="备份目录路径（默认: data/backups）",
    )

    parser.add_argument("--no-compress", action="store_true", help="不压缩备份文件")

    parser.add_argument(
        "--max-backups",
        "-n",
        type=int,
        default=30,
        help="保留的最大备份数量（默认: 30）",
    )

    parser.add_argument(
        "--backup-prefix",
        type=str,
        default="annotations_backup",
        help="备份文件前缀（默认: annotations_backup）",
    )

    parser.add_argument(
        "--schedule", "-s", action="store_true", help="启动定期备份服务"
    )

    parser.add_argument(
        "--interval", "-i", type=int, default=24, help="定期备份间隔（小时，默认: 24）"
    )

    parser.add_argument(
        "--log-file", type=str, default=None, help="日志文件路径（默认: 输出到控制台）"
    )

    parser.add_argument(
        "--log-level",
        type=str,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="日志级别（默认: INFO）",
    )

    parser.add_argument(
        "--cleanup-days",
        type=int,
        default=None,
        help="清理指定天数之前的备份（可选，与 --max-backups 配合使用）",
    )

    args = parser.parse_args()

    # 设置日志
    log_level = getattr(logging, args.log_level)
    setup_logging(log_file=args.log_file, log_level=log_level)

    # 如果启用定期备份
    if args.schedule:
        run_scheduled_backup(
            interval_hours=args.interval,
            backup_dir=args.backup_dir,
            compress=not args.no_compress,
            max_backups=args.max_backups,
            backup_prefix=args.backup_prefix,
            log_file=args.log_file,
        )
    else:
        # 执行单次备份
        backup_path = backup_database(
            backup_dir=args.backup_dir,
            compress=not args.no_compress,
            max_backups=args.max_backups,
            backup_prefix=args.backup_prefix,
        )

        # 如果指定了清理天数，执行按日期清理
        if args.cleanup_days:
            backup_dir = args.backup_dir or (DB_DIR / "backups")
            cleanup_backups_by_age(
                backup_dir=backup_dir,
                days_to_keep=args.cleanup_days,
                backup_prefix=args.backup_prefix,
                compress=not args.no_compress,
            )

        if backup_path:
            logging.info("备份完成！")
            sys.exit(0)
        else:
            logging.error("备份失败！")
            sys.exit(1)


if __name__ == "__main__":
    main()
