"""
Stop Loss Strategies

实现普通止损和移动止损逻辑
"""
import logging
from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Optional, Dict, Any
from ..core import (
    Position, PositionSide, TrailingStopConfig,
    ActivationType, DistanceType
)

logger = logging.getLogger(__name__)


class StopLossStrategy(ABC):
    """止损策略基类"""

    @abstractmethod
    def should_trigger(self, position: Position, current_price: Decimal) -> bool:
        """判断是否应该触发止损"""
        pass

    @abstractmethod
    def get_stop_price(self, position: Position) -> Optional[Decimal]:
        """获取当前止损价格"""
        pass

    @abstractmethod
    def update(self, position: Position, current_price: Decimal) -> None:
        """更新止损状态"""
        pass

    @abstractmethod
    def get_state(self) -> Dict[str, Any]:
        """获取状态（用于持久化）"""
        pass

    @abstractmethod
    def restore_state(self, state: Dict[str, Any]) -> None:
        """恢复状态（用于重启恢复）"""
        pass


class FixedStopLoss(StopLossStrategy):
    """固定止损"""

    def __init__(self):
        pass

    def should_trigger(self, position: Position, current_price: Decimal) -> bool:
        """判断是否触发固定止损"""
        if not position.stop_loss:
            return False

        if position.side == PositionSide.LONG:
            return current_price <= position.stop_loss
        else:  # SHORT
            return current_price >= position.stop_loss

    def get_stop_price(self, position: Position) -> Optional[Decimal]:
        """获取止损价格"""
        return position.stop_loss

    def update(self, position: Position, current_price: Decimal) -> None:
        """固定止损不需要更新"""
        pass

    def get_state(self) -> Dict[str, Any]:
        """固定止损无状态"""
        return {}

    def restore_state(self, state: Dict[str, Any]) -> None:
        """固定止损无状态"""
        pass


class TrailingStopLoss(StopLossStrategy):
    """移动止损"""

    def __init__(self, config: TrailingStopConfig, atr: Optional[float] = None):
        self.config = config
        self.atr = atr

        # 状态
        self.activated: bool = False
        self.activation_price: Optional[Decimal] = None
        self.trail_stop_price: Optional[Decimal] = None
        self.highest_price: Optional[Decimal] = None  # Long 用
        self.lowest_price: Optional[Decimal] = None  # Short 用

    def should_trigger(self, position: Position, current_price: Decimal) -> bool:
        """判断是否触发移动止损"""
        if not self.activated or not self.trail_stop_price:
            return False

        if position.side == PositionSide.LONG:
            return current_price <= self.trail_stop_price
        else:  # SHORT
            return current_price >= self.trail_stop_price

    def get_stop_price(self, position: Position) -> Optional[Decimal]:
        """获取当前止损价格"""
        if self.activated:
            return self.trail_stop_price
        return position.stop_loss  # 未激活时返回初始止损

    def update(self, position: Position, current_price: Decimal) -> None:
        """更新移动止损"""
        # 检查是否应该激活
        if not self.activated:
            if self._should_activate(position, current_price):
                self._activate(position, current_price)

        # 如果已激活，更新追踪止损
        if self.activated:
            self._update_trailing_stop(position, current_price)

    def _should_activate(self, position: Position, current_price: Decimal) -> bool:
        """判断是否应该激活移动止损"""
        entry_price = position.entry_price
        profit = self._calculate_profit(position.side, entry_price, current_price)

        if self.config.activation.type == ActivationType.IMMEDIATE:
            return True
        elif self.config.activation.type == ActivationType.PROFIT_PCT:
            profit_pct = profit / float(entry_price)
            return profit_pct >= self.config.activation.threshold
        elif self.config.activation.type == ActivationType.PROFIT_DOLLAR:
            profit_dollar = profit * float(position.size)
            return profit_dollar >= self.config.activation.threshold
        return False

    def _activate(self, position: Position, current_price: Decimal) -> None:
        """激活移动止损"""
        self.activated = True
        self.activation_price = current_price

        # 初始化追踪价格
        if position.side == PositionSide.LONG:
            self.highest_price = current_price
        else:
            self.lowest_price = current_price

        # 计算初始止损距离
        distance = self._calculate_distance(current_price)
        if position.side == PositionSide.LONG:
            self.trail_stop_price = current_price - Decimal(str(distance))
        else:
            self.trail_stop_price = current_price + Decimal(str(distance))

        logger.info(
            f"Trailing stop activated at {current_price}, "
            f"initial stop: {self.trail_stop_price}, "
            f"side: {position.side}"
        )

    def _update_trailing_stop(self, position: Position, current_price: Decimal) -> None:
        """更新追踪止损价格"""
        if position.side == PositionSide.LONG:
            # Long: 追踪最高价
            if self.highest_price is None or current_price > self.highest_price:
                self.highest_price = current_price

                # 计算新的止损价格
                distance = self._calculate_distance(current_price)
                new_stop = current_price - Decimal(str(distance))

                # 止损只能向上移动
                if self.trail_stop_price is None or new_stop > self.trail_stop_price:
                    old_stop = self.trail_stop_price
                    self.trail_stop_price = new_stop
                    logger.debug(
                        f"Trailing stop updated: {old_stop} -> {new_stop} "
                        f"(price: {current_price}, highest: {self.highest_price})"
                    )
        else:
            # Short: 追踪最低价
            if self.lowest_price is None or current_price < self.lowest_price:
                self.lowest_price = current_price

                # 计算新的止损价格
                distance = self._calculate_distance(current_price)
                new_stop = current_price + Decimal(str(distance))

                # 止损只能向下移动
                if self.trail_stop_price is None or new_stop < self.trail_stop_price:
                    old_stop = self.trail_stop_price
                    self.trail_stop_price = new_stop
                    logger.debug(
                        f"Trailing stop updated: {old_stop} -> {new_stop} "
                        f"(price: {current_price}, lowest: {self.lowest_price})"
                    )

    def _calculate_distance(self, price: Decimal) -> float:
        """计算止损距离"""
        if self.config.distance.type == DistanceType.PERCENTAGE:
            return float(price) * self.config.distance.value
        elif self.config.distance.type == DistanceType.ATR:
            if self.atr is None:
                # 如果没有 ATR，回退到百分比
                logger.warning("ATR not provided, falling back to percentage")
                return float(price) * self.config.distance.value
            return self.atr * self.config.distance.atr_multiplier
        elif self.config.distance.type == DistanceType.FIXED_DOLLAR:
            return self.config.distance.value
        else:
            raise ValueError(f"Unknown distance type: {self.config.distance.type}")

    def _calculate_profit(self, side: PositionSide, entry_price: Decimal, current_price: Decimal) -> float:
        """计算利润"""
        if side == PositionSide.LONG:
            return float(current_price - entry_price)
        else:
            return float(entry_price - current_price)

    def get_state(self) -> Dict[str, Any]:
        """获取状态"""
        return {
            "activated": self.activated,
            "activation_price": float(self.activation_price) if self.activation_price else None,
            "trail_stop_price": float(self.trail_stop_price) if self.trail_stop_price else None,
            "highest_price": float(self.highest_price) if self.highest_price else None,
            "lowest_price": float(self.lowest_price) if self.lowest_price else None,
        }

    def restore_state(self, state: Dict[str, Any]) -> None:
        """恢复状态"""
        self.activated = state.get("activated", False)
        self.activation_price = Decimal(str(state["activation_price"])) if state.get("activation_price") else None
        self.trail_stop_price = Decimal(str(state["trail_stop_price"])) if state.get("trail_stop_price") else None
        self.highest_price = Decimal(str(state["highest_price"])) if state.get("highest_price") else None
        self.lowest_price = Decimal(str(state["lowest_price"])) if state.get("lowest_price") else None
        logger.info(f"Trailing stop state restored: {state}")


