"""
Trading Metrics

交易统计指标计算
"""
import logging
from decimal import Decimal
from typing import List, Dict, Any
from ..core import Trade, Position

logger = logging.getLogger(__name__)


class TradingMetrics:
    """交易指标计算器"""

    def calculate_session_metrics(
        self,
        trades: List[Trade],
        positions: List[Position],
        initial_balance: Decimal,
        current_balance: Decimal
    ) -> Dict[str, Any]:
        """
        计算会话交易指标

        Args:
            trades: 成交记录列表
            positions: 仓位列表
            initial_balance: 初始余额
            current_balance: 当前余额

        Returns:
            交易指标字典
        """
        if not trades:
            return self._empty_metrics()

        # 分离盈利和亏损交易
        winning_trades = []
        losing_trades = []

        for trade in trades:
            # 假设 Trade 有 pnl 字段或计算 pnl
            pnl = self._calculate_trade_pnl(trade)
            if pnl > 0:
                winning_trades.append(trade)
            else:
                losing_trades.append(trade)

        total_trades = len(trades)
        winning_count = len(winning_trades)
        losing_count = len(losing_trades)

        # 计算基本指标
        win_rate = (winning_count / total_trades * 100) if total_trades > 0 else 0.0

        total_profit = sum(self._calculate_trade_pnl(t) for t in winning_trades)
        total_loss = abs(sum(self._calculate_trade_pnl(t) for t in losing_trades))

        profit_factor = (float(total_profit) / float(total_loss)) if total_loss > 0 else 0.0

        avg_win = (float(total_profit) / winning_count) if winning_count > 0 else 0.0
        avg_loss = (float(total_loss) / losing_count) if losing_count > 0 else 0.0

        largest_win = max((self._calculate_trade_pnl(t) for t in winning_trades), default=Decimal("0"))
        largest_loss = min((self._calculate_trade_pnl(t) for t in losing_trades), default=Decimal("0"))

        # 总盈亏
        total_pnl = current_balance - initial_balance
        total_return = (float(total_pnl) / float(initial_balance) * 100) if initial_balance > 0 else 0.0

        # 平均持仓时间
        avg_holding_time = self._calculate_avg_holding_time(trades)

        return {
            "total_trades": total_trades,
            "winning_trades": winning_count,
            "losing_trades": losing_count,
            "win_rate": round(win_rate, 2),
            "profit_factor": round(profit_factor, 2),
            "total_profit": float(total_profit),
            "total_loss": float(total_loss),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "largest_win": float(largest_win),
            "largest_loss": float(largest_loss),
            "total_pnl": float(total_pnl),
            "total_return_pct": round(total_return, 2),
            "avg_holding_time_seconds": avg_holding_time,
        }

    def _calculate_trade_pnl(self, trade: Trade) -> Decimal:
        """计算单笔交易的 PnL（简化）"""
        # 这里需要根据实际的 Trade 结构计算
        # 假设 Trade 包含足够的信息
        return Decimal("0")  # 占位符

    def _calculate_avg_holding_time(self, trades: List[Trade]) -> float:
        """计算平均持仓时间（秒）"""
        # 简化实现
        return 0.0

    def _empty_metrics(self) -> Dict[str, Any]:
        """空指标"""
        return {
            "total_trades": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "total_profit": 0.0,
            "total_loss": 0.0,
            "avg_win": 0.0,
            "avg_loss": 0.0,
            "largest_win": 0.0,
            "largest_loss": 0.0,
            "total_pnl": 0.0,
            "total_return_pct": 0.0,
            "avg_holding_time_seconds": 0.0,
        }

