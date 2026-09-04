"""
Order Types and Utilities

订单类型定义和工具函数（包括 Snowflake ID 生成）
"""
import time
import os
import hashlib
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class SnowflakeIDGenerator:
    """
    Snowflake ID 生成器

    生成唯一的客户端订单 ID (clOrdId)
    格式: {prefix}{direction}{snowflake_base36}

    Snowflake 布局 (64 位):
    - 41 位: 时间戳（毫秒，自 2024-01-01）
    - 10 位: 节点 ID（主机 hash ^ PID）
    - 12 位: 序列（同毫秒内递增）
    """

    # 纪元起始时间: 2024-01-01 00:00:00 UTC (毫秒)
    EPOCH = 1704067200000

    # 位数配置
    TIMESTAMP_BITS = 41
    NODE_BITS = 10
    SEQUENCE_BITS = 12

    # 最大值
    MAX_NODE_ID = (1 << NODE_BITS) - 1
    MAX_SEQUENCE = (1 << SEQUENCE_BITS) - 1

    def __init__(self, node_id: Optional[int] = None):
        """
        初始化 Snowflake ID 生成器

        Args:
            node_id: 节点 ID (0-1023)，如果未提供则自动生成
        """
        if node_id is None:
            node_id = self._generate_node_id()

        if node_id < 0 or node_id > self.MAX_NODE_ID:
            raise ValueError(f"Node ID must be between 0 and {self.MAX_NODE_ID}")

        self.node_id = node_id
        self.sequence = 0
        self.last_timestamp = -1

        logger.info(f"Snowflake ID generator initialized with node_id={node_id}")

    def _generate_node_id(self) -> int:
        """自动生成节点 ID（基于主机名和 PID）"""
        hostname = os.uname().nodename
        pid = os.getpid()

        # 哈希主机名和 PID
        hash_input = f"{hostname}:{pid}".encode()
        hash_value = int(hashlib.md5(hash_input).hexdigest(), 16)

        # 取模到允许范围
        node_id = hash_value & self.MAX_NODE_ID

        return node_id

    def generate(self) -> int:
        """生成 Snowflake ID"""
        timestamp = self._get_timestamp()

        # 如果在同一毫秒内
        if timestamp == self.last_timestamp:
            self.sequence = (self.sequence + 1) & self.MAX_SEQUENCE
            # 序列溢出，等待下一毫秒
            if self.sequence == 0:
                timestamp = self._wait_next_millis(self.last_timestamp)
        else:
            self.sequence = 0

        # 时间回拨检测
        if timestamp < self.last_timestamp:
            raise RuntimeError(
                f"Clock moved backwards. Refusing to generate ID for "
                f"{self.last_timestamp - timestamp}ms"
            )

        self.last_timestamp = timestamp

        # 组合 ID
        snowflake_id = (
            ((timestamp - self.EPOCH) << (self.NODE_BITS + self.SEQUENCE_BITS)) |
            (self.node_id << self.SEQUENCE_BITS) |
            self.sequence
        )

        return snowflake_id

    def _get_timestamp(self) -> int:
        """获取当前时间戳（毫秒）"""
        return int(time.time() * 1000)

    def _wait_next_millis(self, last_timestamp: int) -> int:
        """等待下一毫秒"""
        timestamp = self._get_timestamp()
        while timestamp <= last_timestamp:
            timestamp = self._get_timestamp()
        return timestamp

    def to_base36(self, num: int) -> str:
        """将整数转换为 base36 字符串"""
        if num == 0:
            return '0'

        chars = '0123456789abcdefghijklmnopqrstuvwxyz'
        result = []

        while num:
            num, remainder = divmod(num, 36)
            result.append(chars[remainder])

        return ''.join(reversed(result))

    def generate_client_order_id(
        self,
        prefix: str,
        direction: str,
        max_length: int = 32
    ) -> str:
        """
        生成客户端订单 ID

        Args:
            prefix: 前缀（例如策略名）
            direction: 方向标识（L=long, S=short）
            max_length: 最大长度限制（OKX 限制 32 字符）

        Returns:
            客户端订单 ID
        """
        # 规范化前缀（只保留字母数字，转小写）
        normalized_prefix = ''.join(c for c in prefix if c.isalnum()).lower()

        # 生成 Snowflake ID 并转为 base36
        snowflake_id = self.generate()
        snowflake_str = self.to_base36(snowflake_id)

        # 组合: prefix + direction + snowflake
        cl_ord_id = f"{normalized_prefix}{direction}{snowflake_str}"

        # 如果超长，截断前缀
        if len(cl_ord_id) > max_length:
            available_prefix_len = max_length - len(direction) - len(snowflake_str)
            if available_prefix_len > 0:
                normalized_prefix = normalized_prefix[:available_prefix_len]
                cl_ord_id = f"{normalized_prefix}{direction}{snowflake_str}"
            else:
                # 如果还是超长，只保留方向和 snowflake
                cl_ord_id = f"{direction}{snowflake_str}"
                if len(cl_ord_id) > max_length:
                    cl_ord_id = cl_ord_id[:max_length]

        return cl_ord_id


# 全局单例
_global_generator: Optional[SnowflakeIDGenerator] = None


def get_global_generator() -> SnowflakeIDGenerator:
    """获取全局 Snowflake ID 生成器"""
    global _global_generator
    if _global_generator is None:
        _global_generator = SnowflakeIDGenerator()
    return _global_generator


def generate_client_order_id(
    prefix: str = "",
    direction: str = "",
    max_length: int = 32
) -> str:
    """
    便捷函数：生成客户端订单 ID

    Args:
        prefix: 前缀（例如策略名）
        direction: 方向标识（L=long, S=short）
        max_length: 最大长度限制

    Returns:
        客户端订单 ID
    """
    generator = get_global_generator()
    return generator.generate_client_order_id(prefix, direction, max_length)


def normalize_prefix(prefix: str, max_length: int = 18) -> str:
    """
    规范化前缀

    Args:
        prefix: 原始前缀
        max_length: 最大长度

    Returns:
        规范化后的前缀
    """
    # 只保留字母数字，转小写
    normalized = ''.join(c for c in prefix if c.isalnum()).lower()
    # 截断
    return normalized[:max_length]


def is_our_order(cl_ord_id: str, prefix: str) -> bool:
    """
    判断订单是否属于我们（通过前缀匹配）

    Args:
        cl_ord_id: 客户端订单 ID
        prefix: 我们的前缀

    Returns:
        是否属于我们
    """
    normalized_prefix = normalize_prefix(prefix)
    return cl_ord_id.lower().startswith(normalized_prefix)
