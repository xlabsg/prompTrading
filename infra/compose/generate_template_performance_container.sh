#!/bin/bash
# 生成 Templates 性能数据（容器环境）

COMPOSE_FILE="docker-compose.prod.yml"
if [ "$1" = "--dev" ]; then
    COMPOSE_FILE="docker-compose.dev.yml"
fi

echo "📊 开始生成模板性能数据..."

docker compose -f "$COMPOSE_FILE" exec -T api python -c "
import sys
sys.path.insert(0, '/app')

from control_plane.db import create_db_engine, create_session_factory, session_scope
from control_plane.models import StrategyTemplate
from app.services.template_performance_generator import generate_template_performance_data
from app.settings import settings

engine = create_db_engine(settings.db_url)
with session_scope(create_session_factory(engine)) as db:
    templates = db.query(StrategyTemplate).filter(
        StrategyTemplate.is_public == True
    ).all()

    if not templates:
        print('⚠️  警告：没有找到公开模板')
        print('请先运行初始化脚本')
    else:
        print(f'找到 {len(templates)} 个公开模板\\n')

        for i, tmpl in enumerate(templates, 1):
            print(f'[{i}/{len(templates)}] {tmpl.name}')
            try:
                generate_template_performance_data(db, tmpl.id)
                print('  ✅ 完成')
            except Exception as e:
                print(f'  ⚠️  失败: {e}')

        print('\\n✅ 所有模板性能数据生成完成！')
"
