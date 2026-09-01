# OKX SDK

Python SDK for OKX Exchange trading operations.

## Features

- ✅ REST API client with HMAC-SHA256 authentication
- ✅ Order placement (market and limit orders)
- ✅ Position and balance queries
- ✅ Instrument metadata caching
- ✅ Order size normalization (lot size, min size, contract value)
- ✅ Error handling and custom exceptions

## Installation

```bash
cd packages/okx_sdk
pip install -e .
```

## Usage

```python
from okx_sdk import OKXClient

# Initialize client
client = OKXClient(
    api_key="your_api_key",
    secret_key="your_secret_key",
    passphrase="your_passphrase"
)

# Test connectivity
if client.ping():
    print("Connected to OKX")

# Test credentials
try:
    client.test_credentials()
    print("Credentials are valid")
except OKXAuthError:
    print("Invalid credentials")

# Get balance
balances = client.get_balance(ccy="USDT")
print(f"USDT Balance: {balances[0].avail_bal}")

# Place market order
order = client.place_order(
    inst_id="BTC-USDT-SWAP",
    side="buy",
    ord_type="market",
    size=0.001,  # in BTC
    pos_side="net",
)
print(f"Order ID: {order.ord_id}")

# Get positions
positions = client.get_positions(inst_id="BTC-USDT-SWAP")
for pos in positions:
    print(f"Position: {pos.pos_side} {pos.pos} @ {pos.avg_px}")
```

## Development

Run tests:

```bash
pytest tests/ -v
```
