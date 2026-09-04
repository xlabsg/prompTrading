#!/bin/bash
# 安全地生成模板性能数据（避免重复）
# 只为没有性能数据的模板生成

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

COMPOSE_FILE="docker-compose.prod.yml"
if [ "$1" = "--dev" ]; then
    COMPOSE_FILE="docker-compose.dev.yml"
fi

echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  安全生成模板性能数据${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

docker compose -f "$COMPOSE_FILE" exec -T api python -c "
import sys
sys.path.insert(0, '/app')

from control_plane.db import create_db_engine, create_session_factory, session_scope
from control_plane.models import StrategyTemplate, TemplatePerformanceRun
from app.services.template_performance_generator import generate_template_performance_data
from app.settings import settings

engine = create_db_engine(settings.db_url)

with session_scope(create_session_factory(engine)) as db:
    templates = db.query(StrategyTemplate).filter(
        StrategyTemplate.is_public == True
    ).all()

    print(f'找到 {len(templates)} 个公开模板\n')

    for i, tmpl in enumerate(templates, 1):
        # 检查是否已有性能数据
        existing_runs = db.query(TemplatePerformanceRun).filter(
            TemplatePerformanceRun.template_id == tmpl.id
        ).count()

        if existing_runs > 0:
            print(f'[{i}/{len(templates)}] {tmpl.name}')
            print(f'  ⏭️  已有 {existing_runs} 条性能数据，跳过')
        else:
            print(f'[{i}/{len(templates)}] {tmpl.name}')
            try:
                generate_template_performance_data(db, tmpl.id)
                print(f'  ✅ 已生成性能数据')
            except Exception as e:
                print(f'  ⚠️  失败: {e}')

    print(f'\n✅ 检查完成！')
"
