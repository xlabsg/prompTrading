# PrompTrading

Forge algorithmic trading strategies with an LLM, backtest them, and run them live.

PrompTrading turns a plain-language description — *"a moving average crossover on BTC with a 2% trailing stop"* — into executable strategy code, backtests it against historical data, and can promote it to live trading on OKX behind a risk-control layer.

> **Trading real money carries real risk.** This project executes live orders against a real exchange. Nothing here is financial advice, and no strategy it produces is validated for profitability. Start with [OKX demo trading](https://www.okx.com/demo-trading), and never grant your API key withdrawal permissions.

---

## How it works

```
   Web console (React)
           │
           ▼
   API (FastAPI) ──────► PostgreSQL · Redis
           │
           ▼
      Worker ──────► ephemeral Docker containers
           │              ├── agent     (LLM generates strategy code)
           │              └── backtest  (runs the strategy on history)
           ▼
   Risk engine ──────► OKX (live orders)
```

Strategy generation, backtesting, and trading are all queued through Redis and executed asynchronously. The agent and backtest steps run in **throwaway containers**, so generated code never executes in the API process.

## Features

- **Natural-language strategy authoring** — describe the idea, get working Python
- **Iterative refinement** — the agent validates its own output and retries on failure
- **Backtesting** — run a version against historical bars before risking capital
- **Live trading on OKX** — with an invasive risk layer: nine pre-trade validation checks, trailing stops, ATR/support-resistance based TP/SL, and exchange reconciliation
- **Provider-agnostic LLM** — anything OpenAI-compatible (DeepSeek, OpenAI, and others)
- **Observability** — optional Langfuse tracing of prompts, costs, and token usage
- **Encrypted credentials** — exchange API keys are stored Fernet-encrypted at rest

## Quick start

**Requirements:** Docker with Compose, and an API key for an OpenAI-compatible LLM.

```bash
git clone https://github.com/<you>/prompTrading.git
cd prompTrading
cp infra/compose/.env.example infra/compose/.env   # then edit it, see below
./infra/compose/update.sh
```

Generate the encryption key that `.env` requires:

```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Once the stack is up:

| Service   | URL                          |
|-----------|------------------------------|
| Web console | http://localhost:3000      |
| API       | http://localhost:8000        |
| API docs  | http://localhost:8000/docs   |

`update.sh` accepts service names to rebuild selectively (`./update.sh api worker`), and `--no-build` / `--no-pull` to skip steps.

## Configuration

Everything lives in `infra/compose/.env`.

**Required**

| Variable | Purpose |
|---|---|
| `TRADING_API_ENCRYPTION_KEY` | Fernet key encrypting exchange credentials at rest |
| `LLM_API_KEY` | Key for your LLM provider |
| `POSTGRES_PASSWORD` | Database password |

**LLM selection**

| Variable | Purpose |
|---|---|
| `LLM_PROVIDER` | Provider identifier |
| `LLM_BASE_URL` | OpenAI-compatible endpoint |
| `LLM_MODEL` | Model name |
| `LLM_TEMPERATURE` | Sampling temperature |
| `LLM_HTTP_TIMEOUT_S` | Request timeout |
| `LLM_FALLBACK_ON_ERROR` | Emit a template strategy instead of failing the job |

`DEEPSEEK_*` and `OPENAI_API_KEY` are honoured as provider-specific overrides.

**Optional**

- `LANGFUSE_ENABLED`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST` — prompt and cost tracing
- `GITHUB_APP_*`, `GITHUB_OAUTH_*`, `GOOGLE_OAUTH_*` — repository sync and social sign-in
- `APP_PUBLIC_BASE_URL`, `APP_ADMIN_EMAILS`, `APP_ADMIN_API_KEY` — deployment and admin access

For production deployment behind Traefik and TLS, see [`infra/compose/PRODUCTION_DEPLOYMENT.md`](infra/compose/PRODUCTION_DEPLOYMENT.md). For the OKX live-trading walkthrough, see [`LIVE_TRADING_SETUP.md`](LIVE_TRADING_SETUP.md).

## Repository layout

```
apps/web/              React + Vite console (TypeScript)
services/
  api/                 FastAPI backend
  worker/              Job processor; spawns ephemeral containers
packages/
  agent/               Strategy generation agent (entrypoint: agent.runner_v2)
  backtest/            Backtesting engine
  risk_engine/         Pre-trade risk checks, TP/SL, reconciliation
  strategy_sdk/        Protocols strategy authors write against
  okx_sdk/             OKX REST client
  control_plane/       Shared SQLAlchemy models, enums, schemas
  code_editor/         Fuzzy patch application for agent edits
  data/                Data utilities
infra/
  compose/             Docker Compose stacks (dev / prod / e2e)
  images/              Images for the ephemeral agent and backtest containers
```

## Writing a strategy by hand

Strategies implement the protocols in `packages/strategy_sdk/`: a `LiveStrategy` exposes `initialize`, `on_bar`, and `on_error`, and expresses intent through a `Broker` (`set_target_allocation`, `market_order`) rather than placing orders directly. That indirection is what lets the same strategy run under both the backtester and the live risk engine.

## Development

```bash
# Frontend
cd apps/web && npm run dev

# Shell into the API container
docker compose -f infra/compose/docker-compose.dev.yml exec api bash
```

Integration tests live in `services/api/tests/` — see that directory's README.

## Contributing

Issues and pull requests are welcome. Please open an issue before starting substantial work so the approach can be agreed on first.

## License

Apache License 2.0 — see [LICENSE](LICENSE).

This project bundles third-party code; attributions and their licenses are recorded in [NOTICE](NOTICE) and [`THIRD_PARTY_LICENSES/`](THIRD_PARTY_LICENSES).
