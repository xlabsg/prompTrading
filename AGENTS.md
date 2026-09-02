# Repository Guidelines

## RULES
focus on coding readabiliy and performance first
do not write code at begining, we can talk first until I let you write code
consider use “First principle” to thinking
no need write README md docs
when modifying worker, sandbox or docker orchestration, must verify with a real container smoke test (Worker -> Docker Agent lifecycle), do not rely solely on in-memory mocks

## Project Structure & Module Organization
- `apps/web`: Vite + React console with Tailwind styling; code lives in `src/` and builds into `dist/`.
- `packages/*`: Reusable Python libraries (`control_plane`, `agent`, `backtest`, `data`, `okx_sdk`) consumed by services and workers via `pip install -e`.
- `services/api`: FastAPI application exposing strategy, backtest, and trading endpoints from `app/`.
- `services/worker`: Background runners and feeds stored under `worker/`.
- `infra/compose`: Docker Compose manifests, `.env`, and `update.sh` helpers that orchestrate containers.

## Build, Test, and Development Commands
- API: `cd services/api && pip install -e '.[test]' && uvicorn app.main:app --reload` for rapid iteration; Compose will start it automatically via `./infra/compose/update.sh`.
- Web: `cd apps/web && npm install && npm run dev` launches Vite on `localhost:5173`; `npm run build` outputs production assets.
- Worker: `cd services/worker && pip install -e . && python worker/main.py` to replay tasks locally.
- Full stack: `./infra/compose/update.sh` rebuilds images, applies migrations, and restarts containers.
- Tests: `cd packages/okx_sdk && pytest -q` for SDK validation; run `services/api/setup_and_test.sh` inside the API container for smoke checks.

## Coding Style & Naming Conventions
- Python: 4-space indentation, type-hinted functions, and descriptive module names (`trading_session_service.py`). Favor dataclasses and enums from `control_plane`, and keep imports sorted (stdlib, third-party, local).
- TypeScript/React: Follow functional component style with PascalCase filenames (`BacktestView.tsx`). Use Tailwind utility classes consistently and keep hooks near their owners under `src/hooks/`. Run `npm run lint` before pushing.
- Config files (`*.env`, YAML) must not embed secrets; document required keys in README or service-specific docs.

## Testing Guidelines
- Prefer pytest for Python packages/services. Store tests beside implementation (e.g., `packages/control_plane/tests/`). Name files `test_<unit>.py` and keep fixtures reusable.
- For the web console, add vitest or Playwright suites under `apps/web/src/__tests__`; snapshot tests should sit next to their components.
- Target coverage of trading-critical paths (strategy eval, order placement, WebSocket broadcasting). When patching these areas, add regression tests or update `services/api/test_okx_setup.py`.
- **Container Smoke Testing**: When modifying Worker orchestration, Docker container parameters (e.g., `read_only`, `tmpfs`, limits), or agent runtime dependencies, always execute a real end-to-end container run (`Worker -> Docker Agent/Backtest`) to verify filesystem permissions and lifecycle in addition to in-memory/mock unit tests.

## Commit & Pull Request Guidelines
- Use Conventional Commit prefixes as seen in history (`feat:`, `fix:`, `refactor:`). Scope tags (`feat(api): ...`) help reviewers trace ownership.
- Each PR must describe motivation, testing evidence (`pytest`, `npm run lint`, Compose logs), and link to issues or runbooks. Include screenshots or terminal captures for UI/backtest changes.
- Keep PRs atomic: isolated backend, frontend, or infra adjustments unless the change requires synchronized updates. Update docs (`README.md`, `LIVE_TRADING_SETUP.md`) whenever workflows change.
