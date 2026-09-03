#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-core}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="${E2E_COMPOSE_FILE:-$SCRIPT_DIR/docker-compose.e2e.yml}"
PROJECT_NAME="${E2E_PROJECT_NAME:-ai_strategy_e2e}"
CONSUMERS="${E2E_WORKER_CONSUMERS:-3}"
export COMPOSE_PROJECT_NAME="$PROJECT_NAME"

if [[ "$MODE" != "core" && "$MODE" != "extended" ]]; then
  echo "Usage: $0 [core|extended]" >&2
  exit 2
fi

# Load env vars from the shared compose .env if present (where you keep LLM keys).
# Compose only auto-loads .env from the current working directory.
ENV_FILE="${E2E_ENV_FILE:-$SCRIPT_DIR/.env}"
declare -a DC_ENV_ARGS=()
if [[ -f "$ENV_FILE" ]]; then
  DC_ENV_ARGS=(--env-file "$ENV_FILE")
  echo "[e2e] Using env file: $ENV_FILE"
fi

# Defaults: core skips real LLM test, extended enables it.
if [[ "$MODE" == "core" ]]; then
  export E2E_REAL_EXTERNAL="${E2E_REAL_EXTERNAL:-0}"
else
  export E2E_REAL_EXTERNAL="${E2E_REAL_EXTERNAL:-1}"
fi

dc() {
  if (( ${#DC_ENV_ARGS[@]} )); then
    docker compose "${DC_ENV_ARGS[@]}" -p "$PROJECT_NAME" -f "$COMPOSE_FILE" "$@"
  else
    docker compose -p "$PROJECT_NAME" -f "$COMPOSE_FILE" "$@"
  fi
}

cleanup() {
  local code=$?
  if [[ $code -ne 0 ]]; then
    echo "[e2e] FAILED (exit=$code). Dumping logs..." >&2
    dc logs --no-color --timestamps --tail=500 || true
  fi
  echo "[e2e] Tearing down environment..." >&2
  # If worker is stopped while job containers are still running, they won't be
  # auto-removed. Kill them so volumes/networks can be removed cleanly.
  local net="${PROJECT_NAME}_default"
  local ws_vol="${PROJECT_NAME}_workspaces_e2e"
  local ids=""
  ids="$(docker ps -a --filter "network=$net" --format '{{.ID}} {{.Names}}' | awk '$2 ~ /^(agent|backtest|dev|repo-sync)-/ {print $1}' || true)"
  if [[ -z "$ids" ]]; then
    ids="$(docker ps -a --filter "volume=$ws_vol" --format '{{.ID}} {{.Names}}' | awk '$2 ~ /^(agent|backtest|dev|repo-sync)-/ {print $1}' || true)"
  fi
  if [[ -n "$ids" ]]; then
    echo "[e2e] Removing stray job containers..." >&2
    # shellcheck disable=SC2086
    docker rm -f $ids >/dev/null 2>&1 || true
  fi
  # Include profile services (web) if started.
  dc --profile ui down -v --remove-orphans || true
  exit "$code"
}
trap cleanup EXIT

echo "[e2e] Bringing up stack (mode=$MODE, consumers=$CONSUMERS)..."

# Build and start infra + workers; runner will be invoked as a one-shot.
dc up -d --build --remove-orphans api agent-image backtest-image dev-image worker-scheduler
dc up -d --build --remove-orphans --scale worker-consumer="$CONSUMERS" worker-consumer

if [[ "$MODE" == "extended" ]]; then
  echo "[e2e] Starting UI (web) service..."
  dc --profile ui up -d --build --remove-orphans web
fi

echo "[e2e] Waiting for API health..."
dc ps api
ok=0
for _ in {1..60}; do
  if dc exec -T api python -c "import urllib.request; r=urllib.request.urlopen('http://localhost:8000/healthz', timeout=2); r.close() and None" >/dev/null 2>&1; then
    ok=1
    break
  fi
  sleep 2
done
if [[ "$ok" != "1" ]]; then
  echo "[e2e] API health check failed" >&2
  exit 1
fi

PYTEST_CMD="pytest -m integration -v"
if [[ "$MODE" == "core" ]]; then
  # Core focuses on generation + backtesting (fallback/no-LLM).
  PYTEST_CMD="pytest -m 'integration and e2e_core' -v"
fi
if [[ "$MODE" == "extended" ]]; then
  # Extended adds real-LLM coverage when configured.
  PYTEST_CMD="pytest -m 'integration and (e2e_core or e2e_extended)' -v"
fi

echo "[e2e] Running tests: $PYTEST_CMD"
dc run --rm -T --no-deps --build e2e-runner "$PYTEST_CMD"

echo "[e2e] PASSED"
