#!/bin/bash
# Trigger Stable5 screening (container environment)

set -euo pipefail

COMPOSE_FILE="docker-compose.yml"
if [ "${1:-}" = "--dev" ]; then
  COMPOSE_FILE="docker-compose.dev.yml"
fi
if [ "${1:-}" = "--prod" ]; then
  COMPOSE_FILE="docker-compose.prod.yml"
fi

LIMIT="${STABLE5_LIMIT:-50}"

echo "Triggering Stable5 screening job (limit=${LIMIT})..."

COMPOSE_FILE_HINT="$COMPOSE_FILE" STABLE5_LIMIT="$LIMIT" docker compose -f "$COMPOSE_FILE" exec -T api python - <<'PY'
import json
import os
import uuid

from control_plane.db import create_db_engine, create_session_factory, session_scope
from control_plane.enums import JobType
from control_plane.models import Job
from control_plane.queue import QUEUE_NAME
from app.settings import settings

import redis

limit = int(os.getenv("STABLE5_LIMIT", "50"))
compose_file = os.getenv("COMPOSE_FILE_HINT", "docker-compose.yml")
job_id = str(uuid.uuid4())

engine = create_db_engine(settings.db_url)
with session_scope(create_session_factory(engine)) as db:
    job = Job(
        id=job_id,
        type=JobType.TEMPLATE_STABLE5_SCREENING.value,
        payload={"limit": limit},
        status="queued",
    )
    db.add(job)
    db.commit()

rds = redis.Redis.from_url(settings.redis_url, decode_responses=True)
rds.rpush(QUEUE_NAME, json.dumps({"job_id": job_id}))

print(f"Stable5 screening job queued: {job_id}")
print("Watch worker logs:")
print(f"  docker compose -f infra/compose/{compose_file} logs -f worker")
PY
