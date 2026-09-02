"""Single entry point for creating strategy versions.

Every caller used to repeat the same two-step dance: construct a
`StrategyVersion` with `workspace_path=""`, flush to get the generated id, then
patch the path in. Missing that second step leaves a version pointing at an
empty directory, which only surfaces later as a confusing backtest failure.

Two workspace layouts exist, and the difference is what `snapshot` selects:

- `snapshot=True`  — copy the current strategy files into `versions/<id>/` now.
  Used when the version records the state of the strategy at this moment.
- `snapshot=False` — reserve `versions/<id>/` for a job container to populate.
  Used when an agent or backtest container writes the version's contents.
"""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from control_plane.models import StrategyVersion
from control_plane.workspaces import snapshot_current_strategy_to_version


def next_version_number(db: Session, strategy_id: str) -> int:
    """Next sequential version number for a strategy (1-based)."""
    current = db.execute(
        select(func.max(StrategyVersion.version)).where(
            StrategyVersion.strategy_id == strategy_id
        )
    ).scalar()
    return int(current or 0) + 1


def create_strategy_version(
    db: Session,
    *,
    strategy_id: str,
    prompt: Optional[str] = None,
    llm_meta: Optional[dict[str, Any]] = None,
    version: Optional[int] = None,
    snapshot: bool = True,
    workspaces_dir: Optional[str] = None,
) -> StrategyVersion:
    """Create a `StrategyVersion` with its `workspace_path` already set.

    Args:
        version: explicit version number; defaults to the next in sequence.
        snapshot: copy the current strategy into the version directory.
        workspaces_dir: workspace root; required when `snapshot` is True.

    The returned version is flushed but not committed, so callers keep control
    of the surrounding transaction.
    """
    if snapshot and not workspaces_dir:
        raise ValueError("workspaces_dir is required when snapshot=True")

    record = StrategyVersion(
        strategy_id=strategy_id,
        version=version if version is not None else next_version_number(db, strategy_id),
        workspace_path="",
        prompt=prompt,
        llm_meta=llm_meta or {},
    )
    db.add(record)
    # The id is generated on flush and the workspace path is derived from it.
    db.flush()

    if snapshot:
        record.workspace_path = snapshot_current_strategy_to_version(
            workspaces_dir, strategy_id, record.id
        )
    else:
        record.workspace_path = f"versions/{record.id}"
    return record


__all__ = ["create_strategy_version", "next_version_number"]
