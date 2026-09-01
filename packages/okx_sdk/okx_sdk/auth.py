"""Authentication utilities for OKX API."""

import base64
import hashlib
import hmac
from datetime import datetime, timezone


def generate_timestamp() -> str:
    """Generate OKX API timestamp in ISO 8601 format with milliseconds."""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def generate_signature(
    timestamp: str,
    method: str,
    request_path: str,
    body: str,
    secret_key: str,
) -> str:
    """
    Generate HMAC-SHA256 signature for OKX API request.
    
    Args:
        timestamp: ISO 8601 timestamp
        method: HTTP method (GET, POST, etc.)
        request_path: API endpoint path with query string
        body: Request body as JSON string (empty string for GET)
        secret_key: API secret key
        
    Returns:
        Base64-encoded signature
    """
    message = f"{timestamp}{method.upper()}{request_path}{body}"
    mac = hmac.new(
        secret_key.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256
    )
    return base64.b64encode(mac.digest()).decode("utf-8")


def generate_headers(
    api_key: str,
    secret_key: str,
    passphrase: str,
    timestamp: str,
    method: str,
    request_path: str,
    body: str = "",
) -> dict[str, str]:
    """
    Generate authentication headers for OKX API request.
    
    Args:
        api_key: API key
        secret_key: API secret key
        passphrase: API passphrase
        timestamp: ISO 8601 timestamp
        method: HTTP method
        request_path: API endpoint path with query string
        body: Request body as JSON string
        
    Returns:
        Dictionary of headers
    """
    signature = generate_signature(timestamp, method, request_path, body, secret_key)
    
    return {
        "OK-ACCESS-KEY": api_key,
        "OK-ACCESS-SIGN": signature,
        "OK-ACCESS-TIMESTAMP": timestamp,
        "OK-ACCESS-PASSPHRASE": passphrase,
        "Content-Type": "application/json",
    }
