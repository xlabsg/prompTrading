from __future__ import annotations

import ast
import json
import os
import subprocess
import tempfile
import textwrap
from dataclasses import dataclass
from typing import Any

from agent.llm_openai_compat import ChatCompletionRequest, ChatMessage, _strip_code_fences, chat_completion
from agent.pipeline.base import extract_json_from_text
from agent.prompt.builder import PromptBuilder
from agent.prompt.context import prepare_code_context


@dataclass(frozen=True)
class SpecArtifacts:
    spec: dict[str, Any]
    validation: dict[str, Any]
    attempts: int


# Global prompt builder (lazy init)
_prompt_builder: PromptBuilder | None = None


def _get_prompt_builder() -> PromptBuilder:
    """Get or create the global PromptBuilder."""
    global _prompt_builder
    if _prompt_builder is None:
        _prompt_builder = PromptBuilder()
    return _prompt_builder


def _validate_spec(spec: dict[str, Any]) -> None:
    if not isinstance(spec, dict):
        raise ValueError("spec_not_object")
    if spec.get("version") != 1:
        raise ValueError("spec_invalid_version")
    required = ["summary", "strategy_type", "market", "interval", "direction", "indicators", "entry_rules", "exit_rules", "params", "risk", "debug_series"]
    for key in required:
        if key not in spec:
            raise ValueError(f"spec_missing_{key}")
    if not isinstance(spec.get("indicators"), list) or not spec["indicators"]:
        raise ValueError("spec_indicators_empty")
    if not isinstance(spec.get("params"), list):
        raise ValueError("spec_params_not_list")
    if not isinstance(spec.get("debug_series"), list) or not (2 <= len(spec["debug_series"]) <= 6):
        raise ValueError("spec_debug_series_invalid")
    if spec.get("direction") not in ("long", "short", "both"):
        raise ValueError("spec_direction_invalid")


def build_strategy_spec(*, llm: Any, prompt: str, current_code: str) -> dict[str, Any]:
    """Build strategy spec using PromptBuilder.

    Args:
        llm: LLM configuration with api_key, base_url, model, temperature.
        prompt: User request prompt.
        current_code: Existing strategy code.

    Returns:
        Validated spec dictionary.
    """
    # Build prompt using PromptBuilder
    builder = _get_prompt_builder()
    system, user, _ = builder.build_spec_generation(
        prompt=prompt,
        current_code=current_code,
    )

    last_err: Exception | None = None
    for attempt in range(1, 4):
        req = ChatCompletionRequest(
            api_key=llm.api_key or "",
            base_url=llm.base_url,
            model=llm.model,
            messages=[ChatMessage(role="system", content=system), ChatMessage(role="user", content=user)],
            temperature=0.05 if attempt == 1 else 0.1,
        )
        raw = chat_completion(req)
        try:
            spec = json.loads(extract_json_from_text(raw))
            _validate_spec(spec)
            return spec
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            user = user + "\n\nIMPORTANT: Your previous response was invalid. Output strictly valid JSON ONLY."
    raise last_err or RuntimeError("spec_build_failed")


def _static_safety_check(code: str) -> None:
    tree = ast.parse(code)
    banned_imports = {"os", "sys", "subprocess", "socket", "pathlib", "requests", "urllib", "http", "shutil"}
    banned_calls = {"open", "exec", "eval", "__import__"}
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                name = (alias.name or "").split(".", 1)[0]
                if name in banned_imports:
                    raise ValueError(f"banned_import:{name}")
        if isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Name) and fn.id in banned_calls:
                raise ValueError(f"banned_call:{fn.id}")


