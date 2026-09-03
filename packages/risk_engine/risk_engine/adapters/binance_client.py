"""Binance REST API client supporting Spot and USDⓈ-M Futures."""

import hashlib
import hmac
import logging
import time
from decimal import Decimal
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

import requests

logger = logging.getLogger(__name__)


class BinanceAPIError(Exception):
    """Exception raised for Binance API errors."""

    def __init__(self, status_code: int, code: int, message: str):
        self.status_code = status_code
        self.code = code
        self.message = message
        super().__init__(f"Binance API Error [{code}]: {message} (HTTP {status_code})")


class BinanceClient:
    """Binance REST API client with connection pooling and caching."""

    SPOT_PROD_URL = "https://api.binance.com"
    SPOT_TESTNET_URL = "https://testnet.binance.vision"
    FUTURES_PROD_URL = "https://fapi.binance.com"
    FUTURES_TESTNET_URL = "https://testnet.binancefuture.com"

    def __init__(
        self,
        api_key: str,
        secret_key: str,
        testnet: bool = False,
        timeout: int = 15,
        default_futures: bool = True,
    ):
        self.api_key = (api_key or "").strip()
        self.secret_key = (secret_key or "").strip()
        self.testnet = testnet
        self.timeout = timeout
        self.default_futures = default_futures

        self.spot_base_url = self.SPOT_TESTNET_URL if testnet else self.SPOT_PROD_URL
        self.futures_base_url = self.FUTURES_TESTNET_URL if testnet else self.FUTURES_PROD_URL

        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "prompTrading/1.0",
        })

        self._exchange_info_cache: Dict[str, tuple[float, Dict[str, Any]]] = {}
        self._exchange_info_ttl = 300.0  # 5 minutes

    def _sign(self, query_string: str) -> str:
        """Compute HMAC-SHA256 signature."""
        return hmac.new(
            self.secret_key.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        signed: bool = False,
        is_futures: Optional[bool] = None,
    ) -> Any:
        """Send HTTP request to Binance."""
        if is_futures is None:
            is_futures = self.default_futures

        base_url = self.futures_base_url if is_futures else self.spot_base_url
        url = f"{base_url}{endpoint}"

        headers = {}
        if self.api_key:
            headers["X-MBX-APIKEY"] = self.api_key

        payload = {k: v for k, v in (params or {}).items() if v is not None}

        if signed:
            payload["timestamp"] = int(time.time() * 1000)
            payload["recvWindow"] = 5000
            query_string = urlencode(payload)
            signature = self._sign(query_string)
            query_string = f"{query_string}&signature={signature}"
        else:
            query_string = urlencode(payload)

        try:
            if method.upper() == "GET":
                req_url = f"{url}?{query_string}" if query_string else url
                resp = self.session.get(req_url, headers=headers, timeout=self.timeout)
            elif method.upper() == "POST":
                resp = self.session.post(url, headers=headers, data=query_string, timeout=self.timeout)
            elif method.upper() == "DELETE":
                req_url = f"{url}?{query_string}" if query_string else url
                resp = self.session.delete(req_url, headers=headers, timeout=self.timeout)
            else:
                resp = self.session.request(method, url, headers=headers, data=query_string, timeout=self.timeout)

            if not resp.ok:
                try:
                    err_json = resp.json()
                    raise BinanceAPIError(
                        status_code=resp.status_code,
                        code=err_json.get("code", -1),
                        message=err_json.get("msg", resp.text),
                    )
                except ValueError:
                    resp.raise_for_status()

            return resp.json()
        except requests.RequestException as exc:
            logger.error(f"Binance HTTP error on {method} {endpoint}: {exc}")
            raise

    # -------------------------------------------------------------------------
    # Connectivity & Market Data
    # -------------------------------------------------------------------------

    def ping(self, is_futures: Optional[bool] = None) -> bool:
        """Test API connectivity."""
        endpoint = "/fapi/v1/ping" if (is_futures if is_futures is not None else self.default_futures) else "/api/v3/ping"
        self._request("GET", endpoint, signed=False, is_futures=is_futures)
        return True

    def get_ticker(self, symbol: str, is_futures: Optional[bool] = None) -> Dict[str, Any]:
        """Get latest price for a symbol."""
        endpoint = "/fapi/v1/ticker/price" if (is_futures if is_futures is not None else self.default_futures) else "/api/v3/ticker/price"
        data = self._request("GET", endpoint, params={"symbol": symbol.upper()}, signed=False, is_futures=is_futures)
        # Unified format: last price
        return {"symbol": data.get("symbol", symbol), "last": data.get("price", "0")}

    def get_exchange_info(self, symbol: Optional[str] = None, is_futures: Optional[bool] = None) -> Dict[str, Any]:
        """Fetch and cache exchange info for symbol filters (tickSize, stepSize)."""
        fut = is_futures if is_futures is not None else self.default_futures
        cache_key = f"{'futures' if fut else 'spot'}_{symbol or 'all'}"
        now = time.time()

        if cache_key in self._exchange_info_cache:
            cached_time, cached_data = self._exchange_info_cache[cache_key]
            if now - cached_time < self._exchange_info_ttl:
                return cached_data

        endpoint = "/fapi/v1/exchangeInfo" if fut else "/api/v3/exchangeInfo"
        params = {"symbol": symbol.upper()} if symbol else {}
        try:
            data = self._request("GET", endpoint, params=params, signed=False, is_futures=fut)
            self._exchange_info_cache[cache_key] = (now, data)
            return data
        except Exception as e:
            logger.warning(f"Failed to fetch exchangeInfo: {e}")
            if cache_key in self._exchange_info_cache:
                return self._exchange_info_cache[cache_key][1]
            return {}

    def get_symbol_filters(self, symbol: str, is_futures: Optional[bool] = None) -> Dict[str, Decimal]:
        """Extract tickSize and stepSize filters for precision normalization."""
        info = self.get_exchange_info(symbol, is_futures=is_futures)
        symbols = info.get("symbols", [])
        if not symbols and "filters" in info:
            symbols = [info]

        target_sym = symbol.upper()
        found_symbol = None
        for s in symbols:
            if s.get("symbol") == target_sym:
                found_symbol = s
                break

        res = {
            "tickSize": Decimal("0.01"),
            "stepSize": Decimal("0.001"),
            "minQty": Decimal("0.001"),
            "minNotional": Decimal("5.0"),
        }

        if not found_symbol:
            return res

        for f in found_symbol.get("filters", []):
            f_type = f.get("filterType")
            if f_type in ("PRICE_FILTER",):
                if "tickSize" in f:
                    res["tickSize"] = Decimal(str(f["tickSize"]))
            elif f_type in ("LOT_SIZE", "MARKET_LOT_SIZE"):
                if "stepSize" in f:
                    res["stepSize"] = Decimal(str(f["stepSize"]))
                if "minQty" in f:
                    res["minQty"] = Decimal(str(f["minQty"]))
            elif f_type in ("MIN_NOTIONAL", "NOTIONAL"):
                notional = f.get("minNotional") or f.get("notional")
                if notional:
                    res["minNotional"] = Decimal(str(notional))

        return res

    # -------------------------------------------------------------------------
    # Trading Operations
    # -------------------------------------------------------------------------

    def place_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: Optional[Decimal | float | str] = None,
        price: Optional[Decimal | float | str] = None,
        client_order_id: Optional[str] = None,
        time_in_force: Optional[str] = None,
        reduce_only: bool = False,
        stop_price: Optional[Decimal | float | str] = None,
        position_side: Optional[str] = None,
        is_futures: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Place order on Binance Spot or Futures."""
        fut = is_futures if is_futures is not None else self.default_futures
        endpoint = "/fapi/v1/order" if fut else "/api/v3/order"

        params: Dict[str, Any] = {
            "symbol": symbol.upper(),
            "side": side.upper(),
            "type": order_type.upper(),
        }

        if quantity is not None:
            params["quantity"] = str(quantity)

        if price is not None:
            params["price"] = str(price)

        if client_order_id:
            params["newClientOrderId"] = client_order_id

        if order_type.upper() in ("LIMIT", "STOP_LIMIT", "TAKE_PROFIT_LIMIT"):
            params["timeInForce"] = time_in_force or "GTC"

        if stop_price is not None:
            params["stopPrice"] = str(stop_price)

        if fut:
            if reduce_only:
                params["reduceOnly"] = "true"
            if position_side and position_side.upper() in ("LONG", "SHORT"):
                params["positionSide"] = position_side.upper()

        return self._request("POST", endpoint, params=params, signed=True, is_futures=fut)

    def cancel_order(
        self,
        symbol: str,
        order_id: Optional[str | int] = None,
        client_order_id: Optional[str] = None,
        is_futures: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Cancel an open order."""
        fut = is_futures if is_futures is not None else self.default_futures
        endpoint = "/fapi/v1/order" if fut else "/api/v3/order"

        params: Dict[str, Any] = {"symbol": symbol.upper()}
        if order_id is not None:
            params["orderId"] = str(order_id)
        elif client_order_id is not None:
            params["origClientOrderId"] = client_order_id

        return self._request("DELETE", endpoint, params=params, signed=True, is_futures=fut)

    def get_order(
        self,
        symbol: str,
        order_id: Optional[str | int] = None,
        client_order_id: Optional[str] = None,
        is_futures: Optional[bool] = None,
    ) -> Optional[Dict[str, Any]]:
        """Get order status."""
        fut = is_futures if is_futures is not None else self.default_futures
        endpoint = "/fapi/v1/order" if fut else "/api/v3/order"

        params: Dict[str, Any] = {"symbol": symbol.upper()}
        if order_id is not None:
            params["orderId"] = str(order_id)
        elif client_order_id is not None:
            params["origClientOrderId"] = client_order_id

        try:
            return self._request("GET", endpoint, params=params, signed=True, is_futures=fut)
        except BinanceAPIError as e:
            if e.code in (-2013, -2011):  # Order does not exist
                return None
            raise

    def get_open_orders(
        self,
        symbol: Optional[str] = None,
        is_futures: Optional[bool] = None,
    ) -> List[Dict[str, Any]]:
        """Get open orders."""
        fut = is_futures if is_futures is not None else self.default_futures
        endpoint = "/fapi/v1/openOrders" if fut else "/api/v3/openOrders"
        params = {"symbol": symbol.upper()} if symbol else {}
        res = self._request("GET", endpoint, params=params, signed=True, is_futures=fut)
        return res if isinstance(res, list) else []

    def get_positions(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get futures positions with risk and PnL."""
        endpoint = "/fapi/v2/positionRisk"
        params = {"symbol": symbol.upper()} if symbol else {}
        res = self._request("GET", endpoint, params=params, signed=True, is_futures=True)
        return res if isinstance(res, list) else []

    def get_balance(self, is_futures: Optional[bool] = None) -> Dict[str, Any]:
        """Get account balance."""
        fut = is_futures if is_futures is not None else self.default_futures
        if fut:
            endpoint = "/fapi/v2/balance"
            res = self._request("GET", endpoint, signed=True, is_futures=True)
            return {"balances": res if isinstance(res, list) else []}
        else:
            endpoint = "/api/v3/account"
            res = self._request("GET", endpoint, signed=True, is_futures=False)
            return {"balances": res.get("balances", [])}

    def set_leverage(self, symbol: str, leverage: int) -> Dict[str, Any]:
        """Set futures leverage."""
        return self._request(
            "POST",
            "/fapi/v1/leverage",
            params={"symbol": symbol.upper(), "leverage": int(leverage)},
            signed=True,
            is_futures=True,
        )

    def set_margin_type(self, symbol: str, margin_type: str) -> bool:
        """Set futures margin type: ISOLATED or CROSSED."""
        try:
            self._request(
                "POST",
                "/fapi/v1/marginType",
                params={"symbol": symbol.upper(), "marginType": margin_type.upper()},
                signed=True,
                is_futures=True,
            )
            return True
        except BinanceAPIError as e:
            if e.code == -4046:  # No need to change margin type
                return True
            logger.warning(f"Could not set margin type: {e}")
            return False
