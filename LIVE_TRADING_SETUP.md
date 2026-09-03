# Live Trading Module - Quick Start Guide

## 🚀 Quick Setup (5 minutes)

### 1. Install Dependencies in API Container

```bash
# From project root
docker compose -f infra/compose/docker-compose.dev.yml exec api bash
cd /app
./setup_and_test.sh
```

This will:
- Install OKX SDK package
- Verify cryptography library
- Run automated tests
- Verify database models

### 2. Set Encryption Key (Development)

```bash
# Generate a key
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Add to docker-compose.dev.yml environment section for 'api' service:
# TRADING_API_ENCRYPTION_KEY=<your-generated-key>

# Restart API container
docker compose -f infra/compose/docker-compose.dev.yml restart api
```

### 3. Configure Trading in UI

1. Navigate to http://localhost:3000
2. Create or select a strategy
3. Go to **Exchange Accounts** dialog
4. Select **OKX** or **Binance**:
   - **OKX**: Enter API Key, API Secret, Passphrase
   - **Binance**: Enter API Key, API Secret (Passphrase is not required)
5. Set risk parameters (max position %, leverage, stop loss, trailing stop)
6. Complete configuration

### 4. Start Trading

- Click **"启动交易"** (Start Trading)
- Monitor real-time PnL, positions, and orders
- Click **"停止交易"** (Stop Trading) to stop

---

## 📋 What Was Implemented

### Backend & Risk Engine
✅ **Multi-Exchange Execution Engine** - Native `OKXAdapter` and `BinanceAdapter` implementing the `ExchangeAdapter` abstraction  
✅ **Microsecond Risk Control** - 9 pre-trade validation checks (`RiskValidator`), dynamic TP/SL, and 60-second periodic reconciler  
✅ **Binance Client & Adapter** - HMAC-SHA256 authenticated REST client with connection pooling, supporting Spot and USDⓈ-M Futures  
✅ **Fernet Encryption** - Secure API credential storage with environment-backed key  
✅ **Trading Engine** - Session manager, order executor, position monitor  

### AI Agent & Trade Kit Skills
✅ **OKX Agent Trade Kit Skills** - Pre-built skills under `packages/agent/skills/`:
   - `okx-cex-market`: 70+ built-in technical indicators (RSI, MACD, BB, ATR, KDJ, AHR999, etc.)
   - `okx-cex-bot`: Native Spot Grid, Contract Grid, and DCA bot parameterization
   - `okx-cex-smartmoney`: Whale tracking, consensus positioning, and top trader leaderboards
   - `binance-cex`: Binance trading conventions, precision filters, and CLI usage
✅ **Quant Toolkit CLI** - `pt-quant indicators --source okx` for fast introspection

### Frontend
✅ **LiveTradingView Component** - Configuration wizard with risk parameter controls  
✅ **Exchange Support** - OKX and Binance fully enabled in UI  
✅ **Real-time Updates** - Status polling every 5 seconds  
✅ **PnL Display** - Shows total PnL and trade count

---

## 🧪 Testing

### Automated Tests

Run in API container:
```bash
docker compose -f infra/compose/docker-compose.dev.yml exec api python test_okx_setup.py
```

Tests:
- ✅ Encryption/Decryption
- ✅ OKX SDK imports
- ✅ Client initialization
- ✅ Auth functions (signature generation)
- ✅ Order size normalization

### Manual Testing

**Test Configuration Flow:**
1. Open Live Trading tab
2. Complete 4-step wizard
3. Verify credentials are validated (backend calls OKX API)
4. Check API returns error for invalid credentials

**Test Trading Session:**
1. Start trading session
2. Verify status changes to "运行中" (Running)
3. Check database for TradingSession record
4. Stop trading session
5. Verify status changes to "已停止" (Stopped)

---

## 📁 Key Files

### Backend
- [`packages/okx_sdk/`](packages/okx_sdk) - OKX SDK package
- [`services/api/app/crypto.py`](services/api/app/crypto.py) - Encryption utilities
- [`services/api/app/trading_engine/`](services/api/app/trading_engine) - Trading engine
- [`services/api/app/routers/trading.py`](services/api/app/routers/trading.py) - API router

### Frontend
- [`apps/web/src/lib/api/trading.ts`](apps/web/src/lib/api/trading.ts) - Trading API client
- [`apps/web/src/components/console/LiveTradingView.tsx`](apps/web/src/components/console/LiveTradingView.tsx) - UI component

---

## ⚠️ Important Notes

> [!WARNING]
> **API Permissions**: Only enable trading permissions on your OKX API key. Never enable withdrawal permissions.

> [!IMPORTANT]
> **Encryption Key**: In production, store `TRADING_API_ENCRYPTION_KEY` in a secure vault (AWS Secrets Manager, etc.). Never commit to version control.

> [!NOTE]
> **OKX Testnet**: Use https://www.okx.com/demo-trading for testing before using real funds.

---

## 🔍 Troubleshooting

**Problem**: "Invalid credentials" error when saving config  
**Solution**: Verify API key, secret, and passphrase are correct. Check OKX account settings.

**Problem**: Trading session won't start  
**Solution**: Check API container logs: `docker compose -f infra/compose/docker-compose.dev.yml logs api`

**Problem**: PnL not updating  
**Solution**: Ensure server is running and check browser console for polling errors

---

## 📚 Additional Resources

- [OKX API Documentation](https://www.okx.com/docs-v5/en/)
- [Cryptography Library Docs](https://cryptography.io/)