class StopLossManager:
    """止损管理器 - 统一管理多种止损策略"""

    def __init__(self):
        self.strategies: Dict[str, StopLossStrategy] = {}  # position_id -> strategy

    def register_position(
        self,
        position_id: str,
        position: Position,
        config: TrailingStopConfig,
        atr: Optional[float] = None
    ):
        """为仓位注册止损策略"""
        if config.enabled:
            strategy = TrailingStopLoss(config, atr)
        else:
            strategy = FixedStopLoss()

        self.strategies[position_id] = strategy
        logger.info(f"Registered stop loss strategy for position {position_id}: {strategy.__class__.__name__}")

    def update(self, position_id: str, position: Position, current_price: Decimal):
        """更新止损"""
        strategy = self.strategies.get(position_id)
        if strategy:
            strategy.update(position, current_price)

    def should_trigger(self, position_id: str, position: Position, current_price: Decimal) -> bool:
        """检查是否应该触发止损"""
        strategy = self.strategies.get(position_id)
        if strategy:
            return strategy.should_trigger(position, current_price)
        return False

    def get_stop_price(self, position_id: str, position: Position) -> Optional[Decimal]:
        """获取止损价格"""
        strategy = self.strategies.get(position_id)
        if strategy:
            return strategy.get_stop_price(position)
        return None

    def remove_position(self, position_id: str):
        """移除仓位的止损策略"""
        if position_id in self.strategies:
            del self.strategies[position_id]
            logger.info(f"Removed stop loss strategy for position {position_id}")

    def get_state(self) -> Dict[str, Any]:
        """获取所有策略的状态"""
        return {
            position_id: strategy.get_state()
            for position_id, strategy in self.strategies.items()
        }

    def restore_state(self, state: Dict[str, Any], config: TrailingStopConfig):
        """恢复所有策略的状态"""
        for position_id, strategy_state in state.items():
            if config.enabled:
                strategy = TrailingStopLoss(config)
                strategy.restore_state(strategy_state)
            else:
                strategy = FixedStopLoss()
            self.strategies[position_id] = strategy
        logger.info(f"Restored {len(self.strategies)} stop loss strategies")
