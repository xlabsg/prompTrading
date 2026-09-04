"""
Position Monitor with Risk Engine Integration

仓位监控器（集成 Risk Engine）
"""
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

# Control plane imports
from control_plane.enums import LogLevel, PositionSide as DBPositionSide, PositionStatus
from control_plane.models import Position as DBPosition, TradingConfig, StrategyExchangeAccount

# Risk Engine imports
from risk_engine import (
    StopLossManager, PnLCalculator, DrawdownTracker,
    Position as SDKPosition, PositionSide as SDKPositionSide,
    TrailingStopConfig, PositionStatus as SDKPositionStatus
)

# App imports
from app.crypto import decrypt_credential
from app.trading_engine.logging_utils import log_trading_event
from app.trading_engine.sdk_config import build_trading_config
from app.routers.ws import manager as ws_manager
from app.settings import settings

logger = logging.getLogger(__name__)


class PositionMonitor:
    """
    仓位监控器（集成 Risk Engine）

    功能：
    - 移动止损管理
    - 准确的 PnL 计算（含费用）
    - 回撤监控
    - 自动止损触发
    """

    def __init__(
        self,
        config: TradingConfig,
        session_id: str,
        db: Session,
        account: StrategyExchangeAccount,
        exchange_adapter=None,
        trailing_stop_config: Optional[TrailingStopConfig] = None
    ):
        """
        初始化增强仓位监控器（兼容原始 API）

        Args:
            config: 交易配置
            session_id: 交易会话 ID
            db: 数据库会话
            account: 交易账户
            exchange_adapter: 可选的交易所适配器（如果提供则复用）
            trailing_stop_config: 可选的移动止损配置
        """
        self.config = config
        self.session_id = session_id
        self.db = db
        self.account = account

        # Build SDK config for trailing stop settings
        self.sdk_config = build_trading_config(config)
        self.trailing_stop_config = trailing_stop_config or self.sdk_config.risk.trailing_stop

        # Create exchange adapter if not provided
        if exchange_adapter:
            self.exchange_adapter = exchange_adapter
            self._owns_adapter = False
        else:
            self.exchange_adapter = self._create_exchange_adapter()
            self._owns_adapter = True

        # SDK 组件
        self.stop_loss_manager = StopLossManager()
        self.pnl_calculator = PnLCalculator(include_fees=True, use_mark_price=True)
        self.drawdown_tracker = DrawdownTracker()

        logger.info(
            f"Enhanced PositionMonitor initialized for session {session_id} "
            f"(trailing_stop: {self.trailing_stop_config.enabled})"
        )

    def _create_exchange_adapter(self):
        """创建交易所适配器"""
        from risk_engine import OKXAdapter

        client = self._get_okx_client()
        return OKXAdapter(client)

    def _get_okx_client(self):
        """获取 OKX 客户端"""
        from okx_sdk import OKXClient

        return OKXClient(
            api_key=(self.account.api_key_encrypted or "").strip(),
            secret_key=decrypt_credential(self.account.api_secret_encrypted).strip(),
            passphrase=decrypt_credential(self.account.api_passphrase_encrypted or "").strip(),
            simulated=settings.okx_simulated_trading,
        )

    def update_positions(self):
        """
        更新仓位（检查移动止损）

        此方法应该定期调用（如每 5 秒）
        """
        try:
            # 从交易所获取仓位
            exchange_positions = self.exchange_adapter.get_positions(
                symbol=self.config.symbol
            )

            for ex_pos in exchange_positions:
                # 转换为 SDK Position
                sdk_position = self._convert_to_sdk_position(ex_pos)

                if not sdk_position:
                    continue

                # 检查和更新移动止损
                self._check_and_update_stop_loss(sdk_position, ex_pos)

                # 更新数据库中的仓位
                self._update_db_position(sdk_position, ex_pos)

            # 更新回撤统计
            self._update_drawdown_stats()

            # 广播 WebSocket 更新
            self._broadcast_position_update()

        except Exception as e:
            logger.error(f"Failed to update positions: {e}", exc_info=True)

    def _check_and_update_stop_loss(self, sdk_position: SDKPosition, ex_pos: dict):
        """检查和更新移动止损"""
        try:
            position_id = f"{sdk_position.symbol}_{sdk_position.side.value}"
            current_price = Decimal(str(ex_pos.get("markPx", ex_pos.get("last"))))

            # 如果仓位还没有注册止损策略，注册它
            if position_id not in self.stop_loss_manager.strategies:
                self.stop_loss_manager.register_position(
                    position_id=position_id,
                    position=sdk_position,
                    config=self.trailing_stop_config,
                    atr=None  # TODO: 从 K 线计算 ATR
                )
                logger.info(f"Registered stop loss strategy for position: {position_id}")

            # 更新移动止损
            self.stop_loss_manager.update(position_id, sdk_position, current_price)

            # 检查是否触发止损
            if self.stop_loss_manager.should_trigger(position_id, sdk_position, current_price):
                logger.warning(f"Stop loss triggered for {position_id} at price {current_price}")

                # 记录日志
                log_trading_event(
                    self.db,
                    strategy_id=self.config.strategy_id,
                    session_id=self.session_id,
                    level=LogLevel.WARNING,
                    message=f"Stop loss triggered for {position_id}",
                    metadata={
                        "position_id": position_id,
                        "current_price": float(current_price),
                        "stop_price": float(self.stop_loss_manager.get_stop_price(position_id, sdk_position)),
                        "unrealized_pnl": float(sdk_position.unrealized_pnl),
                    },
                )

                # 执行平仓
                self._close_position(sdk_position)

        except Exception as e:
            logger.error(f"Failed to check/update stop loss: {e}", exc_info=True)

    def _close_position(self, position: SDKPosition):
        """
        平仓（触发止损或移动止损时执行市价减仓平仓）

        Args:
            position: SDK 仓位对象
        """
        try:
            # 确定平仓方向
            from control_plane.enums import OrderSide
            from app.trading_engine.executor import OrderExecutor

            if position.side == SDKPositionSide.LONG:
                side = OrderSide.SELL
                pos_side = "long"
            else:
                side = OrderSide.BUY
                pos_side = "short"

            logger.warning(
                f"Executing stop-loss market close order for {position.symbol}_{position.side.value} "
                f"side={side.value} size={position.size}"
            )

            executor = OrderExecutor(self.config, self.session_id, self.db, self.account)
            executor.place_market_order(
                side=side,
                size=float(position.size),
                symbol=position.symbol,
                pos_side=pos_side,
                reduce_only=True,
            )

        except Exception as e:
            logger.error(f"Failed to close position: {e}", exc_info=True)

    def _convert_to_sdk_position(self, ex_pos: dict) -> Optional[SDKPosition]:
        """
        将交易所仓位转换为 SDK Position

        Args:
            ex_pos: 交易所返回的仓位数据

        Returns:
            SDK Position 对象或 None
        """
        try:
            # 解析仓位大小
            size = Decimal(str(ex_pos.get("pos", "0")))
            if size == 0:
                return None

            # 解析方向
            pos_side_str = ex_pos.get("posSide", "net")
            if pos_side_str == "long":
                side = SDKPositionSide.LONG
            elif pos_side_str == "short":
                side = SDKPositionSide.SHORT
            else:
                side = SDKPositionSide.NET

            # 创建 SDK Position
            position = SDKPosition(
                symbol=ex_pos.get("instId", ""),
                side=side,
                size=size,
                entry_price=Decimal(str(ex_pos.get("avgPx", "0"))),
                current_price=Decimal(str(ex_pos.get("markPx", ex_pos.get("last", "0")))),
                unrealized_pnl=Decimal(str(ex_pos.get("upl", "0"))),
                realized_pnl=Decimal(str(ex_pos.get("realizedPnl", "0"))),
                leverage=int(ex_pos.get("lever", 1)),
                margin=Decimal(str(ex_pos.get("margin", "0"))),
                liquidation_price=Decimal(str(ex_pos.get("liqPx", "0"))) if ex_pos.get("liqPx") else None,
                status=SDKPositionStatus.OPEN,
            )

            return position

        except Exception as e:
            logger.error(f"Failed to convert position: {e}", exc_info=True)
            return None

    def _update_db_position(self, sdk_position: SDKPosition, ex_pos: dict):
        """
        更新数据库中的仓位记录

        Args:
            sdk_position: SDK 仓位对象
            ex_pos: 交易所返回的仓位数据
        """
        try:
            # 查找或创建仓位记录
            db_side = self._convert_db_position_side(sdk_position.side)

            position = self.db.query(DBPosition).filter(
                DBPosition.session_id == self.session_id,
                DBPosition.symbol == sdk_position.symbol,
                DBPosition.side == db_side,
                DBPosition.status == PositionStatus.OPEN,
            ).first()

            if not position:
                # 创建新仓位
                position = DBPosition(
                    session_id=self.session_id,
                    symbol=sdk_position.symbol,
                    side=db_side,
                    size=float(sdk_position.size),
                    entry_price=float(sdk_position.entry_price),
                    current_price=float(sdk_position.current_price),
                    unrealized_pnl=float(sdk_position.unrealized_pnl),
                    realized_pnl=float(sdk_position.realized_pnl),
                    status=PositionStatus.OPEN,
                )
                self.db.add(position)
            else:
                # 更新现有仓位
                position.size = float(sdk_position.size)
                position.current_price = float(sdk_position.current_price)
                position.unrealized_pnl = float(sdk_position.unrealized_pnl)
                position.realized_pnl = float(sdk_position.realized_pnl)

                # 更新移动止损状态（如果有）
                position_id = f"{sdk_position.symbol}_{sdk_position.side.value}"
                if position_id in self.stop_loss_manager.strategies:
                    stop_price = self.stop_loss_manager.get_stop_price(position_id, sdk_position)
                    if stop_price:
                        position.trailing_stop_price = float(stop_price)
                        position.trailing_stop_activated = True

                # 如果仓位已平（大小为 0）
                if sdk_position.size == 0:
                    position.status = PositionStatus.CLOSED
                    position.closed_at = datetime.now(timezone.utc)

                    # 从止损管理器中移除
                    self.stop_loss_manager.remove_position(position_id)

            self.db.commit()

        except Exception as e:
            logger.error(f"Failed to update DB position: {e}", exc_info=True)
            self.db.rollback()

    def _update_drawdown_stats(self):
        """更新回撤统计"""
        try:
            # 获取账户权益
            balance = self.exchange_adapter.get_balance()
            current_equity = Decimal(str(balance.get("totalEq", 0)))

            # 更新回撤追踪器
            self.drawdown_tracker.update(current_equity)

            # 获取统计信息
            stats = self.drawdown_tracker.get_stats()

            # 记录日志（如果超过阈值）
            if stats["current_drawdown_pct"] > 5.0:
                logger.warning(
                    f"Current drawdown: {stats['current_drawdown_pct']:.2f}% "
                    f"(max: {stats['max_drawdown_pct']:.2f}%)"
                )

        except Exception as e:
            logger.error(f"Failed to update drawdown stats: {e}", exc_info=True)

    def _broadcast_position_update(self):
        """广播 WebSocket 更新"""
        try:
            ws_manager.broadcast_from_thread(
                strategy_id=self.config.strategy_id,
                message={
                    "type": "position_update",
                    "session_id": self.session_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )
        except Exception as e:
            logger.debug(f"Failed to broadcast position update: {e}")

    def _convert_db_position_side(self, sdk_side: SDKPositionSide) -> DBPositionSide:
        """转换 SDK 仓位方向到数据库枚举"""
        if sdk_side == SDKPositionSide.LONG:
            return DBPositionSide.LONG
        elif sdk_side == SDKPositionSide.SHORT:
            return DBPositionSide.SHORT
        else:
            return DBPositionSide.NET

    def get_total_pnl(self) -> float:
        """
        计算总 PnL

        Returns:
            float - 总盈亏
        """
        try:
            positions = self.db.query(DBPosition).filter(
                DBPosition.session_id == self.session_id,
                DBPosition.status == PositionStatus.OPEN,
            ).all()

            total_pnl = sum(pos.unrealized_pnl + pos.realized_pnl for pos in positions)
            return total_pnl

        except Exception as e:
            logger.error(f"Failed to calculate total PnL: {e}", exc_info=True)
            return 0.0
