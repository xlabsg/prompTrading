"""
PnL Calculator

准确的 PnL 计算引擎（包含费用）
"""
import logging
from decimal import Decimal
from typing import Optional
from ..core import Position, PositionSide

logger = logging.getLogger(__name__)


class PnLCalculator:
    """PnL 计算器"""

    def __init__(
        self,
        include_fees: bool = True,
        use_mark_price: bool = True
    ):
        """
        初始化 PnL 计算器

        Args:
            include_fees: 是否包含费用
            use_mark_price: 是否使用标记价格（而非最新价）
        """
        self.include_fees = include_fees
        self.use_mark_price = use_mark_price

    def calculate_unrealized_pnl(
        self,
        position: Position,
        current_price: Optional[Decimal] = None,
        include_fees: Optional[bool] = None
    ) -> Decimal:
        """
        计算未实现盈亏

        Args:
            position: 仓位
            current_price: 当前价格（如果未提供则使用 position.current_price）
            include_fees: 是否包含费用（如果未提供则使用实例配置）

        Returns:
            未实现盈亏
        """
        if include_fees is None:
            include_fees = self.include_fees

        price = current_price if current_price else position.current_price
        entry_price = position.entry_price
        size = position.size

        if position.side == PositionSide.LONG:
            pnl = (price - entry_price) * size
        else:  # SHORT
            pnl = (entry_price - price) * size

        # 减去费用（估算）
        if include_fees:
            # 假设开仓和平仓各收取 0.05% 手续费（具体费率应从配置读取）
            entry_fee = entry_price * size * Decimal("0.0005")
            exit_fee = price * size * Decimal("0.0005")
            total_fee = entry_fee + exit_fee
            pnl = pnl - total_fee

        return pnl

    def calculate_roi(
        self,
        position: Position,
        current_price: Optional[Decimal] = None
    ) -> float:
        """
        计算投资回报率 (ROI)

        Args:
            position: 仓位
            current_price: 当前价格

        Returns:
            ROI (百分比)
        """
        pnl = self.calculate_unrealized_pnl(position, current_price)
        initial_value = position.entry_price * position.size

        if initial_value == 0:
            return 0.0

        roi = (float(pnl) / float(initial_value)) * 100
        return roi

