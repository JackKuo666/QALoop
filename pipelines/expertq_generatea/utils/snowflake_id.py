import time
import threading
from typing import Optional


class SnowflakeIDGenerator:
    """
    雪花ID生成器

    雪花ID结构 (64位):
    - 符号位: 1位，固定为0
    - 时间戳: 41位，毫秒级时间戳
    - 工作机器ID: 10位，包含5位数据中心ID和5位机器ID
    - 序列号: 12位，同一毫秒内的自增序列

    特点:
    - 趋势递增
    - 全局唯一
    - 支持分布式环境
    - 高性能
    """

    def __init__(self, datacenter_id: int = 1, worker_id: int = 1, sequence: int = 0):
        """
        初始化雪花ID生成器

        Args:
            datacenter_id: 数据中心ID (0-31)
            worker_id: 工作机器ID (0-31)
            sequence: 初始序列号
        """
        # 位数分配
        self.TIMESTAMP_BITS = 41
        self.DATACENTER_ID_BITS = 5
        self.WORKER_ID_BITS = 5
        self.SEQUENCE_BITS = 12

        # 最大值
        self.MAX_DATACENTER_ID = -1 ^ (-1 << self.DATACENTER_ID_BITS)
        self.MAX_WORKER_ID = -1 ^ (-1 << self.WORKER_ID_BITS)
        self.MAX_SEQUENCE = -1 ^ (-1 << self.SEQUENCE_BITS)

        # 偏移量
        self.WORKER_ID_SHIFT = self.SEQUENCE_BITS
        self.DATACENTER_ID_SHIFT = self.SEQUENCE_BITS + self.WORKER_ID_BITS
        self.TIMESTAMP_LEFT_SHIFT = (
            self.SEQUENCE_BITS + self.WORKER_ID_BITS + self.DATACENTER_ID_BITS
        )

        # 验证参数
        if datacenter_id > self.MAX_DATACENTER_ID or datacenter_id < 0:
            raise ValueError(
                f"Datacenter ID must be between 0 and {self.MAX_DATACENTER_ID}"
            )
        if worker_id > self.MAX_WORKER_ID or worker_id < 0:
            raise ValueError(f"Worker ID must be between 0 and {self.MAX_WORKER_ID}")

        self.datacenter_id = datacenter_id
        self.worker_id = worker_id
        self.sequence = sequence

        # 时间戳基准点 (2023-01-01 00:00:00 UTC)
        self.EPOCH = 1672531200000

        # 上次生成ID的时间戳
        self.last_timestamp = -1

        # 线程锁
        self.lock = threading.Lock()

    def _get_timestamp(self) -> int:
        """
        获取当前毫秒时间戳

        Returns:
            当前毫秒时间戳
        """
        return int(time.time() * 1000)

    def _wait_for_next_millis(self, last_timestamp: int) -> int:
        """
        等待到下一毫秒

        Args:
            last_timestamp: 上次时间戳

        Returns:
            新的时间戳
        """
        timestamp = self._get_timestamp()
        while timestamp <= last_timestamp:
            timestamp = self._get_timestamp()
        return timestamp

    def generate_id(self) -> int:
        """
        生成雪花ID

        Returns:
            64位雪花ID

        Raises:
            RuntimeError: 时钟回拨时抛出异常
        """
        with self.lock:
            timestamp = self._get_timestamp()

            # 检查时钟回拨
            if timestamp < self.last_timestamp:
                raise RuntimeError(
                    f"Clock moved backwards. Refusing to generate id for {self.last_timestamp - timestamp} milliseconds"
                )

            # 如果是同一毫秒内
            if timestamp == self.last_timestamp:
                self.sequence = (self.sequence + 1) & self.MAX_SEQUENCE
                # 如果序列号溢出，等待下一毫秒
                if self.sequence == 0:
                    timestamp = self._wait_for_next_millis(self.last_timestamp)
            else:
                # 不同毫秒，序列号重置
                self.sequence = 0

            self.last_timestamp = timestamp

            # 生成ID
            snowflake_id = (
                ((timestamp - self.EPOCH) << self.TIMESTAMP_LEFT_SHIFT)
                | (self.datacenter_id << self.DATACENTER_ID_SHIFT)
                | (self.worker_id << self.WORKER_ID_SHIFT)
                | self.sequence
            )

            return snowflake_id

    def generate_id_str(self) -> str:
        """
        生成字符串格式的雪花ID

        Returns:
            字符串格式的雪花ID
        """
        return str(self.generate_id())

    def parse_id(self, snowflake_id: int) -> dict:
        """
        解析雪花ID

        Args:
            snowflake_id: 雪花ID

        Returns:
            包含解析结果的字典
        """
        timestamp = (snowflake_id >> self.TIMESTAMP_LEFT_SHIFT) + self.EPOCH
        datacenter_id = (
            snowflake_id >> self.DATACENTER_ID_SHIFT
        ) & self.MAX_DATACENTER_ID
        worker_id = (snowflake_id >> self.WORKER_ID_SHIFT) & self.MAX_WORKER_ID
        sequence = snowflake_id & self.MAX_SEQUENCE

        return {
            "timestamp": timestamp,
            "datacenter_id": datacenter_id,
            "worker_id": worker_id,
            "sequence": sequence,
            "datetime": time.strftime(
                "%Y-%m-%d %H:%M:%S", time.localtime(timestamp / 1000)
            ),
        }


# 全局雪花ID生成器实例
_snowflake_generator: Optional[SnowflakeIDGenerator] = None
_generator_lock = threading.Lock()


def get_snowflake_generator(
    datacenter_id: int = 1, worker_id: int = 1
) -> SnowflakeIDGenerator:
    """
    获取全局雪花ID生成器实例

    Args:
        datacenter_id: 数据中心ID
        worker_id: 工作机器ID

    Returns:
        雪花ID生成器实例
    """
    global _snowflake_generator

    if _snowflake_generator is None:
        with _generator_lock:
            if _snowflake_generator is None:
                _snowflake_generator = SnowflakeIDGenerator(datacenter_id, worker_id)

    return _snowflake_generator


def generate_snowflake_id() -> int:
    """
    生成雪花ID (使用默认配置)

    Returns:
        64位雪花ID
    """
    return get_snowflake_generator().generate_id()


def generate_snowflake_id_str() -> str:
    """
    生成字符串格式的雪花ID (使用默认配置)

    Returns:
        字符串格式的雪花ID
    """
    return get_snowflake_generator().generate_id_str()


def parse_snowflake_id(snowflake_id: int) -> dict:
    """
    解析雪花ID

    Args:
        snowflake_id: 雪花ID

    Returns:
        包含解析结果的字典
    """
    return get_snowflake_generator().parse_id(snowflake_id)


# 便捷函数
def snowflake_id() -> int:
    """
    快速生成雪花ID的便捷函数

    Returns:
        64位雪花ID
    """
    return generate_snowflake_id()


def snowflake_id_str() -> str:
    """
    快速生成字符串格式雪花ID的便捷函数

    Returns:
        字符串格式的雪花ID
    """
    return generate_snowflake_id_str()
