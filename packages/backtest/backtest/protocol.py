from __future__ import annotations

import hashlib
import time
from typing import Any, Literal

import numpy as np
import pandas as pd

SignalMode = Literal["target_weights", "auto"]


def detect_signal_mode(signals: dict[str, Any]) -> str:
    decision = signals.get("decision")
    if isinstance(decision, dict):
        if "targets" in decision or "target_weights" in decision:
            return "target_weights"
    if "targets" in signals:
        return "target_weights"
    if "target_weights" in signals:
        return "target_weights"
    return "unknown"


def _to_array(value: Any, *, n: int, dtype: Any) -> np.ndarray:
    if isinstance(value, pd.Series):
        value = value.to_numpy()
    arr = np.asarray(value, dtype=dtype)
    if arr.ndim != 1 or int(arr.shape[0]) != int(n):
        raise ValueError("signals_length_mismatch")
    return arr


def _ensure_reason_list(value: Any | None, *, n: int) -> list[str]:
    if value is None:
        return ["" for _ in range(n)]
    if isinstance(value, pd.Series):
        value = value.to_list()
    if isinstance(value, np.ndarray):
        value = value.tolist()
    if not isinstance(value, list) or len(value) != n:
        raise ValueError("signals_reason_length_mismatch")
    return ["" if v is None else str(v) for v in value]


def _to_int_ms(value: Any | None) -> int | None:
    if value is None:
        return None
    try:
        out = int(value)
    except Exception:
        raise ValueError("signals_timestamp_invalid")
    if out < 0:
        raise ValueError("signals_timestamp_invalid")
    return out


def _pick_symbol_for_targets(targets: dict[str, Any], *, symbol: str | None) -> str:
    if symbol:
        if symbol in targets:
            return symbol
        if len(targets) == 1:
            return str(next(iter(targets.keys())))
        raise ValueError("signals_symbol_not_found_in_targets")
    if len(targets) == 1:
        return str(next(iter(targets.keys())))
    raise ValueError("signals_symbol_required_for_multi_targets")


def _extract_target_payload(
    signals: dict[str, Any],
    *,
    symbol: str | None,
) -> tuple[Any, Any | None, str | None]:
    decision = signals.get("decision")
    decision_obj = decision if isinstance(decision, dict) else {}

    for container in (decision_obj, signals):
        targets = container.get("targets")
        if isinstance(targets, dict) and targets:
            resolved_symbol = _pick_symbol_for_targets(targets, symbol=symbol or str(signals.get("symbol") or ""))
            payload = targets.get(resolved_symbol)
            if isinstance(payload, dict):
                weights_raw = payload.get("target_weights", payload.get("weights"))
                reasons_raw = payload.get("weight_reason", payload.get("reason"))
            else:
                weights_raw = payload
                reasons_raw = None
            return weights_raw, reasons_raw, resolved_symbol

    if "target_weights" in decision_obj:
        return decision_obj.get("target_weights"), decision_obj.get("weight_reason"), symbol
    if "target_weights" in signals:
        # Fix: Use 'is not None' check instead of 'or' to avoid numpy array ambiguity error
        wr = signals.get("weight_reason")
        rr = signals.get("rebalance_reason")
        return signals.get("target_weights"), wr if wr is not None else rr, symbol

    raise ValueError("signals_missing_target_weights")


def _extract_decision_meta(signals: dict[str, Any]) -> dict[str, Any]:
    decision = signals.get("decision")
    decision_obj = decision if isinstance(decision, dict) else {}

    protocol_version = str(
        signals.get("protocol_version")
        or decision_obj.get("protocol_version")
        or "2.0"
    )
    decision_id = (
        decision_obj.get("decision_id")
        or decision_obj.get("id")
        or signals.get("decision_id")
    )
    decision_ts = _to_int_ms(
        decision_obj.get("decision_ts")
        or decision_obj.get("timestamp")
        or signals.get("decision_ts")
        or signals.get("timestamp")
    )
    expires_at = _to_int_ms(
        decision_obj.get("expires_at")
        or signals.get("expires_at")
    )
    diagnostics = decision_obj.get("diagnostics")
    if diagnostics is None:
        diagnostics = signals.get("diagnostics")
    if diagnostics is not None and not isinstance(diagnostics, dict):
        raise ValueError("signals_diagnostics_invalid")

    return {
        "protocol_version": protocol_version,
        "decision_id": None if decision_id is None else str(decision_id),
        "decision_ts": decision_ts,
        "expires_at": expires_at,
        "diagnostics": diagnostics,
    }


def _auto_decision_id(
    *,
    weights: np.ndarray,
    signal_symbol: str | None,
    decision_ts: int | None,
) -> str:
    digest = hashlib.blake2b(digest_size=8)
    digest.update(np.asarray(weights, dtype=np.float64).tobytes())
    digest.update(str(signal_symbol or "").encode("utf-8"))
    digest.update(str(decision_ts or 0).encode("utf-8"))
    return f"auto:{signal_symbol or 'NA'}:{decision_ts or 0}:{digest.hexdigest()}"


def normalize_signals(
    signals: dict[str, Any],
    *,
    n: int,
    mode: SignalMode = "auto",
    symbol: str | None = None,
    now_ts_ms: int | None = None,
    seen_decision_ids: set[str] | None = None,
) -> dict[str, Any]:
    if not isinstance(signals, dict):
        raise ValueError("signals_not_dict")

    detected = detect_signal_mode(signals)
    if mode == "auto":
        mode = detected if detected in ("target_weights",) else "target_weights"

    normalized = dict(signals)

    if mode == "target_weights":
        weights_raw, reasons_raw, resolved_symbol = _extract_target_payload(signals, symbol=symbol)
        weights = _to_array(weights_raw, n=n, dtype=float)
        if np.isnan(weights).any() or np.isinf(weights).any():
            raise ValueError("signals_weights_invalid")
        if np.any(weights > 1.0 + 1e-9) or np.any(weights < -1.0 - 1e-9):
            raise ValueError("signals_weights_out_of_range")
        weights = np.clip(weights, -1.0, 1.0)

        meta = _extract_decision_meta(signals)
        decision_ts = meta["decision_ts"]
        expires_at = meta["expires_at"]
        now_ts = _to_int_ms(now_ts_ms if now_ts_ms is not None else int(time.time() * 1000))
        if expires_at is not None and now_ts is not None and expires_at < now_ts:
            raise ValueError("signals_decision_expired")

        decision_id = meta["decision_id"] or _auto_decision_id(
            weights=weights,
            signal_symbol=resolved_symbol or symbol,
            decision_ts=decision_ts,
        )
        if seen_decision_ids is not None:
            if decision_id in seen_decision_ids:
                raise ValueError("signals_duplicate_decision_id")
            seen_decision_ids.add(decision_id)

        normalized["protocol_version"] = meta["protocol_version"]
        normalized["decision_id"] = decision_id
        normalized["decision_ts"] = decision_ts
        normalized["expires_at"] = expires_at
        normalized["signal_symbol"] = resolved_symbol or symbol
        normalized["diagnostics"] = meta["diagnostics"]
        normalized["target_weights"] = weights
        normalized["weight_reason"] = _ensure_reason_list(reasons_raw, n=n)
        return normalized

    raise ValueError("signals_mode_invalid")
