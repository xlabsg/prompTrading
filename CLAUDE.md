# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI-powered algorithmic trading strategy platform. Combines LLM-assisted strategy generation, backtesting, and live trading (OKX exchange). Monorepo architecture with React frontend, FastAPI backend, and Docker-based infrastructure.

## Repository Structure

```
prompTrading/
├── apps/web/              # React/Vite SPA (TypeScript)
├── services/
│   ├── api/               # FastAPI backend
│   └── worker/            # Background job processor (spawns Docker containers)
├── packages/
│   # --- MVP core ---
│   ├── control_plane/     # Shared DB models, enums, version factory (SQLAlchemy)
│   ├── agent/             # AutonomousAgent: the coding agent (container entry: agent.runner_v2)
│   ├── backtest/          # Backtesting engine (vectorized) + artifacts
│   ├── data/              # Market data providers + shared OHLCV cache
│   ├── code_editor/       # Fuzzy code matching/editing (single implementation)
│   ├── okx_sdk/           # OKX Exchange REST API client
│   # --- live trading ---
│   ├── risk_engine/       # Risk control, stop loss, reconciliation, order manager
│   ├── live_trading_sdk/  # Strategy authoring SDK (Broker / LiveStrategy protocols)
│   # --- peripheral, not on the MVP path ---
│   ├── strategy_templates/    # Template system (parallel strategy/backtest flow)
│   ├── trending_scraper/      # TradingView trending list scraper
│   ├── tradingview_scraper/   # PineScript import from TradingView URLs
│   └── youtube_processor/     # YouTube import — TEMPORARILY DISABLED, not deleted.
│                              # Kept parked: re-enable by uncommenting the
│                              # install in services/api/Dockerfile and the tab
│                              # in ImportStrategyModal.tsx.
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

### Package Tests
Package tests need no services running, only the packages on `PYTHONPATH`:
```bash
PYTHONPATH="packages/agent:packages/backtest:packages/data:packages/code_editor" \
  pytest packages/agent/tests packages/data/tests -q
