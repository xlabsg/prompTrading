#!/bin/bash
# 触发 Trending 抓取（容器环境）

COMPOSE_FILE="docker-compose.prod.yml"
if [ "$1" = "--dev" ]; then
    COMPOSE_FILE="docker-compose.dev.yml"
fi

echo "🔄 触发 Trending 抓取任务..."

docker compose -f "$COMPOSE_FILE" exec -T api python -c "
import sys
import uuid
sys.path.insert(0, '/app')

from control_plane.db import create_db_engine, create_session_factory, session_scope
from control_plane.models import Job
import redis
from control_plane.queue import QUEUE_NAME
from app.settings import settings

# 创建任务
job_id = str(uuid.uuid4())
engine = create_db_engine(settings.db_url)

with session_scope(create_session_factory(engine)) as db:
    job = Job(
        id=job_id,
        type='TRENDING_SCRAPE',
        payload={
            'source_types': ['script'],
            'max_count': 50,
            'auto_backtest': True,
            'auto_backtest_top_n': 10,
        },
        status='queued',
    )
    db.add(job)
    db.commit()

# 添加到队列
rds = redis.Redis.from_url(settings.redis_url, decode_responses=True)
rds.rpush(QUEUE_NAME, job_id)
rds.close()

print(f'✅ Trending 抓取任务已创建: {job_id[:8]}...')
print()
print('任务配置:')
print('  - 最大抓取: 50')
print('  - 最低质量: 30.0')
print('  - 自动回测: True')
print('  - 回测数量: 10')
print()
print('等待 Worker 处理...')
print('预计需要 10-20 分钟完成（包括回测）')
print()
print('查看进度:')
print(f\"  docker compose -f {COMPOSE_FILE} logs -f worker\")
"
