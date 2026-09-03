import os
import tempfile
from sqlalchemy import select

from control_plane.db import create_db_engine, create_session_factory, session_scope
from control_plane.models import Base, Strategy, StrategyMember, StrategyTemplate, StrategyVersion, User
from control_plane.enums import StrategyRole, StrategyTemplateType
from control_plane.templates import instantiate_strategy_from_template


def test_template_fork_domain_and_workspace():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        workspaces_dir = os.path.join(tmpdir, "workspaces")
        engine = create_db_engine(f"sqlite:///{db_path}")
        session_factory = create_session_factory(engine)
        Base.metadata.create_all(engine)

        with session_scope(session_factory) as db:
            user = User(id="usr_fork_tester", email="fork@test.com", name="Fork Tester")
            db.add(user)

            template = StrategyTemplate(
                id="tmpl-divergence",
                name="Divergence Trend",
                template_type=StrategyTemplateType.BUILTIN,
                description="Divergence strategy description",
                prompt="Divergence trading logic",
                config_snapshot={"ema_fast_window": 15, "ema_slow_window": 45},
                subscriber_count=0,
                is_public=True,
            )
            db.add(template)
            db.flush()

            # Simulate fork operation
            strategy_id = "strat-forked-123"
            version_id = "ver-forked-456"

            strategy = Strategy(
                id=strategy_id,
                name="My Divergence Bot",
                description=template.description,
                chat_status="done",
            )
            db.add(strategy)

            member = StrategyMember(
                strategy_id=strategy_id,
                user_id=user.id,
                role=StrategyRole.ADMIN,
            )
            db.add(member)

            version = StrategyVersion(
                id=version_id,
                strategy_id=strategy_id,
                version=1,
                workspace_path=f"versions/{version_id}/",
                prompt=template.prompt,
                llm_meta={"source": "template_fork", "template_id": template.id},
            )
            db.add(version)

            paths = instantiate_strategy_from_template(
                workspaces_dir=workspaces_dir,
                strategy_id=strategy_id,
                version_id=version_id,
                template=template,
            )
            template.subscriber_count += 1
            db.flush()

            # Verify strategy query with member join (as list_strategies does)
            stmt = (
                select(Strategy)
                .join(StrategyMember, StrategyMember.strategy_id == Strategy.id)
                .where(StrategyMember.user_id == user.id)
            )
            user_strategies = list(db.execute(stmt).scalars().all())
            assert len(user_strategies) == 1
            assert user_strategies[0].name == "My Divergence Bot"

            # Verify files on disk
            strategy_py = os.path.join(paths.strategy_dir, "strategy.py")
            assert os.path.exists(strategy_py)
            with open(strategy_py) as f:
                code = f.read()
                assert "Divergence-style mean reversion" in code

            version_py = os.path.join(paths.versions_dir, version_id, "strategy.py")
            assert os.path.exists(version_py)
            with open(version_py) as f:
                v_code = f.read()
                assert "Divergence-style mean reversion" in v_code

            # Verify template subscriber count
            assert template.subscriber_count == 1


if __name__ == "__main__":
    test_template_fork_domain_and_workspace()
    print("test_template_fork_domain_and_workspace passed successfully!")
