#!/usr/bin/env python3
"""
为所有模板生成初始性能数据

生成历史回测数据和信号
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from control_plane.db import create_db_engine, create_session_factory, session_scope
from control_plane.models import StrategyTemplate
from app.services.template_performance_generator import generate_template_performance_data
from app.settings import settings


def generate_all_templates_performance():
    """为所有公开模板生成性能数据"""

    print("📊 开始生成模板性能数据...")

    engine = create_db_engine(settings.db_url)

    try:
        with session_scope(create_session_factory(engine)) as db:
            templates = db.query(StrategyTemplate).filter(
                StrategyTemplate.is_public == True
            ).all()

            if not templates:
                print("⚠️  警告：没有找到公开模板")
                print("请先运行: python scripts/seed_builtin_templates.py")
                return False

            print(f"找到 {len(templates)} 个公开模板\n")

            for i, template in enumerate(templates, 1):
                print(f"[{i}/{len(templates)}] 处理: {template.name}")

                try:
                    generate_template_performance_data(db, template.id)
                    print("  ✅ 完成")
                except Exception as e:
                    print(f"  ⚠️  失败: {e}")

            print("\n✅ 所有模板性能数据生成完成！")
            return True

    except Exception as e:
        print(f"❌ 错误：{e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = generate_all_templates_performance()
    sys.exit(0 if success else 1)
