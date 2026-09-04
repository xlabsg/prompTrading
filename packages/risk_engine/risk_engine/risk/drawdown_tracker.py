"""
Drawdown Tracker

监控最大回撤和每日亏损
"""
import logging
from datetime import datetime, date
from decimal import Decimal
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class DrawdownTracker:
    """回撤追踪器"""

    def __init__(self):
        # 历史最高权益
        self.peak_equity: Optional[Decimal] = None
        self.peak_equity_date: Optional[datetime] = None

        # 当前回撤
        self.current_drawdown: Decimal = Decimal("0")
        self.current_drawdown_pct: float = 0.0

        # 最大回撤
        self.max_drawdown: Decimal = Decimal("0")
        self.max_drawdown_pct: float = 0.0
        self.max_drawdown_date: Optional[datetime] = None

        # 每日统计
        self.daily_start_equity: Optional[Decimal] = None
        self.daily_pnl: Decimal = Decimal("0")
        self.daily_pnl_pct: float = 0.0
        self.current_date: Optional[date] = None

    def update(self, current_equity: Decimal, timestamp: Optional[datetime] = None):
        """
        更新回撤统计

        Args:
            current_equity: 当前账户权益
            timestamp: 时间戳（如果未提供则使用当前时间）
        """
        if timestamp is None:
            timestamp = datetime.utcnow()

        # 更新历史最高权益
        if self.peak_equity is None or current_equity > self.peak_equity:
            self.peak_equity = current_equity
            self.peak_equity_date = timestamp
            logger.info(f"New peak equity: {current_equity} at {timestamp}")

        # 计算当前回撤
        if self.peak_equity:
            self.current_drawdown = self.peak_equity - current_equity
            self.current_drawdown_pct = (
                float(self.current_drawdown) / float(self.peak_equity) * 100
            )

            # 更新最大回撤
            if self.current_drawdown > self.max_drawdown:
                self.max_drawdown = self.current_drawdown
                self.max_drawdown_pct = self.current_drawdown_pct
                self.max_drawdown_date = timestamp
                logger.warning(
                    f"New max drawdown: {self.max_drawdown} "
                    f"({self.max_drawdown_pct:.2f}%) at {timestamp}"
                )

        # 更新每日统计
        self._update_daily_stats(current_equity, timestamp)

    def _update_daily_stats(self, current_equity: Decimal, timestamp: datetime):
        """更新每日统计"""
        today = timestamp.date()

        # 如果是新的一天，重置每日统计
        if self.current_date != today:
            self.daily_start_equity = current_equity
            self.daily_pnl = Decimal("0")
            self.daily_pnl_pct = 0.0
            self.current_date = today
            logger.info(f"New trading day: {today}, starting equity: {current_equity}")

        # 计算每日盈亏
        if self.daily_start_equity:
            self.daily_pnl = current_equity - self.daily_start_equity
            self.daily_pnl_pct = (
                float(self.daily_pnl) / float(self.daily_start_equity) * 100
            )

    def is_max_drawdown_exceeded(self, max_drawdown_pct: float) -> bool:
        """检查是否超过最大回撤限制"""
        return self.current_drawdown_pct > max_drawdown_pct

    def is_daily_loss_exceeded(
        self,
        max_daily_loss_pct: Optional[float] = None,
        max_daily_loss_dollar: Optional[Decimal] = None
    ) -> bool:
        """检查是否超过每日亏损限制"""
        if max_daily_loss_pct is not None:
            if self.daily_pnl_pct < -max_daily_loss_pct:
                return True

        if max_daily_loss_dollar is not None:
            if self.daily_pnl < -max_daily_loss_dollar:
                return True

        return False

    def reset_daily_stats(self):
        """手动重置每日统计"""
        self.daily_start_equity = None
        self.daily_pnl = Decimal("0")
        self.daily_pnl_pct = 0.0
        self.current_date = None
        logger.info("Daily stats reset")

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "peak_equity": float(self.peak_equity) if self.peak_equity else None,
            "peak_equity_date": self.peak_equity_date.isoformat() if self.peak_equity_date else None,
            "current_drawdown": float(self.current_drawdown),
            "current_drawdown_pct": self.current_drawdown_pct,
            "max_drawdown": float(self.max_drawdown),
            "max_drawdown_pct": self.max_drawdown_pct,
            "max_drawdown_date": self.max_drawdown_date.isoformat() if self.max_drawdown_date else None,
            "daily_pnl": float(self.daily_pnl),
            "daily_pnl_pct": self.daily_pnl_pct,
            "daily_start_equity": float(self.daily_start_equity) if self.daily_start_equity else None,
        }

    def get_state(self) -> Dict[str, Any]:
        """获取状态（用于持久化）"""
        return {
            "peak_equity": float(self.peak_equity) if self.peak_equity else None,
            "peak_equity_date": self.peak_equity_date.isoformat() if self.peak_equity_date else None,
            "max_drawdown": float(self.max_drawdown),
            "max_drawdown_pct": self.max_drawdown_pct,
            "max_drawdown_date": self.max_drawdown_date.isoformat() if self.max_drawdown_date else None,
            "daily_start_equity": float(self.daily_start_equity) if self.daily_start_equity else None,
            "daily_pnl": float(self.daily_pnl),
            "current_date": self.current_date.isoformat() if self.current_date else None,
        }

    def restore_state(self, state: Dict[str, Any]):
        """恢复状态"""
        self.peak_equity = Decimal(str(state["peak_equity"])) if state.get("peak_equity") else None
        self.peak_equity_date = (
            datetime.fromisoformat(state["peak_equity_date"])
            if state.get("peak_equity_date")
            else None
        )
        self.max_drawdown = Decimal(str(state.get("max_drawdown", "0")))
        self.max_drawdown_pct = state.get("max_drawdown_pct", 0.0)
        self.max_drawdown_date = (
            datetime.fromisoformat(state["max_drawdown_date"])
            if state.get("max_drawdown_date")
            else None
        )
        self.daily_start_equity = (
            Decimal(str(state["daily_start_equity"]))
            if state.get("daily_start_equity")
            else None
        )
        self.daily_pnl = Decimal(str(state.get("daily_pnl", "0")))
        self.current_date = (
            datetime.fromisoformat(state["current_date"]).date()
            if state.get("current_date")
            else None
        )
        logger.info(f"Drawdown tracker state restored: peak={self.peak_equity}, max_dd={self.max_drawdown_pct:.2f}%")
