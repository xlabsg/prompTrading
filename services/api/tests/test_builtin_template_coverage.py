"""Every seeded builtin template must have code the backtest path can run.

Regression guard: the worker used to keep its own copy of TEMPLATE_STRATEGIES.
It drifted from the control_plane one, `tmpl-flow-right` shipped without a
worker-side entry, and template_backtest_job raised `template_not_supported`
for a template the UI happily offered. The worker now imports the dict; this
checks the other half, that the seed list stays inside it.
"""

import importlib.util
import os

from control_plane.templates import TEMPLATE_STRATEGIES

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))

# The repo checkout and the api image lay the tree out differently: locally the
# script sits beside the tests, in the image it lives under /app/services/api.
_SEED_SCRIPT_CANDIDATES = (
    os.path.join(_TESTS_DIR, "..", "scripts", "seed_builtin_templates.py"),
    "/app/services/api/scripts/seed_builtin_templates.py",
)


def _load_seed_module():
    for candidate in _SEED_SCRIPT_CANDIDATES:
        if os.path.isfile(candidate):
            spec = importlib.util.spec_from_file_location(
                "seed_builtin_templates", candidate
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
    raise AssertionError(
        f"seed_builtin_templates.py not found in {_SEED_SCRIPT_CANDIDATES}"
    )


def test_every_seeded_template_has_strategy_code():
    seeded = {tmpl["id"] for tmpl in _load_seed_module().BUILTIN_TEMPLATES}
    assert seeded, "seed script registers no templates"
    missing = sorted(seeded - set(TEMPLATE_STRATEGIES))
    assert not missing, f"seeded templates without strategy code: {missing}"
