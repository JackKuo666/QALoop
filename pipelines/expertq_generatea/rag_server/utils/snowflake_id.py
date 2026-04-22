import time
import threading
from typing import Optional


class SnowflakeIDGenerator:
    """雪花ID生成器"""

    def __init__(self, datacenter_id: int = 1, worker_id: int = 1, sequence: int = 0):
        self.TIMESTAMP_BITS = 41
        self.DATACENTER_ID_BITS = 5
        self.WORKER_ID_BITS = 5
        self.SEQUENCE_BITS = 12

        self.MAX_DATACENTER_ID = -1 ^ (-1 << self.DATACENTER_ID_BITS)
        self.MAX_WORKER_ID = -1 ^ (-1 << self.WORKER_ID_BITS)
        self.MAX_SEQUENCE = -1 ^ (-1 << self.SEQUENCE_BITS)

        self.WORKER_ID_SHIFT = self.SEQUENCE_BITS
        self.DATACENTER_ID_SHIFT = self.SEQUENCE_BITS + self.WORKER_ID_BITS
        self.TIMESTAMP_LEFT_SHIFT = (
            self.SEQUENCE_BITS + self.WORKER_ID_BITS + self.DATACENTER_ID_BITS
        )

        if datacenter_id > self.MAX_DATACENTER_ID or datacenter_id < 0:
            raise ValueError(f"Datacenter ID must be between 0 and {self.MAX_DATACENTER_ID}")
        if worker_id > self.MAX_WORKER_ID or worker_id < 0:
            raise ValueError(f"Worker ID must be between 0 and {self.MAX_WORKER_ID}")

        self.datacenter_id = datacenter_id
        self.worker_id = worker_id
        self.sequence = sequence
        self.EPOCH = 1672531200000  # 2023-01-01 UTC
        self.last_timestamp = -1
        self.lock = threading.Lock()

    def _get_timestamp(self) -> int:
        return int(time.time() * 1000)

    def _wait_for_next_millis(self, last_timestamp: int) -> int:
        timestamp = self._get_timestamp()
        while timestamp <= last_timestamp:
            timestamp = self._get_timestamp()
        return timestamp

    def generate_id(self) -> int:
        with self.lock:
            timestamp = self._get_timestamp()
            if timestamp < self.last_timestamp:
                raise RuntimeError("Clock moved backwards")
            if timestamp == self.last_timestamp:
                self.sequence = (self.sequence + 1) & self.MAX_SEQUENCE
                if self.sequence == 0:
                    timestamp = self._wait_for_next_millis(self.last_timestamp)
            else:
                self.sequence = 0
            self.last_timestamp = timestamp
            return (
                ((timestamp - self.EPOCH) << self.TIMESTAMP_LEFT_SHIFT)
                | (self.datacenter_id << self.DATACENTER_ID_SHIFT)
                | (self.worker_id << self.WORKER_ID_SHIFT)
                | self.sequence
            )

    def generate_id_str(self) -> str:
        return str(self.generate_id())


_snowflake_generator: Optional[SnowflakeIDGenerator] = None


def get_snowflake_generator(datacenter_id: int = 1, worker_id: int = 1) -> SnowflakeIDGenerator:
    global _snowflake_generator
    if _snowflake_generator is None:
        _snowflake_generator = SnowflakeIDGenerator(datacenter_id, worker_id)
    return _snowflake_generator


def snowflake_id_str() -> str:
    return get_snowflake_generator().generate_id_str()
