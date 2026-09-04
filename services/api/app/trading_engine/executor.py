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
from control_plane.models import Order, StrategyExchangeAccount, TradingConfig, TradingTrade

# Risk Engine imports
from risk_engine import (
    RiskValidator, PositionManager, OrderManager,
    BinanceAdapter, BinanceClient,
    generate_client_order_id,
    OrderSpec as SDKOrderSpec, OrderSide as SDKOrderSide,
    OrderType as SDKOrderType, PositionSide,
    Balance, Position as SDKPosition, PositionStatus as SDKPositionStatus,
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
        account: Optional[StrategyExchangeAccount] = None
    ):
        """
        初始化增强订单执行器

        Args:
            config: 交易配置（包含加密的 API 凭据）
            session_id: 交易会话 ID
            db: 数据库会话
            account: 交易所账户（可选，纸盘交易时可为 None）
        """
        self.config = config
        self.session_id = session_id
        self.db = db
        self.account = account

        # SDK 配置
        self.sdk_config = build_trading_config(config)

        # 交易所适配器 (支持 OKX, Binance, Paper)
        self.exchange_adapter = self._create_adapter()

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

    def _create_adapter(self):
        """根据交易账户配置创建对应的交易所适配器"""
        exchange_name = (getattr(self.account, "exchange", "") or self.config.exchange or "").lower()

        if exchange_name == "paper" or self.account is None or not getattr(self.account, "api_secret_encrypted", None):
            from app.trading_engine.paper_client import PaperExchangeClient
            from risk_engine.adapters.okx import OKXAdapter
            return OKXAdapter(PaperExchangeClient())

        api_key = (self.account.api_key_encrypted or "").strip()
        secret_key = decrypt_credential(self.account.api_secret_encrypted).strip()

        if exchange_name == "binance":
            testnet = getattr(settings, "binance_testnet", False)
            binance_client = BinanceClient(
                api_key=api_key,
                secret_key=secret_key,
                testnet=testnet,
            )
            return BinanceAdapter(binance_client)

        from okx_sdk import OKXClient
        passphrase = decrypt_credential(self.account.api_passphrase_encrypted or "").strip()
        okx_client = OKXClient(
            api_key=api_key,
            secret_key=secret_key,
            passphrase=passphrase,
            simulated=settings.okx_simulated_trading,
        )
        return OKXAdapter(okx_client)

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
            elif not reduce_only and self.sdk_config.risk.require_stop_loss and getattr(self.config, "stop_loss_pct", None):
                sl_pct = Decimal(str(self.config.stop_loss_pct)) / Decimal("100")
                if sdk_pos_side == PositionSide.LONG or (sdk_pos_side == PositionSide.NET and side == OrderSide.BUY):
                    order_spec.stop_loss = current_price * (Decimal("1") - sl_pct)
                else:
                    order_spec.stop_loss = current_price * (Decimal("1") + sl_pct)
                logger.info(
                    f"Applied fixed stop-loss: SL={order_spec.stop_loss} "
                    f"(entry={current_price}, pct={self.config.stop_loss_pct}%)"
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
                    symbol=target_symbol,
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
            try:
                failed_order = Order(
                    session_id=self.session_id,
                    client_order_id=client_order_id,
                    symbol=target_symbol,
                    side=side,
                    order_type=OrderType.MARKET,
                    size=size,
                    status=OrderStatus.FAILED,
                )
                self.db.add(failed_order)
                self.db.commit()
            except Exception:
                self.db.rollback()

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

    def _convert_to_sdk_position(self, ex_pos: dict) -> Optional[SDKPosition]:
        try:
            size = Decimal(str(ex_pos.get("pos", "0")))
            if size == 0:
                return None

            pos_side_str = str(ex_pos.get("posSide", "net")).lower()
            if pos_side_str == "long":
                side = PositionSide.LONG
            elif pos_side_str == "short":
                side = PositionSide.SHORT
            else:
                side = PositionSide.NET

            return SDKPosition(
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
        except Exception as e:
            logger.error(f"Failed to convert position in executor: {e}", exc_info=True)
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
            current_positions_raw = self.exchange_adapter.get_positions(self.config.symbol)
            balance_raw = self.exchange_adapter.get_balance()

            if isinstance(balance_raw, Balance):
                balance = balance_raw
            elif isinstance(balance_raw, dict):
                total_eq = Decimal(str(balance_raw.get("totalEq", balance_raw.get("total_equity", "10000")) or "10000"))
                avail_bal = Decimal(str(balance_raw.get("availBal", balance_raw.get("available_balance", total_eq)) or total_eq))
                upl = Decimal(str(balance_raw.get("upl", balance_raw.get("unrealized_pnl", "0")) or "0"))
                balance = Balance(
                    total_equity=total_eq,
                    available_balance=avail_bal,
                    margin_used=max(Decimal("0"), total_eq - avail_bal),
                    unrealized_pnl=upl,
                )
            else:
                balance = Balance(
                    total_equity=Decimal("10000"),
                    available_balance=Decimal("10000"),
                    margin_used=Decimal("0"),
                    unrealized_pnl=Decimal("0"),
                )

            current_positions = []
            if isinstance(current_positions_raw, list):
                for p in current_positions_raw:
                    if isinstance(p, SDKPosition):
                        current_positions.append(p)
                    elif isinstance(p, dict):
                        pos_obj = self._convert_to_sdk_position(p)
                        if pos_obj:
                            current_positions.append(pos_obj)

            # 风险验证
            risk_result = self.risk_validator.validate_order(
                order_spec=order_spec,
                current_positions=current_positions,
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

            # 如果不是减仓订单，计算 TP/SL
            limit_price = Decimal(str(price))
            if not reduce_only and self.sdk_config.risk.dynamic_tpsl.enabled:
                tp, sl = self.position_manager.calculate_tpsl(
                    entry_price=limit_price,
                    side=sdk_pos_side,
                    sr=None,
                    atr=None,
                )
                order_spec.take_profit = tp
                order_spec.stop_loss = sl
                logger.info(
                    f"Calculated TP/SL for limit order: TP={tp}, SL={sl} "
                    f"(price={limit_price}, side={sdk_pos_side})"
                )
            elif not reduce_only and self.sdk_config.risk.require_stop_loss and getattr(self.config, "stop_loss_pct", None):
                sl_pct = Decimal(str(self.config.stop_loss_pct)) / Decimal("100")
                if sdk_pos_side == PositionSide.LONG or (sdk_pos_side == PositionSide.NET and side == OrderSide.BUY):
                    order_spec.stop_loss = limit_price * (Decimal("1") - sl_pct)
                else:
                    order_spec.stop_loss = limit_price * (Decimal("1") + sl_pct)
                logger.info(
                    f"Applied fixed stop-loss for limit order: SL={order_spec.stop_loss} "
                    f"(price={limit_price}, pct={self.config.stop_loss_pct}%)"
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

    def cancel_order(self, order: Order | str) -> bool:
        """
        取消订单

        Args:
            order: 数据库订单对象或订单 ID (exchange_order_id / client_order_id / id)

        Returns:
            bool - 是否成功
        """
        try:
            if isinstance(order, str):
                order_id_str = order
                db_order = self.db.query(Order).filter(
                    Order.session_id == self.session_id,
                    (Order.exchange_order_id == order_id_str) | (Order.client_order_id == order_id_str) | (Order.id == order_id_str),
                ).first()
                if db_order is None:
                    return self.exchange_adapter.cancel_order(
                        symbol=self.config.symbol,
                        order_id=order_id_str,
                    )
                order = db_order

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

