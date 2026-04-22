"""Bio Logger - logging utility with correlation ID support"""
import sys
from pathlib import Path
from loguru import logger


def setup_logger(log_dir: str = "logs", level: str = "INFO"):
    """Setup loguru logger"""
    logger.remove()
    logger.add(
        sys.stderr,
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {message}",
        level=level,
        colorize=True
    )
    Path(log_dir).mkdir(exist_ok=True)
    logger.add(
        f"{log_dir}/bio_rag_{{time:YYYY-MM-DD}}.log",
        rotation="1 day",
        retention="30 days",
        level=level
    )
    return logger


bio_logger = setup_logger()
