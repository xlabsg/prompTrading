from __future__ import annotations

import importlib.util
import os
import re
from types import ModuleType
from typing import Any, Callable


def _safe_module_name(name: str) -> str:
    name = re.sub(r"[^a-zA-Z0-9_]+", "_", name)
    if not name:
        name = "strategy_module"
    if name[0].isdigit():
        name = f"m_{name}"
    return name


def load_callable_from_file(file_path: str, func_name: str) -> Callable[..., Any]:
    if not os.path.isfile(file_path):
        raise FileNotFoundError(file_path)
    module_name = _safe_module_name(os.path.splitext(os.path.basename(file_path))[0])
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed_to_load_spec: {file_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    fn = getattr(module, func_name, None)
    if fn is None or not callable(fn):
        raise AttributeError(f"function_not_found: {func_name}")
    return fn

