from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import tempfile
import textwrap
from dataclasses import dataclass
from typing import Any, Optional

from agent.llm_openai_compat import ChatCompletionRequest, ChatMessage, _strip_code_fences, chat_completion


_PINESCRIPT_FENCE_RE = re.compile(r"```pinescript\s*(.*?)```", re.DOTALL | re.IGNORECASE)
_NAME_RE = re.compile(r"^-\\s*Name:\\s*(.+?)\\s*$", re.MULTILINE)
_DESC_RE = re.compile(r"^-\\s*Description:\\s*(.+?)\\s*$", re.MULTILINE)


@dataclass(frozen=True)
class PineArtifacts:
    raw_pinescript: str
    cleaned_pinescript: str
    metadata: dict[str, str]
    ir: dict[str, Any]
    validation: dict[str, Any]


def extract_pinescript_from_prompt(prompt: str) -> Optional[tuple[str, dict[str, str]]]:
    """Extract a PineScript code block + basic metadata from a free-form prompt."""
    m = _PINESCRIPT_FENCE_RE.search(prompt or "")
    if not m:
        return None
    src = (m.group(1) or "").strip()
    if not src:
        return None

    meta: dict[str, str] = {}
    nm = _NAME_RE.search(prompt)
    if nm:
        meta["script_name"] = nm.group(1).strip()
    dm = _DESC_RE.search(prompt)
    if dm:
        meta["script_description"] = dm.group(1).strip()
    return src, meta


def _strip_pine_comments(src: str) -> str:
    """Remove // and /* */ comments while keeping strings."""
    out: list[str] = []
    i = 0
    n = len(src)
    in_str = False
    str_quote = ""
    in_line_comment = False
    in_block_comment = False

    while i < n:
        ch = src[i]
        nxt = src[i + 1] if i + 1 < n else ""

        if in_line_comment:
            if ch == "\n":
                in_line_comment = False
                out.append(ch)
            i += 1
            continue

        if in_block_comment:
            if ch == "*" and nxt == "/":
                in_block_comment = False
                i += 2
                continue
            i += 1
            continue

        if in_str:
            out.append(ch)
            if ch == "\\" and nxt:
                out.append(nxt)
                i += 2
                continue
            if ch == str_quote:
                in_str = False
                str_quote = ""
            i += 1
            continue

        if ch in ("'", '"'):
            in_str = True
            str_quote = ch
            out.append(ch)
            i += 1
            continue

        if ch == "/" and nxt == "/":
            in_line_comment = True
            i += 2
            continue
        if ch == "/" and nxt == "*":
            in_block_comment = True
            i += 2
            continue

        out.append(ch)
        i += 1

    return "".join(out)


