# CLAUDE.md

This file provides guidance to AI coding agents (Claude Code, Codex, Cursor) when
working with code in this repository. `AGENTS.md` is a symlink to this file — edit
this one.

## Working Rules

- **Approach by task complexity**:
  - For complex architectural changes, large refactors, or ambiguous requests: explain the proposed approach or create a plan first before making extensive modifications.
  - For well-specified tasks, localized bug fixes, and direct instructions: proceed autonomously with minimal friction, surgical edits, and immediate verification.
- **Surgical edits & minimal surface area**: Prefer targeted modifications over wholesale rewrites. Do not refactor unrelated code or remove working logic unless explicitly requested.
- **Strict documentation discipline**: Do not add new README-style docs on your own initiative; keep the existing docs (`README.md`, `LIVE_TRADING_SETUP.md`) up to date when workflows change.
- **Real container smoke testing**: When modifying the worker, Docker orchestration, or agent runtime dependencies, verify with a real container smoke test (Worker -> Docker agent/backtest lifecycle). In-memory mocks alone are not evidence.
- **Strict frontend i18n parity**: All frontend user-facing strings must use i18n (`useTranslation` / `t`) with keys declared in both `zh.ts` and `en.ts`. Never hardcode user-facing text in UI components.
- **Verification before completion**: Always verify changes using relevant automated checks (`npm run lint`, `npm run typecheck` in `apps/web`; `ruff check`, `pytest` in backend/packages).

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
npm run dev        # Start dev server with HMR
npm run build      # Build for production
npm run lint       # Run ESLint
npm run typecheck  # TypeScript check without emit (tsc --noEmit)
npm run e2e        # Playwright UI E2E (needs the dev Compose stack + LLM key)
npm run e2e:ui     # Playwright UI mode
```

### Backend & API Testing
```bash
# Code formatting & linting check
ruff check .

# API tests inside dev container
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
Endpoints are split by domain and registered in `app/main.py`:
- **Strategy lifecycle**: `strategies.py` (CRUD, chat, generate, refine, versions), `strategies_import.py` (TradingView / PineScript imports), `strategy_members.py`, `strategy_accounts.py` (exchange accounts, signals, trades), `strategy_workspace.py` (workspace file inspection, compare, git diff, `/overview`, `/params-schema`).
- **Execution & trading**: `trading.py` (live trading sessions, orders, positions, risk settings), `internal_trading.py`, `backtests.py` (backtest runs, metrics, equity curve history).
- **Templates & market**: `templates.py`, `template_backtests.py`, `template_performance.py`, `templates_admin.py`, `markets.py` (available tickers/pairs), `trending.py` (scraped TradingView strategies).
- **Platform & infra**: `auth.py` (JWT tokens, Google/GitHub OAuth), `billing.py` (Stripe subscriptions), `portfolio.py`, `repos.py`, `jobs.py`, `admin_ops.py`, `ws.py` (real-time WebSocket broadcasting).

### Strategy Workspace & System Files Conventions
Inside each strategy directory (`workspaces/<strategy_id>/strategy/` or `versions/<version_id>/`):
- **User-facing strategy files**: `strategy.py`, `strategy_live.py`, `strategy_spec.yaml`, `strategy_protocol.json`.
- **Strategy metadata & parameters**: `strategy_meta.json`, `params_schema.json`. Parameters and schema definitions are exposed to the UI via `GET /strategies/{id}/params-schema`.
- **System & generated files**: `overview.md`, `backtest_iterations.json`.
  - System files are hidden from `/strategies/{id}/files` to prevent accidental manual edits in the code editor.
  - Strategy overview markdown is served via `GET /strategies/{id}/overview` and automatically sanitized with `agent.mermaid_sanitizer.sanitize_overview_markdown` to prevent flowchart rendering syntax errors (e.g. unquoted special characters in node labels).

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
- `BacktestBudget` — caps runs per session (`AGENT_BACKTEST_MAX_RUNS`, default 1)
  and reports stalling when the score stops improving.

Per-run results land in `versions/<id>/backtest_iterations.json` and in
`StrategyVersion.llm_meta`. Worker reuses in-loop agent backtest artifacts during
`generate_and_backtest`, and strategy generation automatically triggers an official
backtest on completion.

Tuning env vars: `AGENT_BACKTEST_MAX_RUNS` (default 1), `AGENT_BACKTEST_STALL_LIMIT`,
`AGENT_BACKTEST_SCORE_KEY`, `AGENT_BACKTEST_BARS`, `AGENT_MAX_STEPS`,
`AGENT_TAU_EVENT_TIMEOUT_S`, `AGENT_TAU_MAX_FOLLOW_UPS`.
`AGENT_MAX_TOKENS` is no longer consulted: Tau sizes compaction from the model's
context window.
The worker points the agent at the job's own dataset when the job has one.

**Supported Providers & Dynamic Model Registration** (`agent/tau_config.py`):
Tau supports Anthropic (`ANTHROPIC_API_KEY`), DeepSeek (`DEEPSEEK_API_KEY`),
Google Gemini (`GEMINI_API_KEY`), OpenAI (`OPENAI_API_KEY`), or custom OpenAI-compatible
gateways (`LLM_BASE_URL`). When using newer models not present in Tau's static catalog
(e.g. `claude-3-7-sonnet-*`, `gemini-2.5-*`), `tau_config.ensure_catalog_entry` dynamically
upserts model configurations into the local Tau provider settings at runtime.

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

