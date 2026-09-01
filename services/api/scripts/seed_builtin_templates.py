#!/usr/bin/env python3
"""
初始化内置策略模板

从 seed_templates.sql 导入内置模板并验证
"""

import os
import sys

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from control_plane.db import create_db_engine, create_session_factory, session_scope
from control_plane.models import StrategyTemplate
from sqlalchemy import text
from app.settings import settings


def seed_templates():
    """执行 seed_templates.sql 并验证"""

    print("📝 开始初始化内置模板...")

    # 读取 SQL 文件
    base_dir = os.path.dirname(__file__)
    candidates = [
        os.path.join(base_dir, '../migrations/seed_templates.sql'),
        os.path.join(base_dir, '../../packages/control_plane/migrations/seed_templates.sql'),
    ]
    sql_path = next((p for p in candidates if os.path.exists(p)), None)

    if not sql_path:
        print("❌ 错误：SQL 文件不存在:")
        for p in candidates:
            print(f"   - {p}")
        return False

    with open(sql_path, 'r') as f:
        sql = f.read()

    # 执行 SQL
    engine = create_db_engine(settings.db_url)

    try:
        with engine.connect() as conn:
            # 分割 SQL 语句并逐个执行
            statements = [s.strip() for s in sql.split(';') if s.strip()]

            for statement in statements:
                if statement:
                    try:
                        conn.execute(text(statement))
                        conn.commit()
                    except Exception as e:
                        print(f"⚠️  警告：执行 SQL 时出错: {e}")
                        # 继续执行其他语句

        # 验证模板是否创建成功
        with session_scope(create_session_factory(engine)) as db:
            template_count = db.query(StrategyTemplate).count()
            featured_count = db.query(StrategyTemplate).filter(
                StrategyTemplate.is_featured == True
            ).count()

            print(f"\n✅ 模板初始化完成！")
            print(f"   - 总模板数: {template_count}")
            print(f"   - 精选模板: {featured_count}")

            if template_count == 0:
                print(f"\n⚠️  警告：没有找到模板，请检查 SQL 文件")
                return False

            # 列出所有模板
            templates = db.query(StrategyTemplate).order_by(
                StrategyTemplate.updated_at.desc()
            ).all()

            print(f"\n📊 已初始化的模板:")
            for tmpl in templates:
                featured = "⭐ " if tmpl.is_featured else "   "
                risk = tmpl.risk_level or "unknown"
                freq = tmpl.trading_frequency or "unknown"
                print(f"   {featured}- {tmpl.name}")
                print(f"      类型: {tmpl.template_type}, 风险: {risk}, 频率: {freq}")

            return True

    except Exception as e:
        print(f"❌ 错误：{e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = seed_templates()
    sys.exit(0 if success else 1)
