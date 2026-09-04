# CLAUDE.md

This file provides guidance to AI coding agents (Claude Code, Codex, Cursor) when
working with code in this repository. `AGENTS.md` is a symlink to this file — edit
this one.

## Working Rules

- Readability and performance come first.
- Do not start by writing code. Talk through the approach until told to write it.
- Think from first principles.
- Do not add new README-style docs on your own initiative; keep the existing docs
  (`README.md`, `LIVE_TRADING_SETUP.md`) up to date when a workflow changes.
- When modifying the worker, Docker orchestration, or agent runtime dependencies,
  verify with a real container smoke test (Worker -> Docker agent/backtest
  lifecycle). In-memory mocks alone are not evidence.

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
│   ├── agent/             # Strategy domain layer for the Tau agent (container entry: agent.runner_v2)
│   ├── backtest/          # Backtesting engine (vectorized) + artifacts
│   ├── data/              # Market data providers + shared OHLCV cache
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
pytest services/api/tests -q
```

### Package Tests
Package tests need no services running, only the packages on `PYTHONPATH`:
```bash
PYTHONPATH="packages/agent:packages/backtest:packages/data" \
  pytest packages/agent/tests packages/data/tests -q
```
`packages/agent/tests/test_tau_ext.py` needs `tau-ai` installed and skips without it.

### Selective Service Updates
```bash
./update.sh api worker          # Update specific services
./update.sh --no-build          # Skip building
./update.sh --no-pull           # Skip pulling remote images
```

## Architecture

### Data Flow
```
Frontend (React) → API (FastAPI) → SQLite (default) / PostgreSQL (optional)
                         ↓
                   Worker Service → Ephemeral Docker Containers
                         ↓                (agent, backtest)
                   OKX Exchange (live trading)
```

### Key Patterns
- **Job Processing**: Worker-based async job execution with RPC dispatch for strategy generation and backtesting
- **WebSocket**: Real-time updates for trading status, positions, and logs
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
**The coding agent is [Tau](https://github.com/huggingface/tau) (`tau-ai`), run as
a child process.** This repo owns the domain layer around it, not the agent loop.
Do not reintroduce a hand-written loop, LLM client, or file-edit tool.

- Container entry point: `agent.runner_v2` (`python -m agent.runner_v2`), spawned
  by the worker for `generate_strategy` / `generate_and_backtest` / `refine_strategy`.
  The API also drives a session in-process for chat refine and `/generate_overview`.
- `agent/tau_driver.py` speaks Tau's JSONL RPC (`tau --mode rpc`) from synchronous
  code. It depends on nothing beyond the standard library.
- `agent/tau_ext.py` is the Tau extension that registers `backtest` and
  `task_done` and injects the strategy protocol into the system prompt.
- Tau supplies `read` / `write` / `edit` / `bash`, context compaction, session
  persistence and the provider layer. `edit` is exact-match: `oldText` must occur
  exactly once, and a failed match is an error rather than a fuzzy fallback.
- The agent works inside `versions/<version_id>/`, not the live `strategy/` dir.
  `runner_v2` seeds that workspace, then publishes to `strategy/` only on success.

**Completion is decided by the driver, not the model.** Tau's loop ends whenever
the model stops calling tools, and `AgentToolResult.terminate` is declared but
never read in tau 0.4.1. So `runner_v2._workspace_problems()` validates the
workspace after `agent_settled` and sends a follow-up prompt when something is
missing. `task_done` is a protocol gate that reports problems early; it cannot
stop the loop.

**Wait for `agent_settled`, never `agent_end`.** `agent_end` carries `will_retry`
and fires again for every automatic retry.

**The turn budget is enforced by the driver too.** `AgentHarnessConfig.max_turns`
exists in tau 0.4.1, but `tau_coding.session` never sets it and neither the CLI
nor the RPC frontend exposes it, so `AGENT_MAX_STEPS` is applied in
`tau_driver._consume_until_settled`: on reaching the cap it sends `abort`, keeps
reading to `agent_settled`, and then refuses to spend a follow-up. Unset (the
default) means no cap, and the container wall clock is the only bound.

**Container timeouts must stay above the driver's own.** The worker kills an
agent container after `AGENT_IDLE_TIMEOUT_S` of silence (420s, above the driver's
`AGENT_TAU_EVENT_TIMEOUT_S` of 300s) or `AGENT_JOB_TIMEOUT_S` of wall clock
(1800s). Both sit above the driver so a stalled session fails with a real
`tau_event_timeout` message instead of an opaque `exit 124`, and
`runner_v2` passes `progress_callback=_print_progress` so tool activity keeps the
idle timer alive during a working session.

**The backtest tool runs in a subprocess** (`agent/backtest_subprocess.py`).
`run_agent_backtest` installs a process-wide network guard whose allowlist holds
only the exchange host, so running it in-process would block the agent's own next
call to the model provider.

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
`AGENT_BACKTEST_SCORE_KEY`, `AGENT_BACKTEST_BARS`, `AGENT_MAX_STEPS`,
`AGENT_TAU_EVENT_TIMEOUT_S`, `AGENT_TAU_MAX_FOLLOW_UPS`.
`AGENT_MAX_TOKENS` is no longer consulted: Tau sizes compaction from the model's
context window.
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
- SQLite (default) / PostgreSQL (optional)
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

## Coding Style

- **Python**: 4-space indentation, type-hinted functions, descriptive module names
  (`trading_session_service.py`). Prefer dataclasses and the enums in
  `control_plane`. Keep imports sorted (stdlib, third-party, local). `ruff` is the
  linter/formatter.
- **TypeScript/React**: functional components, PascalCase filenames
  (`BacktestView.tsx`), Tailwind utility classes, hooks under `src/hooks/` near
  their owners. Run `npm run lint` before pushing.
- **Config** (`*.env`, YAML): never embed secrets. Document required keys in the
  service docs, not inline.

## Testing Conventions

- pytest for Python packages and services. Tests live beside the implementation
  (e.g. `packages/control_plane/tests/`), named `test_<unit>.py`, with reusable
  fixtures.
- Web console tests (vitest or Playwright) go under `apps/web/src/__tests__`;
  snapshot tests sit next to their components.
- Prioritise coverage of trading-critical paths: strategy evaluation, order
  placement, WebSocket broadcasting. Add a regression test when patching these.
- Container smoke tests are required for the changes listed under Working Rules —
  see also `services/api/setup_and_test.sh` for in-container API smoke checks.

## Commits & Pull Requests

- Conventional Commit prefixes, with a scope where it helps: `feat(api): ...`,
  `fix:`, `refactor:`, `chore:`, `docs:`. English.
- A PR states its motivation and its testing evidence (`pytest`, `npm run lint`,
  Compose logs), and links the issue or runbook. Include screenshots or terminal
  captures for UI and backtest changes.
- Keep PRs atomic — backend, frontend, or infra separately, unless the change has
  to land in sync.
