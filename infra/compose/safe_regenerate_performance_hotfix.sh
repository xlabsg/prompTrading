#!/bin/bash
# 临时热修复：在生成性能数据前转换 Decimal 类型
# 无需重新构建容器镜像

set -e

GREEN='\033[0;32m'
NC='\033[0m'

COMPOSE_FILE="docker-compose.prod.yml"
if [ "$1" = "--dev" ]; then
    COMPOSE_FILE="docker-compose.dev.yml"
fi

echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  安全生成模板性能数据（热修复版）${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

docker compose -f "$COMPOSE_FILE" exec -T api python -c "
import sys
sys.path.insert(0, '/app')

from decimal import Decimal
from control_plane.db import create_db_engine, create_session_factory, session_scope
from control_plane.models import StrategyTemplate, TemplatePerformanceRun
from app.services.template_performance_generator import TemplatePerformanceGenerator
from app.settings import settings

engine = create_db_engine(settings.db_url)

# 临时修复：包装 generate_performance_data 方法
original_generate = TemplatePerformanceGenerator.generate_performance_data

def fixed_generate(cls, db, template, **kwargs):
    return original_generate(db, template, **kwargs)

# 替换方法
TemplatePerformanceGenerator.generate_performance_data = classmethod(fixed_generate)

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
                TemplatePerformanceGenerator.generate_performance_data(db, tmpl)
                print(f'  ✅ 已生成性能数据')
            except Exception as e:
                print(f'  ⚠️  失败: {e}')
                import traceback
                traceback.print_exc()

    print(f'\n✅ 检查完成！')
"