def _run_validation_subprocess(
    code: str,
    *,
    timeout_s: int = 20,
    n_bars: int = 800,
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="spec-validate-") as td:
        strategy_path = os.path.join(td, "strategy.py")
        harness_path = os.path.join(td, "harness.py")
        with open(strategy_path, "w", encoding="utf-8") as f:
            f.write(code.strip() + "\n")

        harness = textwrap.dedent(
            f"""
            import importlib.util
            import json
            import traceback
            import numpy as np
            import pandas as pd

            from backtest.vectorized import run_backtest, BacktestConfig

            def load_module(path: str):
                spec = importlib.util.spec_from_file_location("strategy_mod", path)
                mod = importlib.util.module_from_spec(spec)
                assert spec and spec.loader
                spec.loader.exec_module(mod)
                return mod

            def synth_df(n: int) -> pd.DataFrame:
                rng = np.random.default_rng(7)
                rets = rng.normal(0.0, 0.01, size=n)
                close = 100.0 * np.exp(np.cumsum(rets))
                open_ = np.roll(close, 1)
                open_[0] = close[0]
                high = np.maximum(open_, close) * (1.0 + rng.uniform(0.0, 0.002, size=n))
                low = np.minimum(open_, close) * (1.0 - rng.uniform(0.0, 0.002, size=n))
                volume = rng.uniform(1.0, 100.0, size=n)
                ts0 = 1700000000000
                ts = ts0 + np.arange(n, dtype=np.int64) * 3600_000
                return pd.DataFrame({{
                    "timestamp": ts,
                    "open": open_,
                    "high": high,
                    "low": low,
                    "close": close,
                    "volume": volume,
                }})

            def main():
                try:
                    mod = load_module({strategy_path!r})
                    fn = getattr(mod, "generate_signals", None)
                    if fn is None or not callable(fn):
                        raise RuntimeError("missing_generate_signals")
                    data = synth_df({n_bars})
                    out = fn(data.copy(), {{}})
                    if not isinstance(out, dict):
                        raise RuntimeError("signals_not_dict")
                    n = len(data)
                    required = {{"target_weights", "weight_reason"}}
                    warnings = []
                    if "target_weights" in out:
                        tw = np.asarray(out["target_weights"], dtype=float)
                        if tw.shape[0] != n:
                            raise RuntimeError("target_weights_length_mismatch")
                        if np.isnan(tw).any() or np.isinf(tw).any():
                            raise RuntimeError("target_weights_invalid")
                        if "weight_reason" not in out:
                            raise RuntimeError("reason_missing")
                        wr = np.asarray(out["weight_reason"], dtype=object)
                        if wr.shape[0] != n:
                            raise RuntimeError("reason_length_mismatch")
                        if not np.any(np.abs(tw) > 1e-12):
                            warnings.append("signals_empty")
                    else:
                        raise RuntimeError("signals_missing_required_keys")

                    debug_keys = [k for k in out.keys() if k not in required]
                    if len(debug_keys) < 2 or len(debug_keys) > 6:
                        raise RuntimeError("debug_series_count_invalid")

                    run_backtest(data, signals=out, interval="1h", config=BacktestConfig())
                    print(json.dumps({{"ok": True, "warnings": warnings}}))
                    return 0
                except Exception as e:
                    print(json.dumps({{
                        "ok": False,
                        "error": str(e),
                        "traceback": traceback.format_exc(),
                    }}))
                    return 2

            if __name__ == "__main__":
                raise SystemExit(main())
            """
        ).strip()
        with open(harness_path, "w", encoding="utf-8") as f:
            f.write(harness + "\n")

        proc = subprocess.run(
            ["python", harness_path],
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
        stdout = (proc.stdout or "").strip()
        stderr = (proc.stderr or "").strip()
        try:
            payload = json.loads(stdout.splitlines()[-1]) if stdout else {"ok": False, "error": "no_output"}
        except Exception:
            payload = {"ok": False, "error": "invalid_json_output", "stdout": stdout, "stderr": stderr}
        payload.setdefault("exit_code", proc.returncode)
        if stderr:
            payload.setdefault("stderr", stderr[-4000:])
        return payload


def _repair_instruction_message(*, validation: dict[str, Any], prompt: str) -> str:
    """Build repair instruction message using PromptBuilder.

    Args:
        validation: Validation result dictionary.
        prompt: Original user prompt (for language detection).

    Returns:
        Repair instruction message string.
    """
    builder = _get_prompt_builder()
    _, user, _ = builder.build_code_repair(
        prompt=prompt,
        code="",  # Will be filled by caller
        validation=validation,
    )

    # Add FULLFILE prefix note (expected by spec_loop_generate)
    repair_msg = user + """

Output format:
- Output the FULL updated strategy.py (Python only, no markdown).
- Optional prefix 'FULLFILE:' is allowed.
"""
    return repair_msg


def _codegen_messages(*, spec: dict[str, Any], prompt: str, current_code: str) -> tuple[str, str]:
    """Generate codegen messages using template from PromptBuilder.

    Args:
        spec: Strategy spec dictionary.
        prompt: Original user prompt.
        current_code: Existing strategy code.

    Returns:
        Tuple of (system_message, user_message).
    """
    # Use intelligent code context preparation
    builder = _get_prompt_builder()
    code_context = prepare_code_context(
        current_code,
        max_length=2000,  # Spec needs less context
        include_imports=True,
    )

    # Language directive
    from agent.prompt.context import build_language_directive
    language_directive = build_language_directive(prompt)

    system = (
        "You are a senior quant developer. Convert the provided strategy SPEC into a single Python file for vectorized backtesting.\n"
        "Hard requirements:\n"
        "- Provide generate_signals(data: pandas.DataFrame, params: dict) -> dict\n"
        "- data columns: timestamp, open, high, low, close, volume\n"
        "- Return {target_weights: float_array} with values in [-1, 1].\n"
        "- ALSO return weight_reason as list[str] length n.\n"
        "- Include 2-6 bar-aligned debug series (floats/bools) that explain decisions.\n"
        "- Use deterministic, vectorized pandas/numpy.\n"
        "- Allowed imports: pandas, numpy, backtest.indicators\n"
        "- Forbidden: network, file I/O, os/subprocess, randomness.\n"
        f"Output ONLY Python code (no markdown).\n\n{language_directive}"
    )
    user = textwrap.dedent(
        f"""
        SPEC:
        {json.dumps(spec, ensure_ascii=False, indent=2)}

        USER_REQUEST:
        {prompt}

        CURRENT_STRATEGY_CODE (may be empty):
        ```python
        {code_context.strip() if code_context.strip() else "# Empty"}
        ```

        Generate strategy.py now.
        """
    ).strip()
    return system, user


def spec_loop_generate(
    *,
    llm: Any,
    prompt: str,
    current_code: str,
    version_dir: str,
    max_attempts: int = 3,
) -> tuple[str, SpecArtifacts]:
    """Generate strategy using spec-loop pattern.

    Args:
        llm: LLM configuration.
        prompt: User request prompt.
        current_code: Existing strategy code.
        version_dir: Directory to write artifacts.
        max_attempts: Maximum number of codegen attempts.

    Returns:
        Tuple of (generated_code, SpecArtifacts).
    """
    spec = build_strategy_spec(llm=llm, prompt=prompt, current_code=current_code)
    try:
        with open(os.path.join(version_dir, "spec.json"), "w", encoding="utf-8") as f:
            json.dump(spec, f, ensure_ascii=False, indent=2, sort_keys=True)
    except Exception:
        pass

    validation: dict[str, Any] = {}
    code = ""
    attempts = 0
    for attempt in range(1, max(1, int(max_attempts)) + 1):
        attempts = attempt
        system, user = _codegen_messages(spec=spec, prompt=prompt, current_code=current_code)
        messages: list[ChatMessage] = [ChatMessage(role="system", content=system), ChatMessage(role="user", content=user)]
        if attempt > 1:
            messages.append(ChatMessage(role="assistant", content=code.strip()))
            messages.append(ChatMessage(role="user", content=_repair_instruction_message(validation=validation, prompt=prompt)))

        req = ChatCompletionRequest(
            api_key=llm.api_key or "",
            base_url=llm.base_url,
            model=llm.model,
            messages=messages,
            temperature=llm.temperature if attempt == 1 else 0.1,
        )
        raw = chat_completion(req)
        raw = _strip_code_fences(raw)
        if attempt > 1 and raw.lstrip().startswith("FULLFILE:"):
            code = raw.split("FULLFILE:", 1)[1].lstrip()
        else:
            code = raw

        ast.parse(code)
        if "def generate_signals" not in code:
            validation = {"ok": False, "error": "missing_generate_signals", "traceback": "", "attempt": attempt}
        else:
            _static_safety_check(code)
            validation = _run_validation_subprocess(code)
            validation["attempt"] = attempt

        try:
            with open(os.path.join(version_dir, f"spec_validation_attempt_{attempt}.json"), "w", encoding="utf-8") as f:
                json.dump(validation, f, ensure_ascii=False, indent=2, sort_keys=True)
        except Exception:
            pass

        warnings = validation.get("warnings") or []
        if validation.get("ok") is True and not warnings:
            break
        if validation.get("ok") is True and warnings and attempt >= max_attempts:
            break

    if not validation.get("ok"):
        raise RuntimeError(f"spec_codegen_failed:{validation.get('error')}")

    artifacts = SpecArtifacts(spec=spec, validation=validation, attempts=attempts)
    return code, artifacts


__all__ = ["SpecArtifacts", "spec_loop_generate"]