```
Known pre-existing failures (unrelated to the packages above):
`packages/agent/agent/tests/test_code_slice.py` (3) and
`packages/code_editor/.../test_editor.py::test_single_candidate_low_threshold` (1).

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

### API Routers (`services/api/app/routers/`)
Strategy endpoints are split by concern: `strategies.py` (CRUD, chat, generate,
refine, versions), `strategy_members.py`, `strategy_accounts.py` (exchange
accounts, signals, trades), `strategy_workspace.py` (file listing, workspace and
git comparison). Each has its own `router` and is registered in `app/main.py`.

### Trading Engine (`services/api/app/trading_engine/`)
- `manager.py`: Session lifecycle and orchestration
- `executor.py`: Order placement and execution
- `monitor.py`: Real-time position/PnL tracking
- `strategy_runner.py`: Runs the strategy and drives `LiveBroker`
- `live_broker.py`: Translates strategy intent into orders
- `sdk_config.py`: Converts database config to Risk Engine config

Risk Engine is integrated directly into `executor.py` / `monitor.py` / `manager.py`
(there are no separate `enhanced_*` modules).

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
- Backend: `executor.py`, `monitor.py`, `manager.py`
- Database: `migrations/add_trading_sdk_fields.sql`
- API: `routers/trading.py` (exposes risk control fields)
- Frontend: `LiveTradingView.tsx` (configuration UI)

### Live Trading SDK (`packages/live_trading_sdk/`)
**Purpose**: Strategy authoring SDK for strategy developers

**Key Features**:
- `Broker` Protocol - Strategy expresses trading intent (set_target_allocation, market_order)
- `LiveStrategy` Protocol - Strategy lifecycle hooks (initialize, on_bar, on_error)
- `Bar`, `StrategyContext` - Data structures for strategy execution

### Coding Agent (`packages/agent/`)
**`AutonomousAgent` is the single coding agent.** Do not add a parallel
generation path; extend this one.

- Container entry point: `agent.runner_v2` (`python -m agent.runner_v2`), spawned
  by the worker for `generate_strategy` / `generate_and_backtest` / `refine_strategy`.
- The agent works inside `versions/<version_id>/`, not the live `strategy/` dir.
  `runner_v2` seeds that workspace, then publishes to `strategy/` only on success.
- Tools: `ls`, `read_file`, `search_files`, `edit_file`, `write_file`, `task_done`,
  plus the `backtest` skill.
- `task_done` is refused unless both `strategy.py` and `overview.md` (with a
  mermaid diagram) exist.
- Text matching lives in `packages/code_editor`; `agent/editor.py` is a thin
  change-spec adapter over it.

**Closed-loop backtesting** (`agent/backtest_tool.py`): the agent backtests its own
code against real cached market data and iterates on the metrics. Two guards keep
the edit->backtest loop terminating, and both matter — an earlier version that ran
on random data with no cap looped forever and had to be disabled:

- `BacktestDataset` — real market data, so a given (code, dataset) pair is deterministic.
- `BacktestBudget` — caps runs per session (`AGENT_BACKTEST_MAX_RUNS`, default 5)
  and reports stalling when the score stops improving.

Per-run results land in `versions/<id>/backtest_iterations.json` and in
`StrategyVersion.llm_meta`.

Tuning env vars: `AGENT_BACKTEST_MAX_RUNS`, `AGENT_BACKTEST_STALL_LIMIT`,
`AGENT_BACKTEST_SCORE_KEY`, `AGENT_BACKTEST_BARS`, `AGENT_MAX_STEPS`, `AGENT_MAX_TOKENS`.
The worker points the agent at the job's own dataset when the job has one.

### Market Data Cache (`packages/data/data/cache.py`)
All three providers (`okx`, `binance`, `us_stock`) fetch through `cached_fetch`, which
stores one parquet per `(exchange, symbol, interval)` on the shared `/workspaces`
volume. Repeating a backtest over an already-fetched range performs no network call,
which is what makes the agent's iteration loop usable.

- Coverage is tracked over *requested* ranges, so an unfetched earlier start refetches.
- Extending forward fetches only the gap and rewrites the trailing (incomplete) bar.
- Env: `MARKET_DATA_CACHE_DIR`, `MARKET_DATA_CACHE_ENABLED`, `MARKET_DATA_CACHE_TTL_S`.

### Creating Strategy Versions
Use `control_plane.versions.create_strategy_version(...)`; never construct
`StrategyVersion` directly. It sets `workspace_path` for you, which the old
two-step pattern (construct with `""`, flush, patch the path) made easy to forget.

- `snapshot=True` copies the current strategy into `versions/<id>/` now.
- `snapshot=False` reserves the directory for a job container to populate.

### Worker Job Dispatch (`services/worker/worker/main.py`)
`JOB_HANDLERS` maps `JobType` -> handler; every handler is normalised to
`(db, rds, docker_client, job)`. Add a job type by adding a `JobType` member and a
`JOB_HANDLERS` entry.

### Database Models (`packages/control_plane/control_plane/models.py`)
Core entities: Strategy, StrategyVersion, BacktestRun, Job, TradingConfig, TradingSession, Order, Position, TradingLog

### Status Enums (`packages/control_plane/control_plane/enums.py`)
JobStatus, TradingSessionStatus, OrderStatus, PositionStatus, etc.

## Packaging

Every package under `packages/` and both services declare dependencies in
`pyproject.toml`; there are no `requirements.txt` files for services (the two
ephemeral task images under `infra/images/` still use one each).

- Service deps: `services/api/pyproject.toml` (test deps under the `test` extra)
  and `services/worker/pyproject.toml`. The Dockerfiles install from these.
- Local packages are installed from `./packages` by the Dockerfiles, never from
  PyPI. Do not list them in a `dependencies` array: names like `data`, `agent`,
  and `backtest` resolve to unrelated PyPI projects.
- A package needing `data.cache` also needs `pyarrow` (the parquet backend).

After changing any dependency or Dockerfile, rebuild and run the image — a
dependency edit that only works locally proves nothing about the image:
```bash
docker build -f services/api/Dockerfile -t prompt-trading-api:verify .
docker run --rm ... prompt-trading-api:verify python -c "import app.main"
```

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
