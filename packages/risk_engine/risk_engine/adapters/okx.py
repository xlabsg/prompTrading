"""
OKX Exchange Adapter

包装现有的 okx_sdk，实现 ExchangeAdapter 接口
"""
import logging
from decimal import Decimal
from typing import List, Dict, Any, Optional
from .base import ExchangeAdapter
from ..core import (
    OrderSpec, OrderType, OrderSide, PositionSide, TradingMode
)

logger = logging.getLogger(__name__)


class OKXAdapter(ExchangeAdapter):
    """OKX 交易所适配器"""

    def __init__(self, okx_client):
        """
        初始化 OKX 适配器

        Args:
            okx_client: okx_sdk.OKXClient 实例
        """
        self.client = okx_client

    def place_order(self, order_spec: OrderSpec) -> Dict[str, Any]:
        """下单"""
        # 规范化价格和大小
        if order_spec.price:
            price = self.normalize_price(
                order_spec.symbol,
                order_spec.price,
                "down" if order_spec.side == OrderSide.BUY else "up"
            )
        else:
            price = None

        size = self.normalize_size(order_spec.symbol, order_spec.size)

        # 转换订单类型和方向
        ord_type = self.translate_order_type(order_spec.order_type)
        side_params = self.translate_order_side(order_spec.side, order_spec.position_side)

        # 构建订单参数
        order_params = {
            "instId": order_spec.symbol,
            "tdMode": "isolated",  # 默认逐仓
            "side": side_params["side"],
            "ordType": ord_type,
            "sz": str(size),
        }

        # 添加可选参数
        if order_spec.position_side != PositionSide.NET:
            order_params["posSide"] = side_params.get("posSide", "net")

        if price:
            order_params["px"] = str(price)

        if order_spec.reduce_only:
            order_params["reduceOnly"] = True

        if order_spec.client_order_id:
            order_params["clOrdId"] = order_spec.client_order_id

        # 如果有 TP/SL，使用 attachAlgoOrds
        if order_spec.take_profit or order_spec.stop_loss:
            attach_algo_orders = []

            if order_spec.take_profit:
                attach_algo_orders.append({
                    "attachAlgoClOrdId": f"{order_spec.client_order_id}_tp" if order_spec.client_order_id else None,
                    "tpTriggerPx": str(order_spec.take_profit),
                    "tpOrdPx": "-1",  # 市价
                })

            if order_spec.stop_loss:
                attach_algo_orders.append({
                    "attachAlgoClOrdId": f"{order_spec.client_order_id}_sl" if order_spec.client_order_id else None,
                    "slTriggerPx": str(order_spec.stop_loss),
                    "slOrdPx": "-1",  # 市价
                })

            order_params["attachAlgoOrds"] = attach_algo_orders

        # 调用 OKX API
        try:
            response = self.client.place_order(**order_params)
            return response
        except Exception as e:
            logger.error(f"Failed to place order: {e}")
            raise

    def cancel_order(self, symbol: str, order_id: str) -> bool:
        """取消订单"""
        try:
            self.client.cancel_order(inst_id=symbol, ord_id=order_id)
            return True
        except Exception as e:
            logger.error(f"Failed to cancel order: {e}")
            return False

    def get_order(self, symbol: str, order_id: str) -> Optional[Dict[str, Any]]:
        """获取订单信息"""
        try:
            return self.client.get_order(inst_id=symbol, ord_id=order_id)
        except Exception as e:
            logger.error(f"Failed to get order: {e}")
            return None

    def get_open_orders(self, symbol: str) -> List[Dict[str, Any]]:
        """获取未完成订单"""
        try:
            response = self.client.get_open_orders(inst_id=symbol)
            return response if response else []
        except Exception as e:
            logger.error(f"Failed to get open orders: {e}")
            return []

    def get_positions(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """获取仓位信息"""
        try:
            positions = self.client.get_positions(inst_id=symbol)
            return positions if positions else []
        except Exception as e:
            logger.error(f"Failed to get positions: {e}")
            return []

    def get_balance(self) -> Dict[str, Any]:
        """获取账户余额"""
        try:
            balance_info = self.client.get_balance()
            return balance_info
        except Exception as e:
            logger.error(f"Failed to get balance: {e}")
            return {}

    def set_leverage(self, symbol: str, leverage: int, margin_mode: TradingMode) -> bool:
        """设置杠杆"""
        try:
            mg_mode = "isolated" if margin_mode == TradingMode.ISOLATED else "cross"
            self.client.set_leverage(
                inst_id=symbol,
                lever=str(leverage),
                mg_mode=mg_mode
            )
            return True
        except Exception as e:
            logger.error(f"Failed to set leverage: {e}")
            return False

    def get_ticker(self, symbol: str) -> Dict[str, Any]:
        """获取行情信息"""
        try:
            ticker = self.client.get_ticker(inst_id=symbol)
            return ticker if ticker else {}
        except Exception as e:
            logger.error(f"Failed to get ticker: {e}")
            return {}

    def normalize_symbol(self, symbol: str) -> str:
        """规范化交易对符号"""
        # OKX 格式: BTC-USDT-SWAP
        return symbol.upper()

    def normalize_price(self, symbol: str, price: Decimal, direction: str) -> Decimal:
        """规范化价格"""
        # 获取工具信息
        inst_info = self.client.get_instrument(inst_id=symbol)
        if not inst_info:
            return price

        tick_sz = Decimal(str(inst_info.get("tickSz", "0.01")))

        if direction == "down":
            # 向下取整
            steps = int(price / tick_sz)
        else:
            # 向上取整
            steps = int(price / tick_sz) + (1 if price % tick_sz > 0 else 0)

        return Decimal(steps) * tick_sz

    def normalize_size(self, symbol: str, size: Decimal) -> Decimal:
        """规范化订单大小"""
        # 获取工具信息
        inst_info = self.client.get_instrument(inst_id=symbol)
        if not inst_info:
            return size

        lot_sz = Decimal(str(inst_info.get("lotSz", "1")))
        min_sz = Decimal(str(inst_info.get("minSz", "1")))

        # 向下取整到 lot_sz 的倍数
        normalized = (size // lot_sz) * lot_sz

        # 确保不小于最小值
        if normalized < min_sz:
            normalized = min_sz

        return normalized

    def translate_order_type(self, order_type: OrderType) -> str:
        """转换订单类型"""
        mapping = {
            OrderType.MARKET: "market",
            OrderType.LIMIT: "limit",
            OrderType.STOP_MARKET: "conditional",
            OrderType.STOP_LIMIT: "conditional",
            OrderType.TRAILING_STOP: "move_order_stop",
        }
        return mapping.get(order_type, "market")

    def translate_order_side(self, side: OrderSide, position_side: PositionSide) -> Dict[str, str]:
        """转换订单方向"""
        result = {}

        # 基本方向
        result["side"] = "buy" if side == OrderSide.BUY else "sell"

        # 仓位方向
        if position_side == PositionSide.LONG:
            result["posSide"] = "long"
        elif position_side == PositionSide.SHORT:
            result["posSide"] = "short"
        else:
            result["posSide"] = "net"

        return result

    def test_connection(self) -> bool:
        """测试连接"""
        try:
            self.client.ping()
            return True
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            return False
