"""Simulated Paper Trading Exchange Client for zero-key live simulation."""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)


class PaperExchangeClient:
    """Simulates an OKX-compatible exchange client in memory using real market prices."""

    def __init__(self, initial_balance: float = 10_000.0):
        self.initial_balance = float(initial_balance)
        self.cash = float(initial_balance)
        self.positions: Dict[str, Dict[str, Any]] = {}
        self.orders: Dict[str, Dict[str, Any]] = {}
        self.leverage: Dict[str, int] = {}
        self.fee_rate: float = 0.0004  # 4 bps taker fee
        self._price_cache: Dict[str, tuple[float, float]] = {}  # symbol -> (price, timestamp)

    def _fetch_public_ticker_price(self, symbol: str) -> float:
        """Fetch real-time ticker price from OKX public endpoint with caching."""
        now = time.time()
        if symbol in self._price_cache:
            price, ts = self._price_cache[symbol]
            if now - ts < 1.0:  # 1s cache
                return price

        inst_id = symbol
        try:
            url = f"https://www.okx.com/api/v5/market/ticker?instId={inst_id}"
            res = requests.get(url, timeout=3.0)
            if res.status_code == 200:
                data = res.json()
                rows = data.get("data", [])
                if rows and "last" in rows[0]:
                    px = float(rows[0]["last"])
                    if px > 0:
                        self._price_cache[symbol] = (px, now)
                        return px
        except Exception as e:
            logger.debug(f"[PaperExchangeClient] Public ticker fetch failed for {symbol}: {e}")

        # Fallback to cached price or default
        if symbol in self._price_cache:
            return self._price_cache[symbol][0]
        return 65000.0 if "BTC" in symbol else (3500.0 if "ETH" in symbol else 100.0)

    def ping(self) -> bool:
        return True

    def get_ticker(self, inst_id: str) -> Dict[str, Any]:
        price = self._fetch_public_ticker_price(inst_id)
        return {
            "instId": inst_id,
            "last": str(price),
            "askPx": str(round(price * 1.0001, 2)),
            "bidPx": str(round(price * 0.9999, 2)),
            "ts": str(int(time.time() * 1000)),
        }

    def get_instrument(self, inst_id: str) -> Dict[str, Any]:
        return {
            "instId": inst_id,
            "instType": "SWAP" if "SWAP" in inst_id else "SPOT",
            "minSz": "0.001",
            "maxSz": "1000000",
            "lotSz": "0.001",
            "tickSz": "0.1",
            "ctVal": "1",
            "state": "live",
        }

    def set_leverage(self, inst_id: str, lever: int, mgn_mode: str = "cross") -> Dict[str, Any]:
        self.leverage[inst_id] = int(lever)
        return {"instId": inst_id, "lever": str(lever), "mgnMode": mgn_mode}

    def get_positions(self, inst_id: Optional[str] = None) -> List[Dict[str, Any]]:
        results = []
        now_ts = str(int(time.time() * 1000))
        target_symbols = [inst_id] if inst_id else list(self.positions.keys())

        for sym in target_symbols:
            pos_data = self.positions.get(sym)
            if not pos_data:
                continue

            pos_size = float(pos_data.get("pos", 0.0))
            if abs(pos_size) < 1e-8:
                continue

            avg_px = float(pos_data.get("avgPx", 0.0))
            curr_px = self._fetch_public_ticker_price(sym)
            pos_side = "long" if pos_size > 0 else "short"
            upl = (curr_px - avg_px) * pos_size if pos_side == "long" else (avg_px - curr_px) * abs(pos_size)
            upl_ratio = (upl / (avg_px * abs(pos_size))) if avg_px > 0 else 0.0

            results.append({
                "instId": sym,
                "instType": "SWAP" if "SWAP" in sym else "SPOT",
                "mgnMode": "cross",
                "posSide": pos_side,
                "pos": str(abs(pos_size)),
                "availPos": str(abs(pos_size)),
                "avgPx": str(round(avg_px, 4)),
                "markPx": str(round(curr_px, 4)),
                "upl": str(round(upl, 2)),
                "uplRatio": str(round(upl_ratio, 4)),
                "lever": str(self.leverage.get(sym, 1)),
                "notionalUsd": str(round(curr_px * abs(pos_size), 2)),
                "uTime": now_ts,
            })
        return results

    def get_balance(self) -> Dict[str, Any]:
        total_upl = 0.0
        total_margin = 0.0
        for sym, pos_data in self.positions.items():
            pos_size = float(pos_data.get("pos", 0.0))
            if abs(pos_size) < 1e-8:
                continue
            avg_px = float(pos_data.get("avgPx", 0.0))
            curr_px = self._fetch_public_ticker_price(sym)
            pos_side = "long" if pos_size > 0 else "short"
            upl = (curr_px - avg_px) * pos_size if pos_side == "long" else (avg_px - curr_px) * abs(pos_size)
            total_upl += upl
            total_margin += (curr_px * abs(pos_size)) / max(1, self.leverage.get(sym, 1))

        total_equity = self.cash + total_upl
        avail_bal = max(0.0, self.cash - total_margin)

        return {
            "totalEq": str(round(total_equity, 2)),
            "availBal": str(round(avail_bal, 2)),
            "details": [
                {
                    "ccy": "USDT",
                    "eq": str(round(total_equity, 2)),
                    "cashBal": str(round(self.cash, 2)),
                    "availBal": str(round(avail_bal, 2)),
                    "upl": str(round(total_upl, 2)),
                }
            ],
        }

    def place_order(
        self,
        *,
        inst_id: Optional[str] = None,
        instId: Optional[str] = None,
        td_mode: str = "cross",
        tdMode: Optional[str] = None,
        side: str = "buy",
        ord_type: str = "market",
        ordType: Optional[str] = None,
        sz: Optional[str] = None,
        size: Optional[float] = None,
        px: Optional[str] = None,
        price: Optional[float] = None,
        pos_side: Optional[str] = None,
        posSide: Optional[str] = None,
        cl_ord_id: Optional[str] = None,
        clOrdId: Optional[str] = None,
        reduce_only: bool = False,
        reduceOnly: Optional[bool] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        target_inst_id = inst_id or instId or kwargs.get("symbol", "")
        if not target_inst_id:
            raise ValueError("inst_id or instId is required")

        target_ord_type = (ord_type or ordType or "market").lower()

        if sz is not None:
            sz_val = float(sz)
        elif size is not None:
            sz_val = float(size)
        else:
            sz_val = 0.0

        target_px = px if px is not None else (str(price) if price is not None else None)
        curr_price = float(target_px) if (target_px and float(target_px) > 0) else self._fetch_public_ticker_price(target_inst_id)
        order_id = str(uuid.uuid4().hex[:16])
        cl_id = cl_ord_id or clOrdId or f"paper_{int(time.time()*1000)}"

        fee = sz_val * curr_price * self.fee_rate
        self.cash -= fee

        side_lower = (side or kwargs.get("side", "buy")).lower()
        existing = self.positions.get(target_inst_id, {"pos": 0.0, "avgPx": 0.0})
        curr_pos = float(existing.get("pos", 0.0))
        curr_avg = float(existing.get("avgPx", 0.0))

        if side_lower == "buy":
            new_pos = curr_pos + sz_val
            if curr_pos >= 0:
                new_avg = ((curr_pos * curr_avg) + (sz_val * curr_price)) / max(new_pos, 1e-9)
            else:
                # Covering short
                realized_pnl = (curr_avg - curr_price) * min(abs(curr_pos), sz_val)
                self.cash += realized_pnl
                new_avg = curr_avg if new_pos < 0 else curr_price
        else:  # sell
            new_pos = curr_pos - sz_val
            if curr_pos <= 0:
                new_avg = ((abs(curr_pos) * curr_avg) + (sz_val * curr_price)) / max(abs(new_pos), 1e-9)
            else:
                # Closing long
                realized_pnl = (curr_price - curr_avg) * min(curr_pos, sz_val)
                self.cash += realized_pnl
                new_avg = curr_avg if new_pos > 0 else curr_price

        self.positions[target_inst_id] = {
            "pos": new_pos,
            "avgPx": new_avg if abs(new_pos) > 1e-8 else 0.0,
        }

        order_record = {
            "ordId": order_id,
            "clOrdId": cl_id,
            "instId": target_inst_id,
            "side": side_lower,
            "ordType": target_ord_type,
            "sz": str(sz_val),
            "px": str(curr_price),
            "avgPx": str(curr_price),
            "accFillSz": str(sz_val),
            "state": "filled",
            "fee": f"-{round(fee, 4)}",
            "feeCcy": "USDT",
            "cTime": str(int(time.time() * 1000)),
            "uTime": str(int(time.time() * 1000)),
        }
        self.orders[order_id] = order_record

        logger.info(
            f"[PaperExchangeClient] Executed {side} {size} {inst_id} @ {curr_price:.2f} | "
            f"New Pos: {new_pos:.4f} | Cash: ${self.cash:.2f}"
        )

        return {
            "code": "0",
            "msg": "",
            "data": [
                {
                    "ordId": order_id,
                    "clOrdId": cl_id,
                    "tag": "",
                    "sCode": "0",
                    "sMsg": "",
                }
            ],
        }

    def get_order(self, inst_id: str, ord_id: str) -> Dict[str, Any]:
        order = self.orders.get(ord_id)
        if order:
            return order
        return {
            "ordId": ord_id,
            "instId": inst_id,
            "state": "filled",
            "avgPx": str(self._fetch_public_ticker_price(inst_id)),
            "accFillSz": "0",
        }

    def cancel_order(self, inst_id: str, ord_id: str) -> Dict[str, Any]:
        return {"ordId": ord_id, "instId": inst_id, "state": "canceled"}

    def get_open_orders(self, inst_id: Optional[str] = None) -> List[Dict[str, Any]]:
        return []
