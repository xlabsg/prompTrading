"""
Reconciler

对账机制 - 定期与交易所同步订单和仓位状态
"""
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Dict, Any, Optional, Protocol
from ..core import Order, Position, OrderStatus, PositionStatus

logger = logging.getLogger(__name__)


class ExchangeAdapter(Protocol):
    """交易所适配器协议（用于类型检查）"""

    def get_order(self, symbol: str, order_id: str) -> Optional[Dict[str, Any]]:
        """获取订单信息"""
        ...

    def get_open_orders(self, symbol: str) -> List[Dict[str, Any]]:
        """获取未完成订单"""
        ...

    def get_positions(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """获取仓位信息"""
        ...


class Reconciler:
    """对账器"""

    def __init__(
        self,
        exchange_adapter: ExchangeAdapter,
        reconcile_interval_seconds: int = 60,
        reconcile_on_startup: bool = True,
        reconcile_on_error: bool = True
    ):
        self.exchange_adapter = exchange_adapter
        self.reconcile_interval_seconds = reconcile_interval_seconds
        self.reconcile_on_startup = reconcile_on_startup
        self.reconcile_on_error = reconcile_on_error

        self.last_reconcile_time: Optional[datetime] = None
        self.reconcile_count: int = 0
        self.error_count: int = 0

    def should_reconcile(self) -> bool:
        """判断是否应该执行对账"""
        if self.last_reconcile_time is None:
            return True

        elapsed = datetime.utcnow() - self.last_reconcile_time
        return elapsed.total_seconds() >= self.reconcile_interval_seconds

    def reconcile_orders(
        self,
        local_orders: List[Order],
        symbol: str
    ) -> Dict[str, Any]:
        """
        对账订单

        返回:
            {
                "discrepancies": [...],
                "updated_orders": [...],
                "missing_orders": [...],
            }
        """
        result = {
            "discrepancies": [],
            "updated_orders": [],
            "missing_orders": [],
        }

        try:
            # 获取交易所的订单
            exchange_orders = self.exchange_adapter.get_open_orders(symbol)
            exchange_order_map = {
                order["ordId"]: order for order in exchange_orders
            }

            # 检查本地订单
            for local_order in local_orders:
                if not local_order.exchange_order_id:
                    # 本地订单还没有交易所 ID，跳过
                    continue

                if local_order.status not in [
                    OrderStatus.OPEN,
                    OrderStatus.PARTIALLY_FILLED,
                    OrderStatus.SUBMITTED
                ]:
                    # 已完成的订单不需要对账
                    continue

                exchange_order_id = local_order.exchange_order_id
                exchange_order = exchange_order_map.get(exchange_order_id)

                if exchange_order is None:
                    # 交易所中不存在该订单
                    logger.warning(
                        f"Order {local_order.order_id} "
                        f"(exchange: {exchange_order_id}) not found on exchange"
                    )
                    result["missing_orders"].append({
                        "order_id": local_order.order_id,
                        "exchange_order_id": exchange_order_id,
                        "local_status": local_order.status.value,
                    })
                    continue

                # 比对订单状态
                discrepancy = self._compare_order(local_order, exchange_order)
                if discrepancy:
                    result["discrepancies"].append(discrepancy)
                    result["updated_orders"].append({
                        "order_id": local_order.order_id,
                        "old_status": local_order.status.value,
                        "new_status": discrepancy["exchange_status"],
                        "old_filled": float(local_order.filled_size),
                        "new_filled": discrepancy["exchange_filled"],
                    })

            self.last_reconcile_time = datetime.utcnow()
            self.reconcile_count += 1

            if result["discrepancies"] or result["missing_orders"]:
                logger.warning(
                    f"Reconciliation found {len(result['discrepancies'])} discrepancies "
                    f"and {len(result['missing_orders'])} missing orders"
                )
            else:
                logger.debug("Reconciliation completed, no discrepancies found")

        except Exception as e:
            self.error_count += 1
            logger.error(f"Reconciliation error: {e}", exc_info=True)
            raise

        return result

    def _compare_order(
        self,
        local_order: Order,
        exchange_order: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        比对订单

        返回差异（如果有）
        """
        discrepancy = {}

        # 比对状态
        exchange_status = exchange_order.get("state")
        local_status = local_order.status.value

        status_mapping = {
            "live": "open",
            "partially_filled": "partially_filled",
            "filled": "filled",
            "canceled": "cancelled",
        }

        normalized_exchange_status = status_mapping.get(exchange_status, exchange_status)

        if normalized_exchange_status != local_status:
            discrepancy["status_mismatch"] = True
            discrepancy["local_status"] = local_status
            discrepancy["exchange_status"] = normalized_exchange_status

        # 比对成交数量
        exchange_filled = Decimal(str(exchange_order.get("accFillSz", "0")))
        if exchange_filled != local_order.filled_size:
            discrepancy["filled_mismatch"] = True
            discrepancy["local_filled"] = float(local_order.filled_size)
            discrepancy["exchange_filled"] = float(exchange_filled)

        # 比对平均成交价格
        exchange_avg_price_str = exchange_order.get("avgPx")
        if exchange_avg_price_str and exchange_avg_price_str != "":
            exchange_avg_price = Decimal(exchange_avg_price_str)
            if local_order.avg_fill_price and abs(exchange_avg_price - local_order.avg_fill_price) > Decimal("0.01"):
                discrepancy["price_mismatch"] = True
                discrepancy["local_avg_price"] = float(local_order.avg_fill_price)
                discrepancy["exchange_avg_price"] = float(exchange_avg_price)

        if discrepancy:
            discrepancy["order_id"] = local_order.order_id
            discrepancy["exchange_order_id"] = local_order.exchange_order_id
            return discrepancy

        return None

    def reconcile_positions(
        self,
        local_positions: List[Position],
        symbol: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        对账仓位

        返回:
            {
                "discrepancies": [...],
                "updated_positions": [...],
                "missing_positions": [...],
            }
        """
        result = {
            "discrepancies": [],
            "updated_positions": [],
            "missing_positions": [],
        }

        try:
            # 获取交易所的仓位
            exchange_positions = self.exchange_adapter.get_positions(symbol)
            exchange_position_map = {
                f"{pos['instId']}_{pos.get('posSide', 'net')}": pos
                for pos in exchange_positions
            }

            # 检查本地仓位
            for local_pos in local_positions:
                if local_pos.status != PositionStatus.OPEN:
                    continue

                pos_key = f"{local_pos.symbol}_{local_pos.side.value}"
                exchange_pos = exchange_position_map.get(pos_key)

                if exchange_pos is None:
                    # 交易所中不存在该仓位
                    logger.warning(f"Position {pos_key} not found on exchange")
                    result["missing_positions"].append({
                        "symbol": local_pos.symbol,
                        "side": local_pos.side.value,
                        "local_size": float(local_pos.size),
                    })
                    continue

                # 比对仓位
                discrepancy = self._compare_position(local_pos, exchange_pos)
                if discrepancy:
                    result["discrepancies"].append(discrepancy)
                    result["updated_positions"].append({
                        "symbol": local_pos.symbol,
                        "side": local_pos.side.value,
                        "old_size": float(local_pos.size),
                        "new_size": discrepancy["exchange_size"],
                    })

            if result["discrepancies"] or result["missing_positions"]:
                logger.warning(
                    f"Position reconciliation found {len(result['discrepancies'])} discrepancies "
                    f"and {len(result['missing_positions'])} missing positions"
                )
            else:
                logger.debug("Position reconciliation completed, no discrepancies found")

        except Exception as e:
            self.error_count += 1
            logger.error(f"Position reconciliation error: {e}", exc_info=True)
            raise

        return result

    def _compare_position(
        self,
        local_pos: Position,
        exchange_pos: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """比对仓位"""
        discrepancy = {}

        # 比对仓位大小
        exchange_size = Decimal(str(exchange_pos.get("pos", "0")))
        if abs(exchange_size - local_pos.size) > Decimal("0.0001"):  # 容差
            discrepancy["size_mismatch"] = True
            discrepancy["local_size"] = float(local_pos.size)
            discrepancy["exchange_size"] = float(exchange_size)

        # 比对平均入场价格
        exchange_avg_price_str = exchange_pos.get("avgPx")
        if exchange_avg_price_str:
            exchange_avg_price = Decimal(exchange_avg_price_str)
            if abs(exchange_avg_price - local_pos.entry_price) > Decimal("0.01"):
                discrepancy["entry_price_mismatch"] = True
                discrepancy["local_entry_price"] = float(local_pos.entry_price)
                discrepancy["exchange_entry_price"] = float(exchange_avg_price)

        if discrepancy:
            discrepancy["symbol"] = local_pos.symbol
            discrepancy["side"] = local_pos.side.value
            return discrepancy

        return None

    def get_stats(self) -> Dict[str, Any]:
        """获取对账统计"""
        return {
            "reconcile_count": self.reconcile_count,
            "error_count": self.error_count,
            "last_reconcile_time": (
                self.last_reconcile_time.isoformat()
                if self.last_reconcile_time
                else None
            ),
        }