def preprocess_pinescript(src: str, *, max_chars: int = 12_000) -> str:
    """Heuristic preprocessing to reduce noise while preserving trading logic."""
    src = (src or "").replace("\r\n", "\n").replace("\r", "\n")
    src = _strip_pine_comments(src)

    keep: list[str] = []
    for raw in src.splitlines():
        line = raw.strip()
        if not line:
            continue
        # Drop UI/plotting noise.
        if line.startswith(("plot", "hline", "fill", "label.", "table.", "bgcolor", "barcolor", "alert")):
            continue
        # Keep likely trading-logic lines.
        if any(k in line for k in ("strategy.", "ta.", "input.", "var ", "if ", "else", "for ", "while ")):
            keep.append(raw)
            continue
        # Keep assignments that define key series/conditions.
        if "=" in line and not line.startswith("//"):
            keep.append(raw)
            continue

    cleaned = "\n".join(keep).strip()
    if len(cleaned) <= max_chars:
        return cleaned

    # If still too large: keep head+tail to retain declarations and trading logic.
    head = cleaned[: max_chars // 2]
    tail = cleaned[-max_chars // 2 :]
    return (head + "\n\n// ... truncated ...\n\n" + tail).strip()


def _extract_json_object(text: str) -> str:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return text
    return text[start : end + 1]


def _validate_ir(ir: dict[str, Any]) -> None:
    if not isinstance(ir, dict):
        raise ValueError("ir_not_object")
    if "version" not in ir:
        raise ValueError("ir_missing_version")
    if "direction" not in ir:
        raise ValueError("ir_missing_direction")
    if "targets" not in ir or not isinstance(ir["targets"], dict):
        raise ValueError("ir_missing_targets")
    if "params" not in ir or not isinstance(ir["params"], list):
        raise ValueError("ir_missing_params")


def _static_safety_check(code: str) -> None:
    """Reject clearly unsafe / non-deterministic code (best-effort, not a sandbox)."""
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
    """Execute generated code against synthetic OHLCV and a smoke backtest."""
    with tempfile.TemporaryDirectory(prefix="pine-validate-") as td:
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
                # random walk close, positive prices
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
                    required = {"target_weights", "weight_reason"}
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
                    else:
                        raise RuntimeError("signals_missing_required_keys")

                    debug_keys = [k for k in out.keys() if k not in required]
                    if len(debug_keys) < 2 or len(debug_keys) > 6:
                        raise RuntimeError("debug_series_count_invalid")

                    # Smoke run: ensures backtest engine accepts produced signals.
                    run_backtest(data, signals=out, interval="1h", config=BacktestConfig())
                    print(json.dumps({{"ok": True}}))
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
        payload: dict[str, Any]
        try:
            payload = json.loads(stdout.splitlines()[-1]) if stdout else {"ok": False, "error": "no_output"}
        except Exception:
            payload = {"ok": False, "error": "invalid_json_output", "stdout": stdout, "stderr": stderr}

        payload.setdefault("exit_code", proc.returncode)
        if stderr:
            payload.setdefault("stderr", stderr[-4000:])
        return payload


def _looks_like_unified_diff(text: str) -> bool:
    s = (text or "").lstrip()
    return s.startswith("---") and "\n+++" in s and "\n@@" in s


def build_ir(llm: Any, *, pinescript: str, meta: dict[str, str]) -> dict[str, Any]:
    """LLM step: PineScript -> JSON IR."""
    system = (
        "You are a PineScript-to-Python compiler front-end. "
        "Convert PineScript strategy logic into a concise, strictly valid JSON intermediate representation (IR). "
        "Do NOT output markdown. Do NOT output explanations. Output JSON only."
    )
    user = textwrap.dedent(
        f"""
        PineScript strategy source (may be preprocessed):
        ```pinescript
        {pinescript}
        ```

        Metadata:
        {json.dumps(meta, ensure_ascii=False)}

        Output JSON with this schema (include all keys):
        {{
          "version": 1,
          "direction": "long"|"short"|"both",
          "params": [{{"name": "...", "type": "int"|"float"|"bool"|"str", "default": ...}}],
          "indicators": [{{"name": "...", "args": {{}}, "id": "..."}}],
          "targets": {{
            "long": "...",
            "short": "...",
            "flat": "..."
          }},
          "risk": {{"stop": "...", "take_profit": "...", "trailing": "...", "time_exit": "..."}},
          "notes": ["..."]
        }}

        Rules:
        - Use "..." strings for conditions; refer to indicator ids when helpful.
        - If a side is not used, set it to "".
        - If a feature is not present, set it to "" (or empty list).
        """
    ).strip()

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
            obj = json.loads(_extract_json_object(raw))
            _validate_ir(obj)
            return obj
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            # tighten instructions
            user = user + "\n\nIMPORTANT: Your previous response was invalid. Output strictly valid JSON ONLY."
    raise last_err or RuntimeError("ir_build_failed")


def _python_codegen_messages(*, ir: dict[str, Any], pinescript: str, meta: dict[str, str]) -> tuple[str, str]:
    system = (
        "You are a senior quant developer. Convert IR into a single Python file for vectorized backtesting.\n"
        "Hard requirements:\n"
        "- Provide generate_signals(data: pandas.DataFrame, params: dict) -> dict\n"
        "- data columns: timestamp, open, high, low, close, volume\n"
        "- Return {target_weights: float_array} with values in [-1, 1].\n"
        "- ALSO return weight_reason as list[str] length n (empty string when no change).\n"
        "- Include 2-6 bar-aligned debug series (floats/bools) that explain decisions (e.g. rsi, fast_ma, slow_ma, cond_entry).\n"
        "- Use deterministic, vectorized pandas/numpy.\n"
        "- Allowed imports: pandas, numpy, backtest.indicators\n"
        "- Forbidden: network, file I/O, os/subprocess, randomness.\n"
        "Output ONLY Python code (no markdown)."
    )
    user = textwrap.dedent(
        f"""
        METADATA:
        {json.dumps(meta, ensure_ascii=False)}

        IR:
        {json.dumps(ir, ensure_ascii=False, indent=2)}

        REFERENCE PINESCRIPT (preprocessed):
        ```pinescript
        {pinescript[:6000]}
        ```

        Generate strategy.py now.
        """
    ).strip()
    return system, user

def _repair_instruction_message(*, validation: dict[str, Any]) -> str:
    """User message appended after tool output. Keep short and stable for caching."""
    return textwrap.dedent(
        f"""
        TOOL_OUTPUT: validation_json
        {json.dumps(validation, ensure_ascii=False, indent=2)[:8000]}

        Task:
        - Fix the code so TOOL_OUTPUT.ok becomes true.
        - Prefer MINIMAL edits.
        - Do NOT change strategy intent unless required for correctness.

        Output format:
        - Output the FULL updated strategy.py (Python only, no markdown).
        - Optional prefix 'FULLFILE:' is allowed.
        """
    ).strip()


def pinescript_4stage_generate(
    *,
    llm: Any,
    prompt: str,
    version_dir: str,
    max_attempts: int = 3,
) -> tuple[str, PineArtifacts]:
    """Run the 4-stage conversion pipeline and persist debug artifacts in version_dir."""
    extracted = extract_pinescript_from_prompt(prompt)
    if not extracted:
        raise ValueError("pinescript_block_not_found")
    raw_pine, meta = extracted

    cleaned = preprocess_pinescript(raw_pine)
    try:
        with open(os.path.join(version_dir, "pinescript_source.pine"), "w", encoding="utf-8") as f:
            f.write(raw_pine.strip() + "\n")
        with open(os.path.join(version_dir, "pinescript_cleaned.pine"), "w", encoding="utf-8") as f:
            f.write(cleaned.strip() + "\n")
    except Exception:
        pass

    ir = build_ir(llm, pinescript=cleaned, meta=meta)
    try:
        with open(os.path.join(version_dir, "pinescript_ir.json"), "w", encoding="utf-8") as f:
            json.dump(ir, f, ensure_ascii=False, indent=2, sort_keys=True)
    except Exception:
        pass

    validation: dict[str, Any] = {}
    last_err = ""
    last_tb = ""

    code = ""
    for attempt in range(1, max(1, int(max_attempts)) + 1):
        # Unrolled agent loop: keep a stable prefix (system+user with IR/pine),
        # then append previous assistant output + tool output for repair.
        system, user = _python_codegen_messages(ir=ir, pinescript=cleaned, meta=meta)
        messages: list[ChatMessage] = [ChatMessage(role="system", content=system), ChatMessage(role="user", content=user)]
        if attempt > 1:
            # Provide the last version as assistant output and the validator result as tool output.
            messages.append(ChatMessage(role="assistant", content=code.strip()))
            messages.append(ChatMessage(role="user", content=_repair_instruction_message(validation=validation)))

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
        elif attempt > 1 and _looks_like_unified_diff(raw):
            last_err = "unexpected_diff_output"
            validation = {"ok": False, "error": last_err, "traceback": "", "exit_code": 2, "attempt": attempt}
            continue
        else:
            code = raw

        # Minimal structural checks first.
        ast.parse(code)
        if "def generate_signals" not in code:
            last_err = "missing_generate_signals"
            last_tb = ""
            validation = {"ok": False, "error": last_err, "traceback": "", "exit_code": 2, "attempt": attempt}
            continue
        _static_safety_check(code)

        validation = _run_validation_subprocess(code)
        validation["attempt"] = attempt
        try:
            with open(os.path.join(version_dir, "pinescript_validation.json"), "w", encoding="utf-8") as f:
                json.dump(validation, f, ensure_ascii=False, indent=2, sort_keys=True)
        except Exception:
            pass

        if validation.get("ok") is True:
            artifacts = PineArtifacts(
                raw_pinescript=raw_pine,
                cleaned_pinescript=cleaned,
                metadata=meta,
                ir=ir,
                validation=validation,
            )
            return code, artifacts

        last_err = str(validation.get("error") or "validation_failed")
        last_tb = str(validation.get("traceback") or "")

    raise RuntimeError(f"pinescript_conversion_failed:{last_err}")


__all__ = [
    "PineArtifacts",
    "extract_pinescript_from_prompt",
    "pinescript_4stage_generate",
]
