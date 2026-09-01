# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI-powered algorithmic trading strategy platform. Combines LLM-assisted strategy generation, backtesting, and live trading (OKX exchange). Monorepo architecture with React frontend, FastAPI backend, and Docker-based infrastructure.

## Repository Structure

```
stratsmith/
├── apps/web/              # React/Vite SPA (TypeScript)
├── services/
│   ├── api/               # FastAPI backend
│   └── worker/            # Background job processor (spawns Docker containers)
├── packages/
│   ├── control_plane/     # Shared DB models, enums, schemas (SQLAlchemy)
│   ├── risk_engine/       # Trading engine risk control & order execution
│   ├── strategy_sdk/      # Strategy authoring SDK (for strategy developers)
│   ├── okx_sdk/           # OKX Exchange REST API client
│   ├── agent/             # Strategy generation agent
│   ├── backtest/          # Backtesting engine
│   └── data/              # Data utilities
└── infra/
    ├── compose/           # Docker Compose configs
    └── images/            # Docker images (agent, backtest, dev)
```

## Development Commands

### Start Development Environment
```bash
cd infra/compose
./update.sh                     # Build and start all services
```

### Service URLs (Development)
- Frontend: http://localhost:3000
- API: http://localhost:8000
- API Docs: http://localhost:8000/docs

### Frontend (apps/web)
```bash
# Inside web container or locally
npm run dev      # Start dev server with HMR
npm run build    # Build for production
npm run lint     # Run ESLint
```

### API Testing
```bash
docker compose -f infra/compose/docker-compose.dev.yml exec api bash
python test_okx_setup.py        # Test OKX SDK setup
```

### Selective Service Updates
```bash
./update.sh api worker          # Update specific services
./update.sh --no-build          # Skip building
./update.sh --no-pull           # Skip pulling remote images
```

## Architecture

### Data Flow
```
Frontend (React) → API (FastAPI) → PostgreSQL/Redis
                         ↓
                   Worker Service → Ephemeral Docker Containers
                         ↓                (agent, backtest)
                   OKX Exchange (live trading)
```

### Key Patterns
- **Job Queue**: Redis-backed async job processing for strategy generation, backtesting, and trading
- **WebSocket**: Real-time updates for trading status, positions, PnL via Redis pub/sub
- **Encrypted Storage**: API credentials encrypted with Fernet (cryptography library)
- **Ephemeral Containers**: Worker spawns isolated containers for strategy execution

### Trading Engine (`services/api/app/trading_engine/`)
- `manager.py`: Session lifecycle and orchestration
- `executor.py`: Order placement and execution
- `monitor.py`: Real-time position/PnL tracking
- **Enhanced versions** (Risk Engine integrated):
  - `enhanced_executor.py`: Adds risk validation, TP/SL calculation
  - `enhanced_monitor.py`: Adds trailing stop loss, PnL tracking
  - `enhanced_manager.py`: Adds reconciliation mechanism
  - `sdk_config.py`: Converts database config to Risk Engine config

### Risk Engine (`packages/risk_engine/`)
**Purpose**: Trading engine internal risk management and order execution framework

**Key Features**:
- Invasive risk control (9 validation checks)
- Trailing stop loss (profit-based activation)
- Dynamic TP/SL (support/resistance + ATR)
- Reconciliation (sync with exchange)
- Snowflake ID generation (unique order IDs)

**Documentation** (for AI assistants):
- **Read `SDK_QUICK_REFERENCE.md` first** - Quick lookup and common patterns
- `TRADING_SDK_API.md` - Complete API reference (~1200 lines)
- `README.md` - Feature overview and examples
- `INTEGRATION_GUIDE.md` - Integration steps
- `DESIGN.md` - Architecture and design decisions

**Integration Points**:
- Backend: `enhanced_executor.py`, `enhanced_monitor.py`, `enhanced_manager.py`
- Database: `migrations/add_trading_sdk_fields.sql`
- API: `routers/trading.py` (exposes risk control fields)
- Frontend: `LiveTradingView.tsx` (configuration UI)

### Strategy SDK (`packages/strategy_sdk/`)
**Purpose**: Strategy authoring SDK for strategy developers

**Key Features**:
- `Broker` Protocol - Strategy expresses trading intent (set_target_allocation, market_order)
- `LiveStrategy` Protocol - Strategy lifecycle hooks (initialize, on_bar, on_error)
- `Bar`, `StrategyContext` - Data structures for strategy execution

### Database Models (`packages/control_plane/control_plane/models.py`)
Core entities: Strategy, StrategyVersion, BacktestRun, Job, TradingConfig, TradingSession, Order, Position, TradingLog

### Status Enums (`packages/control_plane/control_plane/enums.py`)
JobStatus, TradingSessionStatus, OrderStatus, PositionStatus, etc.

## Tech Stack

### Frontend
- React 18, Vite, TypeScript
- TanStack Query (server state)
- Tailwind CSS, Radix UI
- React Router, Recharts

### Backend
- FastAPI, Uvicorn
- SQLAlchemy 2.0 (async)
- PostgreSQL 16, Redis 7
- Pydantic 2.x

### Infrastructure
- Docker Compose (dev: no Traefik, prod: with Traefik)
- Python 3.13, Node 20

## Environment Variables

Required in `infra/compose/.env`:
- `TRADING_API_ENCRYPTION_KEY`: Fernet key for encrypting trading credentials
- `LLM_API_KEY` / `OPENAI_API_KEY` / `DEEPSEEK_API_KEY`: For strategy generation

## Live Trading Setup

See `LIVE_TRADING_SETUP.md` for OKX integration details. Key points:
- Only enable trading permissions on OKX API key (never withdrawal)
- Use OKX demo trading (https://www.okx.com/demo-trading) for testing
- Generate encryption key: `python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
