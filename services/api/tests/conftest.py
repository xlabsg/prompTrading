"""Pytest fixtures for Docker-Compose-based E2E tests.

Key constraint (first principle):
  Worker runs in a separate process. So tests must interact with the *real* API
  service (HTTP) using committed DB writes; in-process TestClient + transaction
  rollbacks will hide jobs from the worker and cause hangs.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone

import pytest
import requests
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from control_plane.db import create_db_engine
from app.settings import settings
from tests.fixtures.test_data import (
    build_auth_cookies,
    create_test_session,
    create_test_user,
)


def _hour_floor_ms(ts_ms: int) -> int:
    return (ts_ms // 3_600_000) * 3_600_000


def last_30d_range_ms() -> tuple[int, int]:
    """Return an hour-aligned (start_ms, end_ms) for the last 30 days."""
    now_ms = int(time.time() * 1000)
    end_ms = _hour_floor_ms(now_ms)
    start_ms = end_ms - 30 * 24 * 3_600_000
    return start_ms, end_ms


def wait_for_job_completion(
    client: "E2EClient",
    job_id: str,
    *,
    timeout_s: int = 900,
    poll_s: float = 5.0,
) -> dict:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        job = client.get_json(f"/api/jobs/{job_id}")
        if job.get("status") in ("succeeded", "failed"):
            return job
        time.sleep(poll_s)
        poll_s = min(poll_s + 1.5, 20.0)
    raise TimeoutError(f"Job {job_id} did not complete within {timeout_s}s")


def wait_for_backtest_completion(
    client: "E2EClient",
    run_id: str,
    *,
    timeout_s: int = 900,
    poll_s: float = 5.0,
) -> dict:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        run = client.get_json(f"/api/backtests/{run_id}")
        if run.get("status") in ("succeeded", "failed"):
            return run
        time.sleep(poll_s)
        poll_s = min(poll_s + 1.5, 20.0)
    raise TimeoutError(f"BacktestRun {run_id} did not complete within {timeout_s}s")


@dataclass(frozen=True)
class E2EClient:
    base_url: str
    session: requests.Session

    def url(self, path: str) -> str:
        if not path.startswith("/"):
            raise ValueError("path must start with '/'")
        return f"{self.base_url}{path}"

    def request(self, method: str, path: str, **kwargs) -> requests.Response:
        timeout = kwargs.pop("timeout", 60)
        return self.session.request(method, self.url(path), timeout=timeout, **kwargs)

    def get_json(self, path: str, **kwargs) -> dict:
        res = self.request("GET", path, **kwargs)
        assert res.status_code == 200, f"GET {path} -> {res.status_code}: {res.text}"
        return res.json()

    def post_json(self, path: str, payload: dict, **kwargs) -> dict:
        res = self.request("POST", path, json=payload, **kwargs)
        assert res.status_code == 200, f"POST {path} -> {res.status_code}: {res.text}"
        return res.json()


@pytest.fixture(scope="session")
def e2e_api_base_url() -> str:
    url = os.getenv("E2E_API_BASE_URL", "http://api:8000").rstrip("/")
    try:
        requests.get(f"{url}/health", timeout=1.0)
    except Exception:
        pytest.skip(f"E2E API service is not running or not reachable at {url}")
    return url


@pytest.fixture(scope="session")
def e2e_db_engine():
    from control_plane.models import Base
    try:
        engine = create_db_engine(settings.db_url)
        Base.metadata.create_all(bind=engine)
        # Basic sanity: verify DB is reachable and schema exists.
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return engine
    except Exception as e:
        pytest.skip(f"E2E database not available ({settings.db_url}): {e}")


@pytest.fixture(scope="function")
def e2e_db_session(e2e_db_engine) -> Session:
    SessionLocal = sessionmaker(bind=e2e_db_engine, autoflush=False, autocommit=False)
    with SessionLocal() as db:
        yield db


@pytest.fixture(scope="function")
def e2e_user(e2e_db_session: Session) -> dict:
    """Create and commit a real user session usable by the running API service."""
    user = create_test_user(e2e_db_session)
    session = create_test_session(e2e_db_session, user)
    e2e_db_session.commit()
    return {"user": user, "token": session.token, "cookies": build_auth_cookies(session)}


@pytest.fixture(scope="function")
def e2e_client(e2e_api_base_url: str, e2e_user: dict) -> E2EClient:
    sess = requests.Session()
    sess.cookies.update(e2e_user["cookies"])
    client = E2EClient(base_url=e2e_api_base_url, session=sess)
    yield client
    sess.close()


@pytest.fixture(scope="function")
def e2e_strategy_id(e2e_client: E2EClient) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    payload = e2e_client.post_json("/api/strategies", {"name": f"e2e-{ts}"})
    strategy_id = payload.get("id")
    assert isinstance(strategy_id, str) and strategy_id, "Missing strategy id"
    return strategy_id
