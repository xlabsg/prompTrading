"""
State Persistence

状态持久化：Redis 热存储
"""
import json
import logging
from abc import ABC, abstractmethod
from typing import Optional
from .trading_state import TradingState

logger = logging.getLogger(__name__)


class StateStore(ABC):
    """状态存储抽象基类"""

    @abstractmethod
    def save(self, state: TradingState) -> None:
        """保存状态"""
        pass

    @abstractmethod
    def load(self, session_id: str) -> Optional[TradingState]:
        """加载状态"""
        pass

    @abstractmethod
    def delete(self, session_id: str) -> None:
        """删除状态"""
        pass

    @abstractmethod
    def exists(self, session_id: str) -> bool:
        """检查状态是否存在"""
        pass


class RedisStateStore(StateStore):
    """Redis 状态存储（热存储）"""

    def __init__(
        self,
        redis_client,
        key_prefix: str = "trading:",
        ttl_seconds: int = 86400
    ):
        """
        初始化 Redis 状态存储

        Args:
            redis_client: Redis 客户端（假设使用 redis-py）
            key_prefix: 键前缀
            ttl_seconds: 过期时间（秒）
        """
        self.redis = redis_client
        self.key_prefix = key_prefix
        self.ttl_seconds = ttl_seconds

    def _get_key(self, session_id: str) -> str:
        """获取 Redis 键"""
        return f"{self.key_prefix}state:{session_id}"

    def save(self, state: TradingState) -> None:
        """保存状态到 Redis"""
        try:
            key = self._get_key(state.session_id)
            data = json.dumps(state.to_dict())
            self.redis.setex(key, self.ttl_seconds, data)
            logger.debug(f"State saved to Redis: {state.session_id}")
        except Exception as e:
            logger.error(f"Failed to save state to Redis: {e}")
            raise

    def load(self, session_id: str) -> Optional[TradingState]:
        """从 Redis 加载状态"""
        try:
            key = self._get_key(session_id)
            data = self.redis.get(key)
            if data:
                state_dict = json.loads(data)
                state = TradingState.from_dict(state_dict)
                logger.debug(f"State loaded from Redis: {session_id}")
                return state
            return None
        except Exception as e:
            logger.error(f"Failed to load state from Redis: {e}")
            return None

    def delete(self, session_id: str) -> None:
        """从 Redis 删除状态"""
        try:
            key = self._get_key(session_id)
            self.redis.delete(key)
            logger.debug(f"State deleted from Redis: {session_id}")
        except Exception as e:
            logger.error(f"Failed to delete state from Redis: {e}")

    def exists(self, session_id: str) -> bool:
        """检查 Redis 中是否存在状态"""
        try:
            key = self._get_key(session_id)
            return self.redis.exists(key) > 0
        except Exception as e:
            logger.error(f"Failed to check state existence in Redis: {e}")
            return False
