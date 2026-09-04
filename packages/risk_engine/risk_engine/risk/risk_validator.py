"""
Risk Validator

侵入式风险控制 - 在下单前进行风险验证
"""
import logging
from decimal import Decimal
from typing import Optional, List
from ..core import (
    OrderSpec, Position, Balance, RiskConfig, RiskCheckResult,
    OrderSide, PositionSide, RiskViolationType
)

logger = logging.getLogger(__name__)


class RiskValidator:
    """风险验证器 - 侵入式风控"""

    def __init__(self, config: RiskConfig):
        self.config = config
        self.daily_pnl_start: Optional[Decimal] = None  # 每日起始权益
        self.daily_pnl_current: Decimal = Decimal("0")  # 当日盈亏
        self.peak_equity: Optional[Decimal] = None  # 历史最高权益

    def validate_order(
        self,
        order_spec: OrderSpec,
        current_positions: List[Position],
        balance: Balance,
    ) -> RiskCheckResult:
        """
        验证订单是否符合风险规则

        侵入式控制：如果违反规则，直接拒绝订单
        """
        violations = []
        warnings = []
        metadata = {}

        # 1. 检查余额是否足够
        violation = self._check_balance(order_spec, balance)
        if violation:
            violations.append(violation)

        # 2. 检查是否超过最大仓位
        violation = self._check_max_position(order_spec, current_positions, balance)
        if violation:
            violations.append(violation)

        # 3. 检查杠杆是否超限
        violation = self._check_max_leverage(order_spec, balance)
        if violation:
            violations.append(violation)

        # 4. 检查止损是否有效
        if self.config.require_stop_loss:
            violation = self._check_stop_loss(order_spec)
            if violation:
                violations.append(violation)

        # 5. 检查风险回报比
        if order_spec.take_profit and order_spec.stop_loss:
            warning = self._check_risk_reward(order_spec)
            if warning:
                warnings.append(warning)

        # 6. 检查每日亏损限制
        violation = self._check_daily_loss(balance)
        if violation:
            violations.append(violation)

        # 7. 检查最大回撤
        violation = self._check_max_drawdown(balance)
        if violation:
            violations.append(violation)

        # 8. 检查订单大小
        violation = self._check_order_size(order_spec)
        if violation:
            violations.append(violation)

        # 9. 检查是否允许对冲
        if not self.config.allow_hedging:
            violation = self._check_hedging(order_spec, current_positions)
            if violation:
                violations.append(violation)

        approved = len(violations) == 0

        if not approved:
            logger.warning(f"Order rejected: {'; '.join(violations)}")
        elif warnings:
            logger.info(f"Order approved with warnings: {'; '.join(warnings)}")

        return RiskCheckResult(
            approved=approved,
            violations=violations,
            warnings=warnings,
            metadata=metadata
        )

    def _check_balance(self, order_spec: OrderSpec, balance: Balance) -> Optional[str]:
        """检查余额是否足够"""
        # 估算所需保证金
        notional = float(order_spec.size) * float(order_spec.price or 0)
        required_margin = notional  # 简化计算，实际需要考虑杠杆

        if balance.available_balance < Decimal(str(required_margin)):
            return f"{RiskViolationType.INSUFFICIENT_BALANCE}: Required {required_margin}, Available {balance.available_balance}"
        return None

    def _check_max_position(
        self,
        order_spec: OrderSpec,
        current_positions: List[Position],
        balance: Balance
    ) -> Optional[str]:
        """检查是否超过最大仓位"""
        # 计算新订单的名义价值
        order_notional = float(order_spec.size) * float(order_spec.price or 0)

        # 计算当前仓位的总名义价值
        current_notional = sum(
            float(p.size) * float(p.current_price)
            for p in current_positions
            if p.status.value == "open"
        )

        # 如果是减仓订单，不检查
        if order_spec.reduce_only:
            return None

        # 如果订单会减少仓位，也不检查
        for pos in current_positions:
            if pos.symbol == order_spec.symbol and pos.status.value == "open":
                is_closing = (
                    (pos.side == PositionSide.LONG and order_spec.side == OrderSide.SELL) or
                    (pos.side == PositionSide.SHORT and order_spec.side == OrderSide.BUY)
                )
                if is_closing:
                    return None

        # 计算新的总仓位
        new_total_notional = current_notional + order_notional

        # 检查是否超过最大仓位百分比
        max_allowed = float(balance.total_equity) * (self.config.max_position_pct / 100.0)

        if new_total_notional > max_allowed:
            return f"{RiskViolationType.MAX_POSITION_EXCEEDED}: New total {new_total_notional:.2f} > Max allowed {max_allowed:.2f}"
        return None

    def _check_max_leverage(self, order_spec: OrderSpec, balance: Balance) -> Optional[str]:
        """检查杠杆是否超限"""
        # 从元数据中获取杠杆（如果有）
        leverage = order_spec.metadata.get("leverage", 1)

        if leverage > self.config.max_leverage:
            return f"{RiskViolationType.MAX_LEVERAGE_EXCEEDED}: Leverage {leverage} > Max {self.config.max_leverage}"
        return None

    def _check_stop_loss(self, order_spec: OrderSpec) -> Optional[str]:
        """检查止损是否有效"""
        if not order_spec.stop_loss:
            return f"{RiskViolationType.INVALID_STOP_LOSS}: Stop loss is required but not provided"

        # 检查止损价格是否合理
        if order_spec.price:
            if order_spec.side == OrderSide.BUY:
                # Long: 止损应该低于入场价
                if order_spec.stop_loss >= order_spec.price:
                    return f"{RiskViolationType.INVALID_STOP_LOSS}: Stop loss {order_spec.stop_loss} should be below entry {order_spec.price}"
            else:
                # Short: 止损应该高于入场价
                if order_spec.stop_loss <= order_spec.price:
                    return f"{RiskViolationType.INVALID_STOP_LOSS}: Stop loss {order_spec.stop_loss} should be above entry {order_spec.price}"

        return None

    def _check_risk_reward(self, order_spec: OrderSpec) -> Optional[str]:
        """检查风险回报比"""
        if not order_spec.price or not order_spec.take_profit or not order_spec.stop_loss:
            return None

        entry = float(order_spec.price)
        tp = float(order_spec.take_profit)
        sl = float(order_spec.stop_loss)

        risk = abs(entry - sl)
        reward = abs(tp - entry)

        if risk == 0:
            return "Risk is zero, invalid stop loss"

        rr_ratio = reward / risk

        # 动态 TP/SL 配置中的最小风险回报比
        min_rr = self.config.dynamic_tpsl.min_risk_reward

        if rr_ratio < min_rr:
            return f"{RiskViolationType.MIN_RISK_REWARD}: R:R ratio {rr_ratio:.2f} < Min required {min_rr}"

        return None

    def _check_daily_loss(self, balance: Balance) -> Optional[str]:
        """检查每日亏损限制"""
        # 初始化每日起始权益
        if self.daily_pnl_start is None:
            self.daily_pnl_start = balance.total_equity

        # 计算当日盈亏
        self.daily_pnl_current = balance.total_equity - self.daily_pnl_start

        # 检查百分比限制
        if self.config.max_daily_loss_pct:
            loss_pct = (float(self.daily_pnl_current) / float(self.daily_pnl_start)) * 100
            if loss_pct < -self.config.max_daily_loss_pct:
                return f"{RiskViolationType.DAILY_LOSS_LIMIT}: Daily loss {loss_pct:.2f}% exceeds limit {self.config.max_daily_loss_pct}%"

        # 检查金额限制
        if self.config.max_daily_loss_dollar:
            if float(self.daily_pnl_current) < -self.config.max_daily_loss_dollar:
                return f"{RiskViolationType.DAILY_LOSS_LIMIT}: Daily loss ${abs(float(self.daily_pnl_current)):.2f} exceeds limit ${self.config.max_daily_loss_dollar}"

        return None

    def _check_max_drawdown(self, balance: Balance) -> Optional[str]:
        """检查最大回撤"""
        if not self.config.max_drawdown_pct:
            return None

        # 更新历史最高权益
        if self.peak_equity is None or balance.total_equity > self.peak_equity:
            self.peak_equity = balance.total_equity

        # 计算当前回撤
        drawdown = (float(self.peak_equity - balance.total_equity) / float(self.peak_equity)) * 100

        if drawdown > self.config.max_drawdown_pct:
            return f"{RiskViolationType.MAX_DRAWDOWN_EXCEEDED}: Drawdown {drawdown:.2f}% > Max {self.config.max_drawdown_pct}%"

        return None

    def _check_order_size(self, order_spec: OrderSpec) -> Optional[str]:
        """检查订单大小"""
        size = float(order_spec.size)

        if size < self.config.min_order_size:
            return f"Order size {size} < Min order size {self.config.min_order_size}"

        if self.config.max_order_size and size > self.config.max_order_size:
            return f"Order size {size} > Max order size {self.config.max_order_size}"

        return None

    def _check_hedging(
        self,
        order_spec: OrderSpec,
        current_positions: List[Position]
    ) -> Optional[str]:
        """检查是否存在对冲"""
        for pos in current_positions:
            if pos.symbol != order_spec.symbol or pos.status.value != "open":
                continue

            # 检查是否会形成对冲
            is_opposite_side = (
                (pos.side == PositionSide.LONG and order_spec.position_side == PositionSide.SHORT) or
                (pos.side == PositionSide.SHORT and order_spec.position_side == PositionSide.LONG)
            )

            if is_opposite_side and not order_spec.reduce_only:
                return f"Hedging not allowed: Existing {pos.side} position, trying to open {order_spec.position_side}"

        return None

    def reset_daily_stats(self):
        """重置每日统计（应在每日开始时调用）"""
        self.daily_pnl_start = None
        self.daily_pnl_current = Decimal("0")
        logger.info("Daily risk stats reset")

