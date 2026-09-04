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

    def _get_instrument(self, symbol: str) -> Dict[str, Any]:
        """获取交易对元数据，兼容 OKXClient(inst_type, inst_id) 和 PaperExchangeClient(inst_id)"""
        inst_type = "SWAP" if "-SWAP" in symbol.upper() else "SPOT"
        try:
            res = self.client.get_instrument(inst_type, symbol)
            return res if isinstance(res, dict) else {}
        except TypeError:
            try:
                res = self.client.get_instrument(symbol)
                return res if isinstance(res, dict) else {}
            except TypeError:
                try:
                    res = self.client.get_instrument(inst_type=inst_type, inst_id=symbol)
                    return res if isinstance(res, dict) else {}
                except Exception as e:
                    logger.warning(f"Failed to fetch instrument for {symbol}: {e}")
                    return {}
            except Exception as e:
                logger.warning(f"Failed to fetch instrument for {symbol}: {e}")
                return {}
        except Exception as e:
            logger.warning(f"Failed to fetch instrument for {symbol}: {e}")
            return {}

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
        pos_side = side_params.get("posSide", "net") if order_spec.position_side != PositionSide.NET else None

        # 调用 OKX API (兼容真实 OKXClient 与 PaperExchangeClient)
        try:
            try:
                # OKXClient snake_case signature
                response = self.client.place_order(
                    inst_id=order_spec.symbol,
                    side=side_params["side"],
                    ord_type=ord_type,
                    size=float(size),
                    price=float(price) if price is not None else None,
                    pos_side=pos_side,
                    reduce_only=bool(order_spec.reduce_only),
                    cl_ord_id=order_spec.client_order_id,
                    td_mode="cross",
                )
            except TypeError:
                # Fallback for PaperExchangeClient or other dictionary-based clients
                order_params = {
                    "inst_id": order_spec.symbol,
                    "instId": order_spec.symbol,
                    "td_mode": "cross",
                    "tdMode": "cross",
                    "side": side_params["side"],
                    "ord_type": ord_type,
                    "ordType": ord_type,
                    "size": float(size),
                    "sz": str(size),
                    "reduce_only": bool(order_spec.reduce_only),
                    "reduceOnly": bool(order_spec.reduce_only),
                }
                if pos_side:
                    order_params["pos_side"] = pos_side
                    order_params["posSide"] = pos_side
                if price is not None:
                    order_params["price"] = float(price)
                    order_params["px"] = str(price)
                if order_spec.client_order_id:
                    order_params["cl_ord_id"] = order_spec.client_order_id
                    order_params["clOrdId"] = order_spec.client_order_id
                response = self.client.place_order(**order_params)

            # 统一标准化返回字典
            if hasattr(response, "ord_id"):
                return {
                    "ordId": response.ord_id,
                    "clOrdId": response.cl_ord_id,
                    "sCode": getattr(response, "s_code", "0"),
                    "sMsg": getattr(response, "s_msg", ""),
                }
            elif isinstance(response, dict):
                data = response.get("data")
                if isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
                    return data[0]
                return response
            return {"ordId": getattr(response, "ordId", str(response))}
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
            res = self.client.get_order(inst_id=symbol, ord_id=order_id)
            if hasattr(res, "model_dump"):
                return res.model_dump()
            return res if isinstance(res, dict) else None
        except Exception as e:
            logger.error(f"Failed to get order: {e}")
            return None

    def get_open_orders(self, symbol: str) -> List[Dict[str, Any]]:
        """获取未完成订单"""
        try:
            if hasattr(self.client, "get_pending_orders"):
                response = self.client.get_pending_orders(inst_id=symbol)
            elif hasattr(self.client, "get_open_orders"):
                response = self.client.get_open_orders(inst_id=symbol)
            else:
                response = []

            if not response:
                return []

            normalized = []
            for o in response:
                if hasattr(o, "model_dump"):
                    normalized.append(o.model_dump())
                elif isinstance(o, dict):
                    normalized.append(o)
                else:
                    normalized.append(getattr(o, "__dict__", {}))
            return normalized
        except Exception as e:
            logger.error(f"Failed to get open orders: {e}")
            return []

    def get_positions(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """获取仓位信息，并映射为与系统统一的标准格式"""
        try:
            raw_positions = self.client.get_positions(inst_id=symbol)
            if not raw_positions:
                return []

            normalized_list = []
            for p in raw_positions:
                inst_id = getattr(p, "inst_id", None) or (p.get("instId") if isinstance(p, dict) else "")
                pos_raw = getattr(p, "pos", None) if not isinstance(p, dict) else p.get("pos")
                pos_amt = Decimal(str(pos_raw or "0"))
                if pos_amt == 0:
                    continue

                pos_side_raw = getattr(p, "pos_side", None) if not isinstance(p, dict) else p.get("posSide", "net")
                side_str = str(pos_side_raw or "net").lower()

                avg_px = str(getattr(p, "avg_px", None) or (p.get("avgPx") if isinstance(p, dict) else "0"))
                mark_px = str(
                    getattr(p, "mark_px", None)
                    or getattr(p, "last", None)
                    or (p.get("markPx", p.get("last", "0")) if isinstance(p, dict) else "0")
                )
                upl = str(getattr(p, "upl", None) or (p.get("upl") if isinstance(p, dict) else "0"))
                realized_pnl = str(
                    getattr(p, "realized_pnl", None) or (p.get("realizedPnl") if isinstance(p, dict) else "0")
                )
                lever = int(getattr(p, "lever", None) or (p.get("lever", 1) if isinstance(p, dict) else 1) or 1)
                margin = str(getattr(p, "margin", None) or (p.get("margin", "0") if isinstance(p, dict) else "0"))
                liq_px = getattr(p, "liq_px", None) or (p.get("liqPx") if isinstance(p, dict) else None)

                normalized_list.append({
                    "instId": inst_id,
                    "pos": str(abs(pos_amt)),
                    "posSide": side_str,
                    "avgPx": avg_px,
                    "markPx": mark_px,
                    "last": mark_px,
                    "upl": upl,
                    "realizedPnl": realized_pnl,
                    "lever": lever,
                    "margin": margin,
                    "liqPx": str(liq_px) if liq_px and Decimal(str(liq_px)) > 0 else None,
                    "raw": p if isinstance(p, dict) else (p.model_dump() if hasattr(p, "model_dump") else {}),
                })
            return normalized_list
        except Exception as e:
            logger.error(f"Failed to get positions: {e}")
            return []

    def get_balance(self) -> Dict[str, Any]:
        """获取账户余额，映射与系统兼容的 totalEq 与 availBal"""
        try:
            balance_info = self.client.get_balance()
            if isinstance(balance_info, dict):
                return balance_info

            if isinstance(balance_info, list):
                total_eq = Decimal("0")
                avail_bal = Decimal("0")
                upl = Decimal("0")
                details = []
                for b in balance_info:
                    eq_usd = (
                        getattr(b, "eqUsd", None)
                        or getattr(b, "eq", None)
                        if not isinstance(b, dict)
                        else (b.get("eqUsd") or b.get("eq"))
                    )
                    avail = getattr(b, "availBal", None) if not isinstance(b, dict) else b.get("availBal")
                    u = getattr(b, "upl", None) if not isinstance(b, dict) else b.get("upl")
                    ccy = getattr(b, "ccy", "") if not isinstance(b, dict) else b.get("ccy", "")

                    b_eq = Decimal(str(eq_usd or "0"))
                    b_avail = Decimal(str(avail or "0"))
                    b_upl = Decimal(str(u or "0"))

                    total_eq += b_eq
                    avail_bal += b_avail
                    upl += b_upl
                    details.append({
                        "ccy": ccy,
                        "eq": str(b_eq),
                        "availBal": str(b_avail),
                        "upl": str(b_upl),
                    })
                return {
                    "totalEq": str(total_eq),
                    "availBal": str(avail_bal),
                    "upl": str(upl),
                    "details": details,
                }
            return {}
        except Exception as e:
            logger.error(f"Failed to get balance: {e}")
            return {}

    def set_leverage(self, symbol: str, leverage: int, margin_mode: TradingMode = TradingMode.CROSS, **kwargs) -> bool:
        """设置杠杆"""
        try:
            mode = kwargs.get("mode", margin_mode)
            mgn_mode = "isolated" if mode == TradingMode.ISOLATED else "cross"
            try:
                self.client.set_leverage(
                    inst_id=symbol,
                    lever=int(leverage),
                    mgn_mode=mgn_mode,
                )
            except TypeError:
                try:
                    self.client.set_leverage(
                        inst_id=symbol,
                        lever=str(leverage),
                        mg_mode=mgn_mode,
                    )
                except TypeError:
                    self.client.set_leverage(
                        symbol=symbol,
                        leverage=int(leverage),
                        mgn_mode=mgn_mode,
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
        """规范化交易对符号为 OKX 格式 (例如 BTC-USDT-SWAP, BTC-USDT)"""
        s = symbol.upper().strip()
        if ":" in s:
            base_quote = s.split(":")[0].replace("/", "-")
            return f"{base_quote}-SWAP"
        if "/" in s:
            return s.replace("/", "-")
        if "-" not in s:
            for quote in ("USDT", "USDC", "USD"):
                if s.endswith(quote):
                    base = s[:-len(quote)]
                    return f"{base}-{quote}-SWAP"
        return s

    def normalize_price(self, symbol: str, price: Decimal, direction: str = "down") -> Decimal:
        """规范化价格"""
        # 获取工具信息
        inst_info = self._get_instrument(symbol)
        price = Decimal(str(price))
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
        inst_info = self._get_instrument(symbol)
        size = Decimal(str(size))
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
