"""
State Persistence

状态持久化：Redis + PostgreSQL 双写
"""
import json
import logging
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from threading import Lock
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


class PostgreSQLStateStore(StateStore):
    """PostgreSQL 状态存储（冷存储）"""

    def __init__(self, db_session_factory):
        """
        初始化 PostgreSQL 状态存储

        Args:
            db_session_factory: 数据库会话工厂（例如 sessionmaker）
        """
        self.db_session_factory = db_session_factory

    def save(self, state: TradingState) -> None:
        """保存状态到 PostgreSQL"""
        # 注意：这里需要实际的 ORM 模型，简化实现
        logger.debug(f"State would be saved to PostgreSQL: {state.session_id}")
        # 实际实现中应该使用 TradingSession 模型更新
        pass

    def load(self, session_id: str) -> Optional[TradingState]:
        """从 PostgreSQL 加载状态"""
        logger.debug(f"State would be loaded from PostgreSQL: {session_id}")
        # 实际实现中应该从 TradingSession 表查询
        return None

    def delete(self, session_id: str) -> None:
        """从 PostgreSQL 删除状态"""
        logger.debug(f"State would be deleted from PostgreSQL: {session_id}")
        pass

    def exists(self, session_id: str) -> bool:
        """检查 PostgreSQL 中是否存在状态"""
        return False


class DualStateStore(StateStore):
    """双层状态存储（Redis + PostgreSQL）"""

    def __init__(
        self,
        redis_store: Optional[RedisStateStore] = None,
        postgres_store: Optional[PostgreSQLStateStore] = None,
        save_interval_seconds: float = 1.0
    ):
        """
        初始化双层状态存储

        Args:
            redis_store: Redis 存储（热存储）
            postgres_store: PostgreSQL 存储（冷存储）
            save_interval_seconds: 保存间隔（限流）
        """
        self.redis_store = redis_store
        self.postgres_store = postgres_store
        self.save_interval_seconds = save_interval_seconds

        # 限流控制
        self._last_save_time: Dict[str, datetime] = {}
        self._lock = Lock()

    def save(self, state: TradingState) -> None:
        """保存状态（带限流）"""
        with self._lock:
            session_id = state.session_id
            now = datetime.utcnow()

            # 检查是否应该保存（限流）
            last_save = self._last_save_time.get(session_id)
            if last_save:
                elapsed = (now - last_save).total_seconds()
                if elapsed < self.save_interval_seconds:
                    logger.debug(f"Skipping save due to rate limit: {session_id}")
                    return

            # 保存到 Redis（快速）
            if self.redis_store:
                try:
                    self.redis_store.save(state)
                except Exception as e:
                    logger.error(f"Failed to save to Redis: {e}")

            # 保存到 PostgreSQL（慢，异步）
            if self.postgres_store:
                try:
                    self.postgres_store.save(state)
                except Exception as e:
                    logger.error(f"Failed to save to PostgreSQL: {e}")

            self._last_save_time[session_id] = now

    def load(self, session_id: str) -> Optional[TradingState]:
        """加载状态（优先 Redis）"""
        # 优先从 Redis 加载
        if self.redis_store:
            state = self.redis_store.load(session_id)
            if state:
                return state

        # Redis 未命中，从 PostgreSQL 加载
        if self.postgres_store:
            state = self.postgres_store.load(session_id)
            if state and self.redis_store:
                # 回填到 Redis
                try:
                    self.redis_store.save(state)
                except Exception as e:
                    logger.error(f"Failed to backfill Redis: {e}")
            return state

        return None

    def delete(self, session_id: str) -> None:
        """删除状态"""
        if self.redis_store:
            self.redis_store.delete(session_id)
        if self.postgres_store:
            self.postgres_store.delete(session_id)

        with self._lock:
            self._last_save_time.pop(session_id, None)

    def exists(self, session_id: str) -> bool:
        """检查状态是否存在"""
        if self.redis_store and self.redis_store.exists(session_id):
            return True
        if self.postgres_store and self.postgres_store.exists(session_id):
            return True
        return False

