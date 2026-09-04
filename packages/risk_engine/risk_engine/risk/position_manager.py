"""
Position Manager

负责仓位的 TP/SL 计算和管理
支持三种模式：
1. 动态 TP/SL（基于支撑阻力 + ATR）
2. 手动 TP/SL
3. 混合模式（策略可选择）
"""
import logging
from decimal import Decimal
from typing import Optional, Tuple, Dict, Any
from ..core import (
    Position, PositionSide, DynamicTPSLConfig, SupportResistance,
    Bar
)

logger = logging.getLogger(__name__)


class PositionManager:
    """仓位管理器"""

    def __init__(self, config: DynamicTPSLConfig):
        self.config = config
        self._manual_mode: bool = False
        self._manual_tp: Optional[Decimal] = None
        self._manual_sl: Optional[Decimal] = None

    def calculate_tpsl(
        self,
        entry_price: Decimal,
        side: PositionSide,
        sr: Optional[SupportResistance] = None,
        atr: Optional[float] = None,
    ) -> Tuple[Optional[Decimal], Optional[Decimal]]:
        """
        计算 TP/SL

        Returns:
            (take_profit, stop_loss)
        """
        # 如果是手动模式，返回手动设置的值
        if self._manual_mode:
            return self._manual_tp, self._manual_sl

        # 如果动态 TP/SL 未启用，使用兜底值
        if not self.config.enabled:
            return self._calculate_fallback_tpsl(entry_price, side)

        # 动态计算
        if side == PositionSide.LONG:
            return self._calculate_long_tpsl(entry_price, sr, atr)
        else:
            return self._calculate_short_tpsl(entry_price, sr, atr)

    def _calculate_long_tpsl(
        self,
        entry_price: Decimal,
        sr: Optional[SupportResistance],
        atr: Optional[float]
    ) -> Tuple[Optional[Decimal], Optional[Decimal]]:
        """计算 Long 的 TP/SL"""
        # 计算动态缓冲
        sl_buffer = self._calculate_buffer(entry_price, atr)

        # 计算止损
        stop_loss = None
        if self.config.use_support_resistance and sr:
            nearest_support = sr.get_nearest_support(entry_price)
            if nearest_support:
                # 支撑位下方设置止损
                stop_loss = nearest_support * Decimal(str(1 - sl_buffer))
                logger.debug(f"Using support-based SL: {stop_loss} (support: {nearest_support})")

        if stop_loss is None:
            # 兜底：使用百分比止损
            stop_loss = entry_price * Decimal(str(1 - self.config.fallback_sl_pct))
            logger.debug(f"Using fallback SL: {stop_loss}")

        # 计算止盈
        take_profit = None
        if self.config.use_support_resistance and sr:
            nearest_resistance = sr.get_nearest_resistance(entry_price)
            if nearest_resistance:
                # 阻力位下方设置止盈（留出缓冲）
                tp_buffer = sl_buffer * 0.5  # 止盈缓冲更小
                take_profit = nearest_resistance * Decimal(str(1 - tp_buffer))
                logger.debug(f"Using resistance-based TP: {take_profit} (resistance: {nearest_resistance})")

        if take_profit is None:
            # 兜底：使用百分比止盈
            take_profit = entry_price * Decimal(str(1 + self.config.fallback_tp_pct))
            logger.debug(f"Using fallback TP: {take_profit}")

        # 验证风险回报比
        risk = float(entry_price - stop_loss)
        reward = float(take_profit - entry_price)

        if risk <= 0:
            logger.warning(f"Invalid risk: {risk}, using fallback")
            return self._calculate_fallback_tpsl(entry_price, PositionSide.LONG)

        rr_ratio = reward / risk
        if rr_ratio < self.config.min_risk_reward:
            logger.warning(
                f"R:R ratio {rr_ratio:.2f} < min {self.config.min_risk_reward}, "
                f"adjusting TP"
            )
            # 调整止盈以满足最小风险回报比
            required_reward = risk * self.config.min_risk_reward
            take_profit = entry_price + Decimal(str(required_reward))

        return take_profit, stop_loss

    def _calculate_short_tpsl(
        self,
        entry_price: Decimal,
        sr: Optional[SupportResistance],
        atr: Optional[float]
    ) -> Tuple[Optional[Decimal], Optional[Decimal]]:
        """计算 Short 的 TP/SL"""
        # 计算动态缓冲
        sl_buffer = self._calculate_buffer(entry_price, atr)

        # 计算止损
        stop_loss = None
        if self.config.use_support_resistance and sr:
            nearest_resistance = sr.get_nearest_resistance(entry_price)
            if nearest_resistance:
                # 阻力位上方设置止损
                stop_loss = nearest_resistance * Decimal(str(1 + sl_buffer))
                logger.debug(f"Using resistance-based SL: {stop_loss} (resistance: {nearest_resistance})")

        if stop_loss is None:
            # 兜底：使用百分比止损
            stop_loss = entry_price * Decimal(str(1 + self.config.fallback_sl_pct))
            logger.debug(f"Using fallback SL: {stop_loss}")

        # 计算止盈
        take_profit = None
        if self.config.use_support_resistance and sr:
            nearest_support = sr.get_nearest_support(entry_price)
            if nearest_support:
                # 支撑位上方设置止盈（留出缓冲）
                tp_buffer = sl_buffer * 0.5
                take_profit = nearest_support * Decimal(str(1 + tp_buffer))
                logger.debug(f"Using support-based TP: {take_profit} (support: {nearest_support})")

        if take_profit is None:
            # 兜底：使用百分比止盈
            take_profit = entry_price * Decimal(str(1 - self.config.fallback_tp_pct))
            logger.debug(f"Using fallback TP: {take_profit}")

        # 验证风险回报比
        risk = float(stop_loss - entry_price)
        reward = float(entry_price - take_profit)

        if risk <= 0:
            logger.warning(f"Invalid risk: {risk}, using fallback")
            return self._calculate_fallback_tpsl(entry_price, PositionSide.SHORT)

        rr_ratio = reward / risk
        if rr_ratio < self.config.min_risk_reward:
            logger.warning(
                f"R:R ratio {rr_ratio:.2f} < min {self.config.min_risk_reward}, "
                f"adjusting TP"
            )
            # 调整止盈以满足最小风险回报比
            required_reward = risk * self.config.min_risk_reward
            take_profit = entry_price - Decimal(str(required_reward))

        return take_profit, stop_loss

    def _calculate_buffer(self, price: Decimal, atr: Optional[float]) -> float:
        """计算动态缓冲"""
        buffers = [self.config.sr_buffer_pct, self.config.min_sl_pct]

        # 如果启用 ATR 且提供了 ATR 值
        if self.config.use_atr_buffer and atr:
            atr_buffer = (atr * self.config.atr_sl_multiplier) / float(price)
            buffers.append(atr_buffer)

        return max(buffers)

    def _calculate_fallback_tpsl(
        self,
        entry_price: Decimal,
        side: PositionSide
    ) -> Tuple[Decimal, Decimal]:
        """计算兜底 TP/SL"""
        if side == PositionSide.LONG:
            take_profit = entry_price * Decimal(str(1 + self.config.fallback_tp_pct))
            stop_loss = entry_price * Decimal(str(1 - self.config.fallback_sl_pct))
        else:
            take_profit = entry_price * Decimal(str(1 - self.config.fallback_tp_pct))
            stop_loss = entry_price * Decimal(str(1 + self.config.fallback_sl_pct))

        logger.debug(f"Using fallback TP/SL: TP={take_profit}, SL={stop_loss}")
        return take_profit, stop_loss

    def set_manual_tpsl(self, take_profit: Decimal, stop_loss: Decimal):
        """设置手动 TP/SL（混合模式）"""
        self._manual_mode = True
        self._manual_tp = take_profit
        self._manual_sl = stop_loss
        logger.info(f"Manual TP/SL set: TP={take_profit}, SL={stop_loss}")

    def enable_dynamic_tpsl(self):
        """启用动态 TP/SL（混合模式）"""
        self._manual_mode = False
        self._manual_tp = None
        self._manual_sl = None
        logger.info("Dynamic TP/SL enabled")

    def extract_support_resistance(
        self,
        bars: list[Bar],
        lookback: int = 10
    ) -> SupportResistance:
        """
        从 K 线数据中提取支撑阻力位

        使用最近 N 根 K 线的高低点作为阻力支撑
        """
        if not bars:
            return SupportResistance()

        # 取最近的 K 线
        recent_bars = bars[-lookback:] if len(bars) > lookback else bars

        supports = []
        resistances = []

        for bar in recent_bars:
            supports.append(Decimal(str(bar.low)))
            resistances.append(Decimal(str(bar.high)))

        # 去重并排序
        supports = sorted(set(supports))
        resistances = sorted(set(resistances))

        return SupportResistance(supports=supports, resistances=resistances)

    def calculate_atr(self, bars: list[Bar], period: int = 14) -> Optional[float]:
        """
        计算 ATR (Average True Range)

        Args:
            bars: K 线数据
            period: ATR 周期

        Returns:
            ATR 值
        """
        if len(bars) < period + 1:
            logger.warning(f"Not enough bars to calculate ATR: {len(bars)} < {period + 1}")
            return None

        true_ranges = []
        for i in range(1, len(bars)):
            high = bars[i].high
            low = bars[i].low
            prev_close = bars[i - 1].close

            tr = max(
                high - low,
                abs(high - prev_close),
                abs(low - prev_close)
            )
            true_ranges.append(tr)

        # 取最近 period 个 TR 的平均值
        recent_tr = true_ranges[-period:]
        atr = sum(recent_tr) / len(recent_tr)

        return atr

    def get_state(self) -> Dict[str, Any]:
        """获取状态"""
        return {
            "manual_mode": self._manual_mode,
            "manual_tp": float(self._manual_tp) if self._manual_tp else None,
            "manual_sl": float(self._manual_sl) if self._manual_sl else None,
        }

    def restore_state(self, state: Dict[str, Any]):
        """恢复状态"""
        self._manual_mode = state.get("manual_mode", False)
        self._manual_tp = Decimal(str(state["manual_tp"])) if state.get("manual_tp") else None
        self._manual_sl = Decimal(str(state["manual_sl"])) if state.get("manual_sl") else None
        logger.info(f"Position manager state restored: {state}")
