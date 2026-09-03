"""Binance Exchange Adapter

实现 ExchangeAdapter 抽象基类，包装 BinanceClient，对齐 risk_engine 内部数据协议。
"""

import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional

from .base import ExchangeAdapter
from .binance_client import BinanceClient
from ..core import (
    OrderSide,
    OrderSpec,
    OrderType,
    PositionSide,
    TradingMode,
)

logger = logging.getLogger(__name__)


class BinanceAdapter(ExchangeAdapter):
    """Binance 交易所适配器，支持现货与 USDⓈ-M 永续合约。"""

    def __init__(self, binance_client: BinanceClient):
        """
        初始化 Binance 适配器。

        Args:
            binance_client: BinanceClient 实例
        """
        self.client = binance_client

    def normalize_symbol(self, symbol: str) -> str:
        """规范化交易对符号为 Binance 格式 (如 BTC-USDT-SWAP / BTC/USDT -> BTCUSDT)"""
        s = symbol.upper().replace("-SWAP", "").replace("/", "").replace("-", "")
        return s

    def normalize_price(self, symbol: str, price: Decimal, direction: str) -> Decimal:
        """规范化价格精度"""
        norm_sym = self.normalize_symbol(symbol)
        filters = self.client.get_symbol_filters(norm_sym)
        tick_sz = filters["tickSize"]

        if tick_sz <= 0:
            return price

        if direction == "down":
            steps = int(price / tick_sz)
        else:
            steps = int(price / tick_sz) + (1 if price % tick_sz > 0 else 0)

        return Decimal(steps) * tick_sz

    def normalize_size(self, symbol: str, size: Decimal) -> Decimal:
        """规范化订单大小精度"""
        norm_sym = self.normalize_symbol(symbol)
        filters = self.client.get_symbol_filters(norm_sym)
        step_sz = filters["stepSize"]
        min_qty = filters["minQty"]

        if step_sz <= 0:
            return size

        normalized = (size // step_sz) * step_sz
        if normalized < min_qty:
            normalized = min_qty

        return normalized

    def translate_order_type(self, order_type: OrderType) -> str:
        """转换订单类型"""
        mapping = {
            OrderType.MARKET: "MARKET",
            OrderType.LIMIT: "LIMIT",
            OrderType.STOP_MARKET: "STOP_MARKET",
            OrderType.STOP_LIMIT: "STOP",
            OrderType.TRAILING_STOP: "TRAILING_STOP_MARKET",
        }
        return mapping.get(order_type, "MARKET")

    def translate_order_side(self, side: OrderSide, position_side: PositionSide) -> Dict[str, str]:
        """转换订单方向与持仓方向"""
        result = {"side": "BUY" if side == OrderSide.BUY else "SELL"}
        if position_side == PositionSide.LONG:
            result["positionSide"] = "LONG"
        elif position_side == PositionSide.SHORT:
            result["positionSide"] = "SHORT"
        else:
            result["positionSide"] = "BOTH"
        return result

    def place_order(self, order_spec: OrderSpec) -> Dict[str, Any]:
        """下单"""
        norm_sym = self.normalize_symbol(order_spec.symbol)

        # 规范化价格与大小
        price = (
            self.normalize_price(
                norm_sym,
                order_spec.price,
                "down" if order_spec.side == OrderSide.BUY else "up",
            )
            if order_spec.price
            else None
        )
        size = self.normalize_size(norm_sym, order_spec.size)

        side_params = self.translate_order_side(order_spec.side, order_spec.position_side)
        ord_type = self.translate_order_type(order_spec.order_type)

        try:
            res = self.client.place_order(
                symbol=norm_sym,
                side=side_params["side"],
                order_type=ord_type,
                quantity=size,
                price=price,
                client_order_id=order_spec.client_order_id,
                reduce_only=order_spec.reduce_only,
                position_side=side_params.get("positionSide"),
                stop_price=order_spec.stop_loss,
            )
            return res
        except Exception as e:
            logger.error(f"Failed to place Binance order: {e}")
            raise

    def cancel_order(self, symbol: str, order_id: str) -> bool:
        """取消订单"""
        norm_sym = self.normalize_symbol(symbol)
        try:
            # 判断 order_id 是否为纯数字 (交易所 ID) 还是 client_order_id
            if str(order_id).isdigit():
                self.client.cancel_order(norm_sym, order_id=order_id)
            else:
                self.client.cancel_order(norm_sym, client_order_id=order_id)
            return True
        except Exception as e:
            logger.error(f"Failed to cancel Binance order: {e}")
            return False

    def get_order(self, symbol: str, order_id: str) -> Optional[Dict[str, Any]]:
        """获取订单信息"""
        norm_sym = self.normalize_symbol(symbol)
        try:
            if str(order_id).isdigit():
                return self.client.get_order(norm_sym, order_id=order_id)
            else:
                return self.client.get_order(norm_sym, client_order_id=order_id)
        except Exception as e:
            logger.error(f"Failed to get Binance order: {e}")
            return None

    def get_open_orders(self, symbol: str) -> List[Dict[str, Any]]:
        """获取未完成订单"""
        norm_sym = self.normalize_symbol(symbol)
        try:
            return self.client.get_open_orders(norm_sym)
        except Exception as e:
            logger.error(f"Failed to get Binance open orders: {e}")
            return []

    def get_positions(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        获取仓位信息，并映射为统一格式（与 OKX 仓位结构兼容）。
        """
        norm_sym = self.normalize_symbol(symbol) if symbol else None
        try:
            raw_positions = self.client.get_positions(norm_sym)
            normalized_list = []

            for p in raw_positions:
                pos_amt = Decimal(str(p.get("positionAmt", "0")))
                if pos_amt == 0:
                    continue

                # 判断方向
                pos_side_raw = p.get("positionSide", "BOTH").upper()
                if pos_side_raw == "LONG":
                    side_str = "long"
                elif pos_side_raw == "SHORT":
                    side_str = "short"
                else:
                    side_str = "long" if pos_amt > 0 else "short"

                entry_px = str(p.get("entryPrice", "0"))
                mark_px = str(p.get("markPrice", "0"))
                upl = str(p.get("unRealizedProfit", "0"))
                lever = int(p.get("leverage", 1))
                margin = str(p.get("isolatedMargin", p.get("initialMargin", "0")))
                liq_px = str(p.get("liquidationPrice", "0"))

                normalized_list.append({
                    "instId": p.get("symbol", ""),
                    "pos": str(abs(pos_amt)),
                    "posSide": side_str,
                    "avgPx": entry_px,
                    "markPx": mark_px,
                    "last": mark_px,
                    "upl": upl,
                    "realizedPnl": "0",
                    "lever": lever,
                    "margin": margin,
                    "liqPx": liq_px if Decimal(liq_px) > 0 else None,
                    "raw": p,
                })

            return normalized_list
        except Exception as e:
            logger.error(f"Failed to get Binance positions: {e}")
            return []

    def get_balance(self) -> Dict[str, Any]:
        """获取账户余额，映射与 OKX 格式兼容的 totalEq 与 availBal"""
        try:
            res = self.client.get_balance()
            balances = res.get("balances", [])

            total_equity = Decimal("0")
            avail_balance = Decimal("0")

            for b in balances:
                asset = b.get("asset", "")
                if asset in ("USDT", "USDC", "BUSD"):
                    # 合约余额字段
                    bal = Decimal(str(b.get("balance", b.get("free", "0"))))
                    avail = Decimal(str(b.get("availableBalance", b.get("free", "0"))))
                    total_equity += bal
                    avail_balance += avail

            return {
                "totalEq": str(total_equity),
                "availBal": str(avail_balance),
                "availEq": str(avail_balance),
                "details": balances,
            }
        except Exception as e:
            logger.error(f"Failed to get Binance balance: {e}")
            return {"totalEq": "0", "availBal": "0", "details": []}

    def set_leverage(self, symbol: str, leverage: int, margin_mode: TradingMode) -> bool:
        """设置合约杠杆与保证金模式"""
        norm_sym = self.normalize_symbol(symbol)
        try:
            # 保证金模式 (ISOLATED 或 CROSSED)
            mode_str = "ISOLATED" if margin_mode == TradingMode.ISOLATED else "CROSSED"
            self.client.set_margin_type(norm_sym, mode_str)
            # 设置杠杆
            self.client.set_leverage(norm_sym, leverage)
            return True
        except Exception as e:
            logger.error(f"Failed to set Binance leverage: {e}")
            return False

    def get_ticker(self, symbol: str) -> Dict[str, Any]:
        """获取行情信息"""
        norm_sym = self.normalize_symbol(symbol)
        try:
            return self.client.get_ticker(norm_sym)
        except Exception as e:
            logger.error(f"Failed to get Binance ticker: {e}")
            return {"symbol": norm_sym, "last": "0"}

    def test_connection(self) -> bool:
        """测试连接"""
        try:
            return self.client.ping()
        except Exception as e:
            logger.error(f"Binance connection test failed: {e}")
            return False
