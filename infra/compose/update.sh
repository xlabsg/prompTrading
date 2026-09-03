#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

COMPOSE="${COMPOSE_CMD:-docker compose}"

RUNTIME_SERVICES=(api worker worker-rpc web)
TOOLING_SERVICES=(agent-image backtest-image)

PULL=1
BUILD=1
SERVICES=()

usage() {
  cat <<'EOF'
Usage:
  ./update.sh [options] [service...]

What it does:
  - Pulls remote base images if newer are available
  - Rebuilds local images (api/worker/web + tooling images) with --pull
  - Runs `docker compose up -d` to incrementally recreate only changed containers

Options:
  --all           Update all runtime services (default if no service specified)
  --no-pull       Skip `docker compose pull`
  --no-build      Skip `docker compose build`
  -h, --help      Show this help

Examples:
  ./update.sh
  ./update.sh api worker
  ./update.sh --no-build
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --all)
      SERVICES=()
      shift
      ;;
    --no-pull)
      PULL=0
      shift
      ;;
    --no-build)
      BUILD=0
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --)
      shift
      SERVICES+=("$@")
      break
      ;;
    *)
      SERVICES+=("$1")
      shift
      ;;
  esac
done

if [[ ${#SERVICES[@]} -eq 0 ]]; then
  SERVICES=("${RUNTIME_SERVICES[@]}")
fi

echo "==> compose dir: $SCRIPT_DIR"
echo "==> services: ${SERVICES[*]}"

echo "==> resolving services against compose file"
AVAILABLE_SERVICES=()
while IFS= read -r svc; do
  [[ -n "$svc" ]] && AVAILABLE_SERVICES+=("$svc")
done < <($COMPOSE config --services)

filter_services() {
  local arr_name="$1"
  local -a _in=()
  local -a _out=()
  eval "_in=(\"\${${arr_name}[@]}\")"
  for s in "${_in[@]}"; do
    for a in "${AVAILABLE_SERVICES[@]}"; do
      if [[ "$s" == "$a" ]]; then
        _out+=("$s")
        break
      fi
    done
  done
  eval "${arr_name}=(\"\${_out[@]}\")"
}

filter_services SERVICES
filter_services TOOLING_SERVICES

if [[ ${#SERVICES[@]} -eq 0 ]]; then
  echo "No matching runtime services found in compose config."
  exit 1
fi

echo "==> runtime services: ${SERVICES[*]}"
echo "==> tooling services: ${TOOLING_SERVICES[*]}"

if [[ "$PULL" -eq 1 ]]; then
  echo "==> pulling remote images (best-effort)"
  if $COMPOSE pull --help 2>&1 | grep -q -- '--ignore-buildable'; then
    $COMPOSE pull --ignore-buildable "${SERVICES[@]}"
  else
    # Older compose versions may not support --ignore-buildable.
    $COMPOSE pull "${SERVICES[@]}" || true
  fi
fi

if [[ "$BUILD" -eq 1 ]]; then
  echo "==> building local images (with base image refresh)"
  $COMPOSE build --pull "${SERVICES[@]}"
  # These images are used by the worker for ephemeral sandboxes.
  $COMPOSE build --pull "${TOOLING_SERVICES[@]}"
fi

echo "==> applying changes (incremental)"
$COMPOSE up -d --remove-orphans "${SERVICES[@]}"

if printf '%s\n' "${SERVICES[@]}" | grep -qx 'api'; then
  echo "==> seeding builtin templates (best-effort)"
  $COMPOSE exec -T api python /app/services/api/scripts/seed_builtin_templates.py || true
fi

echo "==> status"
$COMPOSE ps
