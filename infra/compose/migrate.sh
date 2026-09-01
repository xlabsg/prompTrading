#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

COMPOSE="${COMPOSE_CMD:-docker compose}"

echo "==> running db migrations (best-effort)"
$COMPOSE exec -T api bash -c '
  if [[ -d /app/services/api/migrations ]]; then
    # Convert SQLAlchemy URL format to standard PostgreSQL URL
    PSQL_URL="${APP_DB_URL/postgresql+psycopg/postgresql}"
    for file in /app/services/api/migrations/*.sql; do
      [[ -f "$file" ]] || continue
      echo "[migrate] $file"
      psql "$PSQL_URL" -v ON_ERROR_STOP=1 -f "$file"
    done
  else
    echo "[migrate] migrations directory not found"
  fi
' || true

echo "==> seeding builtin templates (best-effort)"
SQL_PATH="$SCRIPT_DIR/../../services/api/migrations/seed_templates.sql"
if [[ ! -f "$SQL_PATH" ]]; then
  SQL_PATH="$SCRIPT_DIR/../../packages/control_plane/migrations/seed_templates.sql"
fi
if [[ -f "$SQL_PATH" ]]; then
  cat "$SQL_PATH" | $COMPOSE exec -T api bash -c '
    PSQL_URL="${APP_DB_URL/postgresql+psycopg/postgresql}"
    psql "$PSQL_URL" -v ON_ERROR_STOP=1
  ' || true
else
  echo "[seed] seed_templates.sql not found"
fi
