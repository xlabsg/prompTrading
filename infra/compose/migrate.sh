#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

COMPOSE="${COMPOSE_CMD:-docker compose}"

echo "==> seeding builtin templates"
$COMPOSE exec -T api python /app/services/api/scripts/seed_builtin_templates.py || true
