"""
Order Manager

订单生命周期管理：创建、追踪、取消、陈旧订单清理
"""
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional
from threading import Lock
from ..core import Order, OrderStatus

logger = logging.getLogger(__name__)


class OrderManager:
    """订单管理器"""

    def __init__(
        self,
        order_timeout_seconds: int = 900,  # 15 分钟
        cancel_stale_orders: bool = True
    ):
        self.order_timeout_seconds = order_timeout_seconds
        self.cancel_stale_orders = cancel_stale_orders

        # 订单追踪
        self.orders: Dict[str, Order] = {}  # order_id -> Order
        self.client_order_map: Dict[str, str] = {}  # client_order_id -> order_id
        self.exchange_order_map: Dict[str, str] = {}  # exchange_order_id -> order_id

        # 线程锁
        self._lock = Lock()

    def add_order(self, order: Order):
        """添加订单"""
        with self._lock:
            self.orders[order.order_id] = order
            self.client_order_map[order.client_order_id] = order.order_id
            if order.exchange_order_id:
                self.exchange_order_map[order.exchange_order_id] = order.order_id

            logger.info(
                f"Order added: {order.order_id} "
                f"(client: {order.client_order_id}, "
                f"exchange: {order.exchange_order_id})"
            )

    def get_order(self, order_id: str) -> Optional[Order]:
        """根据订单 ID 获取订单"""
        with self._lock:
            return self.orders.get(order_id)

    def get_order_by_client_id(self, client_order_id: str) -> Optional[Order]:
        """根据客户端订单 ID 获取订单"""
        with self._lock:
            order_id = self.client_order_map.get(client_order_id)
            if order_id:
                return self.orders.get(order_id)
            return None

    def get_order_by_exchange_id(self, exchange_order_id: str) -> Optional[Order]:
        """根据交易所订单 ID 获取订单"""
        with self._lock:
            order_id = self.exchange_order_map.get(exchange_order_id)
            if order_id:
                return self.orders.get(order_id)
            return None

    def update_order(
        self,
        order_id: str,
        status: Optional[OrderStatus] = None,
        filled_size: Optional[Decimal] = None,
        avg_fill_price: Optional[Decimal] = None,
        exchange_order_id: Optional[str] = None,
        fee: Optional[Decimal] = None,
    ):
        """更新订单"""
        with self._lock:
            order = self.orders.get(order_id)
            if not order:
                logger.warning(f"Order not found: {order_id}")
                return

            if status:
                order.status = status
            if filled_size is not None and avg_fill_price is not None:
                order.update_filled(filled_size, avg_fill_price)
            if exchange_order_id and not order.exchange_order_id:
                order.exchange_order_id = exchange_order_id
                self.exchange_order_map[exchange_order_id] = order_id
            if fee is not None:
                order.fee = fee

            order.updated_at = datetime.utcnow()

            logger.debug(
                f"Order updated: {order_id}, "
                f"status={status}, "
                f"filled={filled_size}/{order.size}"
            )

    def get_open_orders(self) -> List[Order]:
        """获取所有未完成的订单"""
        with self._lock:
            return [
                order for order in self.orders.values()
                if order.status in [
                    OrderStatus.PENDING,
                    OrderStatus.SUBMITTED,
                    OrderStatus.OPEN,
                    OrderStatus.PARTIALLY_FILLED
                ]
            ]

    def get_stale_orders(self) -> List[Order]:
        """获取陈旧订单（超过超时时间的未完成订单）"""
        now = datetime.utcnow()
        timeout_threshold = now - timedelta(seconds=self.order_timeout_seconds)

        with self._lock:
            stale_orders = []
            for order in self.orders.values():
                if order.status in [OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED]:
                    if order.created_at < timeout_threshold:
                        stale_orders.append(order)

            return stale_orders

    def mark_order_stale(self, order_id: str):
        """标记订单为过期"""
        self.update_order(order_id, status=OrderStatus.EXPIRED)
        logger.warning(f"Order marked as stale: {order_id}")

    def remove_order(self, order_id: str):
        """移除订单（谨慎使用）"""
        with self._lock:
            order = self.orders.pop(order_id, None)
            if order:
                self.client_order_map.pop(order.client_order_id, None)
                if order.exchange_order_id:
                    self.exchange_order_map.pop(order.exchange_order_id, None)
                logger.info(f"Order removed: {order_id}")

    def get_orders_by_symbol(self, symbol: str) -> List[Order]:
        """获取指定交易对的所有订单"""
        with self._lock:
            return [order for order in self.orders.values() if order.symbol == symbol]

    def get_order_count(self) -> int:
        """获取订单总数"""
        with self._lock:
            return len(self.orders)

    def get_open_order_count(self) -> int:
        """获取未完成订单数"""
        return len(self.get_open_orders())

    def cleanup_finished_orders(self, keep_hours: int = 24):
        """清理已完成的订单（保留最近 N 小时）"""
        now = datetime.utcnow()
        threshold = now - timedelta(hours=keep_hours)

        with self._lock:
            finished_statuses = [
                OrderStatus.FILLED,
                OrderStatus.CANCELLED,
                OrderStatus.REJECTED,
                OrderStatus.EXPIRED,
                OrderStatus.FAILED
            ]

            orders_to_remove = []
            for order_id, order in self.orders.items():
                if order.status in finished_statuses and order.updated_at < threshold:
                    orders_to_remove.append(order_id)

            for order_id in orders_to_remove:
                self.remove_order(order_id)

            if orders_to_remove:
                logger.info(f"Cleaned up {len(orders_to_remove)} finished orders")

    def get_state(self) -> Dict:
        """获取状态（用于持久化）"""
        with self._lock:
            return {
                "orders": {
                    order_id: {
                        "order_id": order.order_id,
                        "exchange_order_id": order.exchange_order_id,
                        "client_order_id": order.client_order_id,
                        "symbol": order.symbol,
                        "side": order.side.value,
                        "order_type": order.order_type.value,
                        "position_side": order.position_side.value,
                        "status": order.status.value,
                        "size": float(order.size),
                        "filled_size": float(order.filled_size),
                        "price": float(order.price) if order.price else None,
                        "avg_fill_price": float(order.avg_fill_price) if order.avg_fill_price else None,
                        "created_at": order.created_at.isoformat(),
                        "updated_at": order.updated_at.isoformat(),
                    }
                    for order_id, order in self.orders.items()
                }
            }

    def restore_state(self, state: Dict):
        """恢复状态"""
        # 注意：这里需要重新创建 Order 对象，但由于涉及枚举转换，
        # 实际使用时建议从数据库恢复而不是从字典
        logger.info("Order manager state restoration not fully implemented")
