"""
Order Executor with Risk Engine Integration

订单执行器（集成 Risk Engine）
"""
import logging
from datetime import datetime, timezone
from typing import Optional
from decimal import Decimal

from sqlalchemy.orm import Session

# Control plane imports
from control_plane.enums import LogLevel, OrderSide, OrderStatus, OrderType, TradeStatus
from control_plane.models import Order, StrategyExchangeAccount, TradingConfig, TradingSession, TradingTrade

# Risk Engine imports
from risk_engine import (
    RiskValidator, PositionManager, OrderManager,
    OKXAdapter, generate_client_order_id,
    OrderSpec as SDKOrderSpec, OrderSide as SDKOrderSide,
    OrderType as SDKOrderType, PositionSide,
)

# App imports
from app.crypto import decrypt_credential
from app.trading_engine.logging_utils import log_trading_event
from app.trading_engine.sdk_config import build_trading_config
from app.settings import settings

logger = logging.getLogger(__name__)


class OrderExecutor:
    """
    订单执行器（集成 Risk Engine）

    功能：
    - 下单前风险验证（侵入式控制）
    - 自动计算 TP/SL
    - 订单追踪和管理
    - Snowflake ID 生成
    """

    def __init__(
        self,
        config: TradingConfig,
        session_id: str,
        db: Session,
        account: StrategyExchangeAccount
    ):
        """
        初始化增强订单执行器

        Args:
            config: 交易配置（包含加密的 API 凭据）
            session_id: 交易会话 ID
            db: 数据库会话
            account: 交易所账户
        """
        self.config = config
        self.session_id = session_id
        self.db = db
        self.account = account

        # SDK 配置
        self.sdk_config = build_trading_config(config)

        # OKX 客户端和适配器
        self.okx_client = self._get_client()
        self.exchange_adapter = OKXAdapter(self.okx_client)

        # SDK 组件
        self.risk_validator = RiskValidator(self.sdk_config.risk)
        self.position_manager = PositionManager(self.sdk_config.risk.dynamic_tpsl)
        self.order_manager = OrderManager(
            order_timeout_seconds=self.sdk_config.order_timeout_seconds,
            cancel_stale_orders=self.sdk_config.cancel_stale_orders
        )

        logger.info(
            f"Enhanced OrderExecutor initialized for session {session_id} "
            f"(symbol: {config.symbol}, exchange: {config.exchange})"
        )

    def _get_client(self):
        """获取或创建 OKX 客户端"""
        from okx_sdk import OKXClient

        return OKXClient(
            api_key=(self.account.api_key_encrypted or "").strip(),
            secret_key=decrypt_credential(self.account.api_secret_encrypted).strip(),
            passphrase=decrypt_credential(self.account.api_passphrase_encrypted or "").strip(),
            simulated=settings.okx_simulated_trading,
        )

    def place_market_order(
        self,
        side: OrderSide,
        size: float,
        symbol: Optional[str] = None,
        pos_side: str = "net",
        reduce_only: bool = False,
    ) -> Optional[Order]:
        """
        下市价单（带风险控制）

        Args:
            side: 订单方向（buy 或 sell）
            size: 订单大小
            pos_side: 仓位方向（net, long, short）
            reduce_only: 是否只减仓

        Returns:
            Order 记录，如果风险验证失败则返回 None
        """
        try:
            # Use provided symbol or fall back to config symbol
            target_symbol = symbol or self.config.symbol

            # 获取当前市场价格
            ticker = self.exchange_adapter.get_ticker(target_symbol)
            current_price = Decimal(str(ticker.get("last", 0)))

            # 转换订单方向和仓位方向
            sdk_side = SDKOrderSide.BUY if side == OrderSide.BUY else SDKOrderSide.SELL
            sdk_pos_side = self._convert_position_side(pos_side)

            # 生成客户端订单 ID
            client_order_id = generate_client_order_id(
                prefix=f"strategy_{self.config.strategy_id}",
                direction="L" if side == OrderSide.BUY else "S"
            )

            # 创建 SDK 订单规格
            order_spec = SDKOrderSpec(
                symbol=target_symbol,
                side=sdk_side,
                order_type=SDKOrderType.MARKET,
                size=Decimal(str(size)),
                price=current_price,  # 市价单也需要价格（用于风险计算）
                position_side=sdk_pos_side,
                reduce_only=reduce_only,
                client_order_id=client_order_id,
            )

            # 如果不是减仓订单，计算 TP/SL
            if not reduce_only and self.sdk_config.risk.dynamic_tpsl.enabled:
                tp, sl = self.position_manager.calculate_tpsl(
                    entry_price=current_price,
                    side=sdk_pos_side,
                    sr=None,  # TODO: 从 K 线数据计算支撑阻力
                    atr=None  # TODO: 从 K 线数据计算 ATR
                )
                order_spec.take_profit = tp
                order_spec.stop_loss = sl

                logger.info(
                    f"Calculated TP/SL: TP={tp}, SL={sl} "
                    f"(entry={current_price}, side={sdk_pos_side})"
                )

            # 风险验证
            if not self._validate_risk(order_spec):
                return None

            # 下单
            response = self.exchange_adapter.place_order(order_spec)
            exchange_order_id = response.get("ordId")

            # 创建数据库订单记录
            order = Order(
                session_id=self.session_id,
                exchange_order_id=exchange_order_id,
                client_order_id=client_order_id,
                symbol=target_symbol,
                side=side,
                order_type=OrderType.MARKET,
                size=size,
                status=OrderStatus.OPEN,
                take_profit=float(order_spec.take_profit) if order_spec.take_profit else None,
                stop_loss=float(order_spec.stop_loss) if order_spec.stop_loss else None,
                reduce_only=reduce_only,
            )
            self.db.add(order)
            self.db.commit()
            self.db.refresh(order)

            # 记录日志
            log_trading_event(
                self.db,
                strategy_id=self.config.strategy_id,
                session_id=self.session_id,
                level=LogLevel.INFO,
                message="Market order placed with risk control",
                metadata={
                    "local_order_id": order.id,
                    "exchange_order_id": exchange_order_id,
                    "client_order_id": client_order_id,
                    "side": side.value,
                    "size": size,
                    "take_profit": float(order_spec.take_profit) if order_spec.take_profit else None,
                    "stop_loss": float(order_spec.stop_loss) if order_spec.stop_loss else None,
                },
            )

            # 创建 TradingTrade 记录
            if not reduce_only:
                trade = TradingTrade(
                    session_id=self.session_id,
                    side=side.value,
                    entry_price=float(current_price),
                    quantity=size,
                    status=TradeStatus.OPEN,
                )
                self.db.add(trade)
                self.db.commit()

            logger.info(
                f"Order placed successfully: {order.id} "
                f"(exchange: {exchange_order_id}, client: {client_order_id})"
            )

            return order

        except Exception as e:
            logger.error(f"Failed to place market order: {e}", exc_info=True)
            log_trading_event(
                self.db,
                strategy_id=self.config.strategy_id,
                session_id=self.session_id,
                level=LogLevel.ERROR,
                message=f"Failed to place order: {str(e)}",
                metadata={
                    "side": side.value,
                    "size": size,
                    "error": str(e),
                },
            )
            return None

    def _validate_risk(self, order_spec: SDKOrderSpec) -> bool:
        """
        验证订单风险

        Args:
            order_spec: SDK 订单规格

        Returns:
            bool - 是否通过验证
        """
        try:
            # 获取当前仓位和余额
            current_positions = self.exchange_adapter.get_positions(self.config.symbol)
            balance = self.exchange_adapter.get_balance()

            # 转换为 SDK Position 对象
            # TODO: 实现完整的转换逻辑

            # 风险验证
            risk_result = self.risk_validator.validate_order(
                order_spec=order_spec,
                current_positions=[],  # TODO: 转换后的仓位列表
                balance=balance,
            )

            if not risk_result.approved:
                logger.error(f"Order rejected by risk validator: {risk_result.reason}")
                log_trading_event(
                    self.db,
                    strategy_id=self.config.strategy_id,
                    session_id=self.session_id,
                    level=LogLevel.ERROR,
                    message=f"Order rejected: {risk_result.reason}",
                    metadata={
                        "violations": risk_result.violations,
                        "warnings": risk_result.warnings,
                    },
                )
                return False

            if risk_result.warnings:
                logger.warning(f"Order approved with warnings: {'; '.join(risk_result.warnings)}")

            return True

        except Exception as e:
            logger.error(f"Risk validation error: {e}", exc_info=True)
            # 验证失败时，默认拒绝订单（安全优先）
            return False

    def _convert_position_side(self, pos_side: str) -> PositionSide:
        """转换仓位方向"""
        if pos_side == "long":
            return PositionSide.LONG
        elif pos_side == "short":
            return PositionSide.SHORT
        else:
            return PositionSide.NET

    def place_limit_order(
        self,
        side: OrderSide,
        size: float,
        price: float,
        symbol: Optional[str] = None,
        pos_side: str = "net",
        reduce_only: bool = False,
    ) -> Optional[Order]:
        """
        下限价单（带风险控制）

        Args:
            side: 订单方向（buy 或 sell）
            size: 订单大小
            price: 限价
            symbol: 交易对
            pos_side: 仓位方向（net, long, short）
            reduce_only: 是否只减仓

        Returns:
            Order 记录，如果风险验证失败则返回 None
        """
        try:
            # Use provided symbol or fall back to config symbol
            target_symbol = symbol or self.config.symbol

            # 转换订单方向和仓位方向
            sdk_side = SDKOrderSide.BUY if side == OrderSide.BUY else SDKOrderSide.SELL
            sdk_pos_side = self._convert_position_side(pos_side)

            # 生成客户端订单 ID
            client_order_id = generate_client_order_id(
                prefix=f"strategy_{self.config.strategy_id}",
                direction="L" if side == OrderSide.BUY else "S"
            )

            # 创建 SDK 订单规格
            order_spec = SDKOrderSpec(
                symbol=target_symbol,
                side=sdk_side,
                order_type=SDKOrderType.LIMIT,
                size=Decimal(str(size)),
                price=Decimal(str(price)),
                position_side=sdk_pos_side,
                reduce_only=reduce_only,
                client_order_id=client_order_id,
            )

            # 风险验证
            if not self._validate_risk(order_spec):
                return None

            # 下单
            response = self.exchange_adapter.place_order(order_spec)
            exchange_order_id = response.get("ordId")

            # 创建数据库订单记录
            order = Order(
                session_id=self.session_id,
                exchange_order_id=exchange_order_id,
                client_order_id=client_order_id,
                symbol=target_symbol,
                side=side,
                order_type=OrderType.LIMIT,
                price=price,
                size=size,
                status=OrderStatus.OPEN,
                reduce_only=reduce_only,
            )
            self.db.add(order)
            self.db.commit()
            self.db.refresh(order)

            # 记录日志
            log_trading_event(
                self.db,
                strategy_id=self.config.strategy_id,
                session_id=self.session_id,
                level=LogLevel.INFO,
                message="Limit order placed with risk control",
                metadata={
                    "local_order_id": order.id,
                    "exchange_order_id": exchange_order_id,
                    "client_order_id": client_order_id,
                    "side": side.value,
                    "size": size,
                    "price": price,
                    "symbol": target_symbol,
                },
            )

            logger.info(
                f"Limit order placed successfully: {order.id} "
                f"(exchange: {exchange_order_id}, client: {client_order_id})"
            )

            return order

        except Exception as e:
            logger.error(f"Failed to place limit order: {e}", exc_info=True)
            log_trading_event(
                self.db,
                strategy_id=self.config.strategy_id,
                session_id=self.session_id,
                level=LogLevel.ERROR,
                message=f"Failed to place limit order: {str(e)}",
                metadata={
                    "side": side.value,
                    "size": size,
                    "price": price,
                    "error": str(e),
                },
            )
            return None

    def cancel_order(self, order: Order) -> bool:
        """
        取消订单

        Args:
            order: 数据库订单对象

        Returns:
            bool - 是否成功
        """
        try:
            if not order or not order.exchange_order_id:
                logger.error(f"Order not found or missing exchange_order_id: {order.id if order else 'None'}")
                return False

            success = self.exchange_adapter.cancel_order(
                symbol=order.symbol,
                order_id=order.exchange_order_id
            )

            if success:
                order.status = OrderStatus.CANCELLED
                self.db.commit()
                logger.info(f"Order cancelled: {order.id}")

            return success

        except Exception as e:
            logger.error(f"Failed to cancel order: {e}", exc_info=True)
            return False

    def update_order_status(self, order: Order) -> bool:
        """
        从交易所更新订单状态

        Args:
            order: 数据库订单对象

        Returns:
            bool - 是否成功更新
        """
        try:
            if not order or not order.exchange_order_id:
                return False

            # 从交易所获取订单信息
            exchange_order = self.exchange_adapter.get_order(
                symbol=order.symbol,
                order_id=order.exchange_order_id
            )

            if not exchange_order:
                return False

            # 更新订单状态
            state = exchange_order.get("state")
            if state == "filled":
                order.status = OrderStatus.FILLED
                order.filled_size = float(exchange_order.get("accFillSz", 0))
                order.avg_fill_price = float(exchange_order.get("avgPx", 0))
            elif state == "partially_filled":
                order.status = OrderStatus.PARTIALLY_FILLED
                order.filled_size = float(exchange_order.get("accFillSz", 0))
                order.avg_fill_price = float(exchange_order.get("avgPx", 0))
            elif state == "canceled":
                order.status = OrderStatus.CANCELLED

            order.updated_at = datetime.now(timezone.utc)
            self.db.commit()

            return True

        except Exception as e:
            logger.error(f"Failed to update order status: {e}", exc_info=True)
            return False

    def cleanup_stale_orders(self):
        """清理陈旧订单"""
        try:
            stale_orders = self.order_manager.get_stale_orders()
            for order in stale_orders:
                logger.warning(f"Cancelling stale order: {order.order_id}")
                self.cancel_order(order.order_id)

        except Exception as e:
            logger.error(f"Failed to cleanup stale orders: {e}", exc_info=True)
