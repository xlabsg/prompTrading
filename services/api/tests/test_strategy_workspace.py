from __future__ import annotations

import json
import os
import tempfile
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from control_plane.models import Strategy
from app.deps import get_db
from app.main import app
from app.settings import settings


@pytest.fixture
def workspace_client(monkeypatch):
    client = TestClient(app)

    # Temporary workspaces dir
    with tempfile.TemporaryDirectory() as tmp_dir:
        monkeypatch.setattr(settings, "workspaces_dir", tmp_dir)
        yield client, tmp_dir


def test_get_strategy_overview_and_params_schema(workspace_client, monkeypatch):
    client, tmp_dir = workspace_client

    strategy_id = "strat_123"
    strategy_dir = os.path.join(tmp_dir, strategy_id, "strategy")
    os.makedirs(strategy_dir, exist_ok=True)

    with open(os.path.join(strategy_dir, "overview.md"), "w", encoding="utf-8") as f:
        f.write("# Strategy Overview\nThis is a test strategy.")

    schema_data = {
        "params": [
            {"name": "fast_period", "type": "int", "default": 12},
            {"name": "slow_period", "type": "int", "default": 26},
        ]
    }
    with open(os.path.join(strategy_dir, "params_schema.json"), "w", encoding="utf-8") as f:
        json.dump(schema_data, f)

    with open(os.path.join(strategy_dir, "strategy_meta.json"), "w", encoding="utf-8") as f:
        json.dump({"parameters": {"fast_period": 12}}, f)

    # Mock DB query for Strategy and membership
    mock_db = MagicMock()
    mock_strat = Strategy(id=strategy_id, name="Test Strat")
    mock_db.get.return_value = mock_strat
    monkeypatch.setattr("app.routers.strategy_workspace.require_strategy_member", lambda *args, **kwargs: None)
    client.app.dependency_overrides[get_db] = lambda: mock_db

    # Test /overview
    res_overview = client.get(f"/api/strategies/{strategy_id}/overview")
    assert res_overview.status_code == 200
    assert res_overview.json()["content"] == "# Strategy Overview\nThis is a test strategy."

    # Test /params-schema
    res_schema = client.get(f"/api/strategies/{strategy_id}/params-schema")
    assert res_schema.status_code == 200
    data = res_schema.json()
    assert data["params_schema"] == schema_data
    assert data["parameters"] == {"fast_period": 12}
