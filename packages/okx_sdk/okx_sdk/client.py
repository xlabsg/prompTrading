"""OKX REST API client."""

import json
import time
from typing import Optional
from urllib.parse import urlencode

import requests

from okx_sdk.auth import generate_headers, generate_timestamp
from okx_sdk.exceptions import OKXAPIError, OKXAuthError, OKXError
from okx_sdk.models import Balance, OrderResponse, Position
from okx_sdk.utils import format_decimal, normalize_order_size


class OKXClient:
    """OKX REST API client for trading operations."""
    
    BASE_URL = "https://www.okx.com"
    
    def __init__(
        self,
        api_key: str,
        secret_key: str,
        passphrase: str,
        base_url: str = BASE_URL,
        timeout: int = 15,
        simulated: bool = False,
    ):
        """
        Initialize OKX client.
        
        Args:
            api_key: API key
            secret_key: API secret key
            passphrase: API passphrase
            base_url: Base URL for API (default: production)
            timeout: Request timeout in seconds
        """
        if not all([api_key, secret_key, passphrase]):
            raise OKXAuthError("API key, secret key, and passphrase are required")
        
        self.api_key = api_key.strip()
        self.secret_key = secret_key.strip()
        self.passphrase = passphrase.strip()
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.simulated = simulated
        
        # Caches
        self._instrument_cache: dict[str, tuple[float, dict]] = {}
        self._instrument_cache_ttl = 300.0  # 5 minutes
        self._account_config_cache: Optional[tuple[float, dict]] = None
        self._account_config_ttl = 30.0  # 30 seconds
    
    def _request(
        self,
        method: str,
        path: str,
        params: Optional[dict] = None,
        body: Optional[dict] = None,
        signed: bool = True,
    ) -> dict:
        """
        Make an HTTP request to OKX API.
        
        Args:
            method: HTTP method
            path: API endpoint path
            params: Query parameters
            body: Request body (for POST requests)
            signed: Whether to sign the request
            
        Returns:
            Response data
            
        Raises:
            OKXAPIError: If API returns an error
            OKXAuthError: If authentication fails
            OKXError: For other errors
        """
        # Build request path with query string
        query_string = ""
        signed_params = None
        if params:
            # Sort params for consistent signing and ensure the on-wire order matches the signature
            signed_params = {k: str(v) if v is not None else "" for k, v in sorted(params.items())}
            query_string = urlencode(signed_params)
        
        request_path = path
        if query_string:
            request_path = f"{path}?{query_string}"
        
        # Prepare request body
        body_str = ""
        if body is not None:
            body_str = json.dumps(body)
        
        # Build headers
        headers = {"Content-Type": "application/json"}
        if self.simulated:
            headers["x-simulated-trading"] = "1"
        if signed:
            timestamp = generate_timestamp()
            auth_headers = generate_headers(
                self.api_key,
                self.secret_key,
                self.passphrase,
                timestamp,
                method,
                request_path,
                body_str,
            )
            headers.update(auth_headers)
        
        # Make request
        url = f"{self.base_url}{path}"
        try:
            response = self.session.request(
                method,
                url,
                params=signed_params if signed_params is not None else params,
                data=body_str if body_str else None,
                headers=headers,
                timeout=self.timeout,
            )
            response.raise_for_status()
        except requests.HTTPError as e:
            if e.response.status_code == 401:
                raise OKXAuthError(f"Authentication failed: {e.response.text}")
            raise OKXAPIError(f"HTTP {e.response.status_code}: {e.response.text}")
        except requests.RequestException as e:
            raise OKXError(f"Request failed: {str(e)}")
        
        # Parse response
        try:
            data = response.json()
        except json.JSONDecodeError:
            raise OKXError(f"Invalid JSON response: {response.text}")
        
        # Check for API errors
        code = str(data.get("code", ""))
        if code != "0":
            msg = data.get("msg", "Unknown error")
            # Debug logging for authentication issues
            if code == "50113":
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"OKX Auth Error - API Key (first 10 chars): {self.api_key[:10]}...")
                logger.error(f"Passphrase (first 3 chars): {self.passphrase[:3]}...")
                logger.error(f"Timestamp: {timestamp}")
                logger.error(f"Request Path: {request_path}")
                logger.error(f"Method: {method}")
            raise OKXAPIError(f"OKX API error: {msg}", code=code, data=data)
        
        return data
    
    def ping(self) -> bool:
        """
        Test API connectivity.
        
        Returns:
            True if API is reachable
        """
        try:
            self._request("GET", "/api/v5/public/time", signed=False)
            return True
        except Exception:
            return False
    
    def test_credentials(self) -> dict:
        """
        Test API credentials by fetching account balance.
        
        Returns:
            Balance response data
            
        Raises:
            OKXAuthError: If credentials are invalid
        """
        return self._request("GET", "/api/v5/account/balance")
    
    def get_instrument(self, inst_type: str, inst_id: str) -> dict:
        """
        Get instrument metadata with caching.
        
        Args:
            inst_type: Instrument type (SPOT, SWAP, etc.)
            inst_id: Instrument ID
            
        Returns:
            Instrument metadata
        """
        cache_key = f"{inst_type}:{inst_id}"
        now = time.time()
        
        # Check cache
        if cache_key in self._instrument_cache:
            cached_time, cached_data = self._instrument_cache[cache_key]
            if now - cached_time < self._instrument_cache_ttl:
                return cached_data
        
        # Fetch from API
        params = {"instType": inst_type.upper(), "instId": inst_id}
        data = self._request("GET", "/api/v5/public/instruments", params=params, signed=False)
        
        instruments = data.get("data", [])
        if not instruments:
            raise OKXError(f"Instrument not found: {inst_id}")
        
        instrument = instruments[0]
        self._instrument_cache[cache_key] = (now, instrument)
        return instrument
    
    def get_account_config(self) -> dict:
        """
        Get account configuration (position mode, etc.) with caching.
        
        Returns:
            Account configuration
        """
        now = time.time()
        
        # Check cache
        if self._account_config_cache:
            cached_time, cached_data = self._account_config_cache
            if now - cached_time < self._account_config_ttl:
                return cached_data
        
        # Fetch from API
        data = self._request("GET", "/api/v5/account/config")
        config = data.get("data", [{}])[0]
        self._account_config_cache = (now, config)
        return config
    
    def get_balance(self, ccy: Optional[str] = None) -> list[Balance]:
        """
        Get account balance.
        
        Args:
            ccy: Optional currency filter
            
        Returns:
            List of balances
        """
        params = {}
        if ccy:
            params["ccy"] = ccy
        
        data = self._request("GET", "/api/v5/account/balance", params=params)
        details = data.get("data", [{}])[0].get("details", [])
        return [Balance(**detail) for detail in details]
    
    def get_positions(self, inst_id: Optional[str] = None) -> list[Position]:
        """
        Get current positions.

        Args:
            inst_id: Optional instrument ID filter

        Returns:
            List of positions
        """
        params = {"instType": "SWAP"}
        if inst_id:
            params["instId"] = inst_id

        data = self._request("GET", "/api/v5/account/positions", params=params)
        positions = data.get("data", [])
        return [Position(**pos) for pos in positions]

    def get_ticker(self, inst_id: str) -> dict:
        """
        Get ticker (real-time price) for an instrument.

        Args:
            inst_id: Instrument ID (e.g., BTC-USDT-SWAP)

        Returns:
            Ticker data with last price, bid/ask, volume, etc.
        """
        params = {"instId": inst_id}
        data = self._request("GET", "/api/v5/market/ticker", params=params, signed=False)
        tickers = data.get("data", [])
        if not tickers:
            raise OKXError(f"Ticker not found for {inst_id}")
        return tickers[0]
    
    def set_leverage(
        self,
        inst_id: str,
        lever: int,
        mgn_mode: str = "cross",
        pos_side: Optional[str] = None,
    ) -> dict:
        """
        Set leverage for an instrument.
        
        Args:
            inst_id: Instrument ID
            lever: Leverage multiplier
            mgn_mode: Margin mode (cross or isolated)
            pos_side: Position side (net, long, short) - required based on position mode
            
        Returns:
            Response data
        """
        body = {
            "instId": inst_id,
            "lever": str(lever),
            "mgnMode": mgn_mode,
        }
        if pos_side:
            body["posSide"] = pos_side
        
        return self._request("POST", "/api/v5/account/set-leverage", body=body)
    
    def place_order(
        self,
        inst_id: str,
        side: str,
        ord_type: str,
        size: float,
        td_mode: str = "cross",
        price: Optional[float] = None,
        pos_side: Optional[str] = None,
        reduce_only: bool = False,
        cl_ord_id: Optional[str] = None,
        market_type: str = "swap",
    ) -> OrderResponse:
        """
        Place an order.
        
        Args:
            inst_id: Instrument ID
            side: Order side (buy or sell)
            ord_type: Order type (market or limit)
            size: Order size in base currency
            td_mode: Trade mode (cash, cross, isolated)
            price: Order price (required for limit orders)
            pos_side: Position side (for SWAP: net, long, short)
            reduce_only: Reduce only flag
            cl_ord_id: Client order ID
            market_type: Market type (spot or swap)
            
        Returns:
            Order response
        """
        # Get instrument metadata for size normalization
        inst_type = "SPOT" if market_type.lower() == "spot" else "SWAP"
        try:
            instrument = self.get_instrument(inst_type, inst_id)
            lot_sz = instrument.get("lotSz")
            min_sz = instrument.get("minSz")
            ct_val = instrument.get("ctVal") if market_type.lower() != "spot" else None
        except Exception:
            lot_sz = min_sz = ct_val = None
        
        # Normalize size
        normalized_size = normalize_order_size(
            size,
            lot_sz=lot_sz,
            min_sz=min_sz,
            ct_val=ct_val,
            market_type=market_type,
        )
        
        if normalized_size <= 0:
            raise OKXError(f"Order size too small after normalization: {size} -> {normalized_size}")
        
        # Resolve position side for SWAP
        if market_type.lower() != "spot" and not pos_side:
            try:
                config = self.get_account_config()
                pos_mode = config.get("posMode", "").lower()
                if pos_mode in ("net_mode", "net"):
                    pos_side = "net"
                else:
                    raise OKXError("pos_side is required for long_short_mode")
            except Exception as e:
                raise OKXError(f"Failed to determine position side: {e}")
        
        # Build order request
        body = {
            "instId": inst_id,
            "tdMode": td_mode if market_type.lower() != "spot" else "cash",
            "side": side.lower(),
            "ordType": ord_type.lower(),
            "sz": format_decimal(normalized_size),
        }
        
        if market_type.lower() != "spot" and pos_side:
            body["posSide"] = pos_side
        
        if ord_type.lower() == "limit":
            if price is None:
                raise OKXError("Price is required for limit orders")
            body["px"] = str(price)
        
        if reduce_only:
            body["reduceOnly"] = "true"
        
        if cl_ord_id:
            body["clOrdId"] = cl_ord_id
        
        # For spot: set tgtCcy to base_ccy so size is in base currency
        if market_type.lower() == "spot":
            body["tgtCcy"] = "base_ccy"
        
        # Place order
        data = self._request("POST", "/api/v5/trade/order", body=body)
        order_data = data.get("data", [{}])[0]
        return OrderResponse(**order_data)
    
    def cancel_order(
        self,
        inst_id: str,
        ord_id: Optional[str] = None,
        cl_ord_id: Optional[str] = None,
    ) -> dict:
        """
        Cancel an order.
        
        Args:
            inst_id: Instrument ID
            ord_id: Order ID (either this or cl_ord_id required)
            cl_ord_id: Client order ID (either this or ord_id required)
            
        Returns:
            Cancel response
        """
        if not ord_id and not cl_ord_id:
            raise OKXError("Either ord_id or cl_ord_id is required")
        
        body = {"instId": inst_id}
        if ord_id:
            body["ordId"] = ord_id
        if cl_ord_id:
            body["clOrdId"] = cl_ord_id
        
        return self._request("POST", "/api/v5/trade/cancel-order", body=body)
    
    def get_order(
        self,
        inst_id: str,
        ord_id: Optional[str] = None,
        cl_ord_id: Optional[str] = None,
    ) -> dict:
        """
        Get order details.

        Args:
            inst_id: Instrument ID
            ord_id: Order ID (either this or cl_ord_id required)
            cl_ord_id: Client order ID (either this or ord_id required)

        Returns:
            Order details
        """
        if not ord_id and not cl_ord_id:
            raise OKXError("Either ord_id or cl_ord_id is required")

        params = {"instId": inst_id}
        if ord_id:
            params["ordId"] = ord_id
        if cl_ord_id:
            params["clOrdId"] = cl_ord_id

        data = self._request("GET", "/api/v5/trade/order", params=params)
        orders = data.get("data", [])
        return orders[0] if orders else {}

    def get_orders_history(
        self,
        inst_type: str = "SWAP",
        inst_id: Optional[str] = None,
        limit: int = 100,
        after: Optional[str] = None,
        use_archive: bool = False,
    ) -> list[dict]:
        """
        Get order history (last 7 days).

        Args:
            inst_type: Instrument type (SWAP, SPOT, etc.)
            inst_id: Optional instrument ID filter
            limit: Number of results (max 100)
            after: OKX pagination cursor (ordId of the last item from previous page)
            use_archive: Whether to fall back to the archive endpoint for older data

        Returns:
            List of historical orders
        """
        params = {
            "instType": inst_type,
            "limit": str(min(limit, 100)),
        }
        if inst_id:
            params["instId"] = inst_id
        if after:
            params["after"] = after

        data = self._request("GET", "/api/v5/trade/orders-history", params=params)
        orders = data.get("data", [])

        if use_archive and len(orders) < limit and not after:
            archive_data = self._request(
                "GET",
                "/api/v5/trade/orders-history-archive",
                params=params,
            )
            orders.extend(archive_data.get("data", []))

        return orders

    def get_positions_history(
        self,
        inst_type: str = "SWAP",
        inst_id: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict]:
        """
        Get position history (closed positions).

        Args:
            inst_type: Instrument type (SWAP, FUTURES, etc.)
            inst_id: Optional instrument ID filter
            limit: Number of results (max 100)

        Returns:
            List of closed positions
        """
        params = {
            "instType": inst_type,
            "limit": str(min(limit, 100)),
        }
        if inst_id:
            params["instId"] = inst_id

        data = self._request("GET", "/api/v5/account/positions-history", params=params)
        return data.get("data", [])

    def get_pending_orders(
        self,
        inst_type: str = "SWAP",
        inst_id: Optional[str] = None,
    ) -> list[dict]:
        """
        Get pending orders (unfilled or partially filled).

        Args:
            inst_type: Instrument type (SWAP, SPOT, etc.)
            inst_id: Optional instrument ID filter

        Returns:
            List of pending orders
        """
        params = {"instType": inst_type}
        if inst_id:
            params["instId"] = inst_id

        data = self._request("GET", "/api/v5/trade/orders-pending", params=params)
        return data.get("data", [])