### Builtin Template Code (`control_plane/templates.py`)
`TEMPLATE_STRATEGIES` is the single source of `generate_signals` code for the
builtin templates, keyed by template id. Both consumers read it: fork/instantiate
via `get_template_strategy_code`, and `worker/template_backtest_job.py` by
importing the dict. Do not add a second copy — the worker used to keep its own,
the two drifted, and a shipped template lost the ability to backtest.

The `code_snapshot.module` column on `StrategyTemplate` is inert metadata. It is
never resolved into an import; template code comes from the dict above.

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
- TanStack Query (server state), React Router
- Tailwind CSS, Radix UI, Framer Motion, Sonner
- Lightweight Charts (v5), AntV G6, Recharts, Mermaid
- i18next / react-i18next

### Backend
- FastAPI, Uvicorn
- SQLAlchemy 2.0 (async), Alembic
- SQLite (default) / PostgreSQL (optional), Redis
- Pydantic 2.x
- Tau AI (pinned 0.4.1), Langfuse (optional observability)

### Infrastructure
- Docker Compose (dev & prod)
- Host Nginx (production reverse proxy, optional)
- Python 3.13, Node 20

## Environment Variables

Configured in `infra/compose/.env` (see `infra/compose/.env.example` for full reference):

- **Core Security & Storage**:
  - `TRADING_API_ENCRYPTION_KEY`: Fernet key for encrypting trading credentials at rest.
  - `APP_DB_URL`: SQLite or PostgreSQL database URL (defaults to `sqlite:////workspaces/app.db`).

- **LLM Configuration**:
  - `LLM_PROVIDER`: Provider name (`deepseek`, `anthropic`, `openai`, `google`).
  - `LLM_MODEL`: Model identifier (e.g. `deepseek-chat`, `claude-3-7-sonnet-20250219`, `gemini-2.5-pro`, `gpt-4o`).
  - `LLM_BASE_URL`: Optional custom OpenAI-compatible endpoint.
  - API Keys: `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `DEEPSEEK_API_KEY`, `OPENAI_API_KEY`, or generic fallback `LLM_API_KEY`.
  - `AGENT_BACKTEST_MAX_RUNS`: Max backtest loop iterations for strategy generation (default: `1`).

- **Container Proxy Configuration** (essential if running proxies on the host for exchange/LLM connectivity):
  - `HTTP_PROXY`, `HTTPS_PROXY`: Host-level proxy settings.
  - `CONTAINER_HTTP_PROXY`, `CONTAINER_HTTPS_PROXY`: Injected into Docker containers (e.g. `http://host.docker.internal:7890`).
  - `NO_PROXY`: Proxy bypass list (default: `localhost,127.0.0.1,api,worker,worker-rpc,web`).

- **Observability & Integrations (Optional)**:
  - `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST`: Langfuse prompt and token tracing.
  - `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`, `GOOGLE_OAUTH_REDIRECT_URI`: Google OAuth.
  - `GITHUB_OAUTH_*`, `GITHUB_APP_*`: GitHub sync and OAuth.

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
  their owners. All user-facing strings must use i18n (`t(...)`) with parity in both
  `zh.ts` and `en.ts`. Run `npm run lint` and `npm run typecheck` before pushing.
- **Config** (`*.env`, YAML): never embed secrets. Document required keys in the
  service docs, not inline.

## Testing Conventions

- **A test must be able to fail for the reason it targets.** Assert the behaviour
  the product promises, not whatever the code currently emits. Never weaken, skip,
  or delete an assertion — and never reshape a test around a bug — just to get a
  green run; fix the code, or fix the test's setup. A test that mocks the thing it
  claims to verify, or that cannot fail, is not evidence.
- pytest for Python packages and services. Tests live beside the implementation
  (e.g. `packages/control_plane/tests/`), named `test_<unit>.py`, with reusable
  fixtures.
- UI end-to-end tests live in `apps/web/e2e/` (Playwright) and run with
  `npm run e2e` (or `npm run e2e:ui`). They drive a real browser against the dev
  Compose stack and, for the generation journey, a real agent container + LLM, so
  they are slow and need `infra/compose/.env` keys. Use them for anything that
  only manifests in the browser — view/state transitions, streaming rendering,
  duplicate requests on remount. Component/snapshot tests sit under
  `apps/web/src/__tests__`.
- Prioritise coverage of trading-critical paths: strategy evaluation, order
  placement, WebSocket broadcasting. Add a regression test when patching these.
- Container smoke tests are required for the changes listed under Working Rules —
  see also `services/api/setup_and_test.sh` for in-container API smoke checks.

## Commits & Pull Requests

- Conventional Commit prefixes, with a scope where it helps: `feat(api): ...`,
  `fix:`, `refactor:`, `chore:`, `docs:`. English.
- A PR states its motivation and its testing evidence (`pytest`, `npm run lint`,
  `npm run typecheck`, Compose logs), and links the issue or runbook. Include
  screenshots or terminal captures for UI and backtest changes.
- Keep PRs atomic — backend, frontend, or infra separately, unless the change has
  to land in sync.
