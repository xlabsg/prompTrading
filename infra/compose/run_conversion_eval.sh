#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-core}"
shift || true

COMPOSE_FILE="infra/compose/docker-compose.e2e.yml"
PROJECT_NAME="${EVAL_PROJECT_NAME:-ai_strategy_eval}"
CONSUMERS="${E2E_WORKER_CONSUMERS:-3}"
export COMPOSE_PROJECT_NAME="$PROJECT_NAME"

if [[ "$MODE" != "core" && "$MODE" != "extended" ]]; then
  echo "Usage: $0 [core|extended] [conversion_eval.py args...]" >&2
  exit 2
fi

# Load env vars from the shared compose .env if present (where you keep LLM keys).
ENV_FILE="${E2E_ENV_FILE:-infra/compose/.env}"
DC_ENV_ARGS=()
if [[ -f "$ENV_FILE" ]]; then
  DC_ENV_ARGS=(--env-file "$ENV_FILE")
  echo "[eval] Using env file: $ENV_FILE"
fi

dc() {
  docker compose "${DC_ENV_ARGS[@]}" -p "$PROJECT_NAME" -f "$COMPOSE_FILE" "$@"
}

cleanup() {
  local code=$?
  if [[ $code -ne 0 ]]; then
    echo "[eval] FAILED (exit=$code). Dumping logs..." >&2
    dc logs --no-color --timestamps --tail=800 || true
  fi
  echo "[eval] Tearing down environment..." >&2
  local net="${PROJECT_NAME}_default"
  local ws_vol="${PROJECT_NAME}_workspaces_e2e"
  local ids=""
  ids="$(docker ps -a --filter "network=$net" --format '{{.ID}} {{.Names}}' | awk '$2 ~ /^(agent|backtest|dev|repo-sync)-/ {print $1}' || true)"
  if [[ -z "$ids" ]]; then
    ids="$(docker ps -a --filter "volume=$ws_vol" --format '{{.ID}} {{.Names}}' | awk '$2 ~ /^(agent|backtest|dev|repo-sync)-/ {print $1}' || true)"
  fi
  if [[ -n "$ids" ]]; then
    echo "[eval] Removing stray job containers..." >&2
    # shellcheck disable=SC2086
    docker rm -f $ids >/dev/null 2>&1 || true
  fi
  dc down -v --remove-orphans || true
  exit "$code"
}
trap cleanup EXIT

echo "[eval] Bringing up stack (mode=$MODE, consumers=$CONSUMERS)..."
dc up -d --build --remove-orphans postgres redis api agent-image backtest-image dev-image worker-scheduler
dc up -d --build --remove-orphans --scale worker-consumer="$CONSUMERS" worker-consumer

echo "[eval] Waiting for API health..."
ok=0
for _ in {1..60}; do
  if dc exec -T api python -c "import urllib.request; r=urllib.request.urlopen('http://localhost:8000/healthz', timeout=2); raise SystemExit(0 if 200 <= r.status < 300 else 1)" >/dev/null 2>&1; then
    ok=1
    break
  fi
  sleep 2
done
if [[ "$ok" != "1" ]]; then
  echo "[eval] API health check failed" >&2
  exit 1
fi

echo "[eval] Clearing Redis queue (best-effort)..."
dc exec -T redis redis-cli DEL ai_strategy_jobs >/dev/null || true

ART_DIR="${EVAL_ARTIFACTS_DIR:-.e2e_artifacts}"
mkdir -p "$ART_DIR"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
REPORT_PATH="/artifacts/conversion_eval_${MODE}_${TS}.json"
FAIL_PATH="/artifacts/conversion_eval_${MODE}_${TS}_failures.json"

DEFAULT_ARGS=()
if [[ "$MODE" == "core" ]]; then
  DEFAULT_ARGS=(--from-trending "${EVAL_FROM_TRENDING:-2}" --skip-backtest)
else
  DEFAULT_ARGS=(--from-trending "${EVAL_FROM_TRENDING:-2}")
fi

ARGS=("$@")
if [[ "${#ARGS[@]}" -eq 0 ]]; then
  ARGS=("${DEFAULT_ARGS[@]}")
fi

echo "[eval] Running conversion_eval.py ${ARGS[*]}"
dc run --rm -T --no-deps --build \
  --entrypoint python \
  -v "$(pwd)/${ART_DIR}:/artifacts" \
  e2e-runner \
  /app/services/api/scripts/conversion_eval.py \
  --api-base-url "${E2E_API_BASE_URL:-http://api:8000}" \
  --out "$REPORT_PATH" \
  --out-failures "$FAIL_PATH" \
  "${ARGS[@]}"

if [[ -f "${ART_DIR}/$(basename "$REPORT_PATH")" ]]; then
  echo "[eval] Report written to: ${ART_DIR}/$(basename "$REPORT_PATH")"
  ln -sf "$(basename "$REPORT_PATH")" "${ART_DIR}/conversion_eval_${MODE}_latest.json" || true
else
  echo "[eval] WARNING: report file not found after run: ${ART_DIR}/$(basename "$REPORT_PATH")" >&2
fi
if [[ -f "${ART_DIR}/$(basename "$FAIL_PATH")" ]]; then
  echo "[eval] Failures written to: ${ART_DIR}/$(basename "$FAIL_PATH")"
  ln -sf "$(basename "$FAIL_PATH")" "${ART_DIR}/conversion_eval_${MODE}_latest_failures.json" || true
else
  echo "[eval] WARNING: failures file not found after run: ${ART_DIR}/$(basename "$FAIL_PATH")" >&2
fi

echo "[eval] PASSED"
