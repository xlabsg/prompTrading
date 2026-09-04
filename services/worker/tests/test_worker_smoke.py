from __future__ import annotations

import os
import sys
import tempfile
from unittest.mock import MagicMock
import pytest

# Ensure local test run does not try to write to /var/log/app
if "LOG_DIR" not in os.environ:
    os.environ["LOG_DIR"] = tempfile.gettempdir()

# Provide mocks for worker-specific system dependencies if running outside worker container
for mod_name in [
    "docker",
    "docker.types",
    "apscheduler",
    "apscheduler.schedulers",
    "apscheduler.schedulers.background",
    "apscheduler.triggers",
    "apscheduler.triggers.cron",
]:
    if mod_name not in sys.modules:
        try:
            __import__(mod_name)
        except ImportError:
            mock_mod = MagicMock()
            sys.modules[mod_name] = mock_mod

from control_plane.enums import JobType


def test_worker_main_imports_and_handlers_complete():
    """Verify worker.main imports cleanly and JOB_HANDLERS covers all defined JobTypes."""
    from worker.main import JOB_HANDLERS

    registered_keys = set(JOB_HANDLERS.keys())
    expected_keys = {jt.value for jt in JobType}

    assert registered_keys == expected_keys, (
        f"Mismatch in JOB_HANDLERS: missing {expected_keys - registered_keys}, extra {registered_keys - expected_keys}"
    )

    for job_type, handler in JOB_HANDLERS.items():
        assert callable(handler), f"Handler for {job_type} is not callable: {handler}"


def test_template_backtest_uses_the_shared_template_source():
    """The worker must not reintroduce its own TEMPLATE_STRATEGIES copy."""
    from control_plane.templates import TEMPLATE_STRATEGIES
    from worker.template_backtest_job import TEMPLATE_STRATEGIES as worker_templates

    assert worker_templates is TEMPLATE_STRATEGIES
