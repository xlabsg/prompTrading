from __future__ import annotations

from dataclasses import dataclass


_EPS = 1e-12


@dataclass(frozen=True)
class WeightTransition:
    signal_type: str
    position_side: str
    signal_reason: str
    order_side: str | None
    changed: bool


def describe_weight_transition(
    weight_from: float,
    weight_to: float,
    *,
    signal_source: str = "target_weights",
) -> WeightTransition:
    wf = float(weight_from)
    wt = float(weight_to)
    delta = wt - wf
    changed = abs(delta) >= _EPS
    order_side = None if not changed else ("buy" if delta > 0 else "sell")

    if abs(wf) < _EPS and abs(wt) < _EPS:
        return WeightTransition(
            signal_type="noop",
            position_side="flat",
            signal_reason="no_change",
            order_side=order_side,
            changed=changed,
        )
    if abs(wf) < _EPS and abs(wt) >= _EPS:
        side = "long" if wt > 0 else "short"
        return WeightTransition(
            signal_type="entry",
            position_side=side,
            signal_reason="entry_signal",
            order_side=order_side,
            changed=changed,
        )
    if abs(wf) >= _EPS and abs(wt) < _EPS:
        side = "long" if wf > 0 else "short"
        return WeightTransition(
            signal_type="exit",
            position_side=side,
            signal_reason="exit_signal",
            order_side=order_side,
            changed=changed,
        )
    if (wf > 0 and wt < 0) or (wf < 0 and wt > 0):
        side = "long" if wt > 0 else "short"
        return WeightTransition(
            signal_type="flip",
            position_side=side,
            signal_reason="flip_signal",
            order_side=order_side,
            changed=changed,
        )
    side = "long" if wt > 0 else "short"
    return WeightTransition(
        signal_type="rebalance",
        position_side=side,
        signal_reason="target_weight_change" if signal_source == "target_weights" else "position_change",
        order_side=order_side,
        changed=changed,
    )
