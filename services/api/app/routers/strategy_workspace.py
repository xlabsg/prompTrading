"""Workspace inspection: file listing, working-copy comparison, and git diffs."""

from __future__ import annotations

import difflib
import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from control_plane.models import Strategy, StrategyVersion

from app.auth import require_strategy_member
from app.deps import get_db
from app.services.worker_rpc import call_worker_rpc
from app.settings import settings

router = APIRouter()


WORKSPACE_VERSIONED_FILES = (
    "strategy.py",
    "strategy_spec.yaml",
    "strategy_live.py",
    "strategy_protocol.json",
    "params_schema.json",
    "strategy_meta.json",
)

WORKSPACE_COMPARE_FILES = (
    *WORKSPACE_VERSIONED_FILES,
    "overview.md",
)


def _read_text_file_if_exists(path: str) -> str | None:
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except UnicodeDecodeError:
        return None
    except OSError:
        return None


def _collect_compare_files(dir_path: str) -> dict[str, str]:
    files: dict[str, str] = {}
    if not os.path.isdir(dir_path):
        return files

    for name in WORKSPACE_COMPARE_FILES:
        text = _read_text_file_if_exists(os.path.join(dir_path, name))
        if text is not None:
            files[name] = text
    return files


def _resolve_version_dir(strategy_id: str, version: StrategyVersion) -> str:
    strategy_root = os.path.normpath(os.path.join(settings.workspaces_dir, strategy_id))
    relative_path = str(version.workspace_path or "").strip()
    if not relative_path:
        relative_path = f"versions/{version.id}"
    normalized_rel = os.path.normpath(relative_path).replace("\\", "/")
    if os.path.isabs(normalized_rel) or normalized_rel == ".." or normalized_rel.startswith("../"):
        normalized_rel = f"versions/{version.id}"
    candidate = os.path.normpath(os.path.join(strategy_root, normalized_rel))
    if candidate != strategy_root and not candidate.startswith(strategy_root + os.sep):
        candidate = os.path.join(strategy_root, "versions", version.id)
    return candidate


def _list_confirmed_versions(strategy_id: str, db: Session) -> list[tuple[StrategyVersion, str, dict[str, str]]]:
    versions = (
        db.execute(
            select(StrategyVersion)
            .where(StrategyVersion.strategy_id == strategy_id)
            .order_by(StrategyVersion.version.desc())
        )
        .scalars()
        .all()
    )
    resolved: list[tuple[StrategyVersion, str, dict[str, str]]] = []
    for version in versions:
        version_dir = _resolve_version_dir(strategy_id, version)
        files = _collect_compare_files(version_dir)
        if files:
            resolved.append((version, version_dir, files))
    return resolved


def _has_pending_workspace_changes(current_files: dict[str, str], latest_files: dict[str, str]) -> bool:
    for name in WORKSPACE_VERSIONED_FILES:
        before = latest_files.get(name)
        after = current_files.get(name)
        if before != after:
            return True
    # overview.md can be pending only when latest snapshot also has it.
    if "overview.md" in latest_files and current_files.get("overview.md") != latest_files.get("overview.md"):
        return True
    return False


def _select_workspace_compare_base(
    strategy_id: str,
    db: Session,
    current_files: dict[str, str],
) -> tuple[StrategyVersion | None, dict[str, str], str]:
    versions = _list_confirmed_versions(strategy_id, db)
    if not versions:
        return None, {}, "workspace_only"

    latest_version, _latest_dir, latest_files = versions[0]
    if _has_pending_workspace_changes(current_files, latest_files):
        return latest_version, latest_files, "pending"

    if len(versions) >= 2:
        previous_version, _previous_dir, previous_files = versions[1]
        return previous_version, previous_files, "latest_confirmed"

    return latest_version, latest_files, "latest_only"


def _count_line_changes(base_text: str | None, head_text: str | None) -> tuple[int, int]:
    base_lines = (base_text or "").splitlines()
    head_lines = (head_text or "").splitlines()
    matcher = difflib.SequenceMatcher(a=base_lines, b=head_lines, autojunk=False)
    additions = 0
    deletions = 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag in ("replace", "insert"):
            additions += j2 - j1
        if tag in ("replace", "delete"):
            deletions += i2 - i1
    return additions, deletions


def _build_workspace_compare(strategy_id: str, db: Session) -> dict[str, Any]:
    strategy_dir = os.path.join(settings.workspaces_dir, strategy_id, "strategy")
    current_files = _collect_compare_files(strategy_dir)
    base_version, base_files, compare_mode = _select_workspace_compare_base(strategy_id, db, current_files)

    changed_files: list[dict[str, Any]] = []
    all_names = sorted(set(base_files.keys()) | set(current_files.keys()))
    for name in all_names:
        before = base_files.get(name)
        after = current_files.get(name)
        if before == after:
            continue
        status = "A" if before is None else ("D" if after is None else "M")
        additions, deletions = _count_line_changes(before, after)
        changed_files.append(
            {
                "path": f"strategy/{name}",
                "status": status,
                "additions": additions,
                "deletions": deletions,
            }
        )

    return {
        "head_commit": "workspace",
        "base_commit": base_version.id if base_version else None,
        "subject": (
            (
                f"Latest confirmed version v{base_version.version} -> current workspace"
                if compare_mode in ("pending", "latest_only")
                else f"Previous confirmed version v{base_version.version} -> current workspace"
            )
            if base_version else "No confirmed version available"
        ),
        "files": changed_files,
    }


def _normalize_workspace_compare_path(path: str) -> str:
    normalized = os.path.normpath(path).replace("\\", "/").lstrip("/")
    if normalized.startswith("strategy/"):
        normalized = normalized[len("strategy/") :]
    if not normalized or normalized == ".":
        raise HTTPException(status_code=400, detail="invalid_path")
    if normalized == ".." or normalized.startswith("../") or "/.." in normalized:
        raise HTTPException(status_code=400, detail="invalid_path")
    return normalized


def _build_workspace_diff(strategy_id: str, path: str, db: Session) -> dict[str, Any]:
    normalized_rel = _normalize_workspace_compare_path(path)
    strategy_dir = os.path.join(settings.workspaces_dir, strategy_id, "strategy")
    current_text = _read_text_file_if_exists(os.path.join(strategy_dir, normalized_rel))

    current_files = _collect_compare_files(strategy_dir)
    _base_version, base_files, _compare_mode = _select_workspace_compare_base(strategy_id, db, current_files)
    base_text = base_files.get(normalized_rel)

    if current_text == base_text:
        return {"path": f"strategy/{normalized_rel}", "diff": ""}

    from_file = "/dev/null" if base_text is None else f"a/{normalized_rel}"
    to_file = "/dev/null" if current_text is None else f"b/{normalized_rel}"
    before_lines = [] if base_text is None else base_text.splitlines()
    after_lines = [] if current_text is None else current_text.splitlines()
    diff_lines = list(
        difflib.unified_diff(
            before_lines,
            after_lines,
            fromfile=from_file,
            tofile=to_file,
            lineterm="",
            n=3,
        )
    )
    if diff_lines:
        diff_lines.insert(0, f"diff --git a/{normalized_rel} b/{normalized_rel}")
    diff_text = "\n".join(diff_lines)
    if diff_text:
        diff_text += "\n"
    return {"path": f"strategy/{normalized_rel}", "diff": diff_text}


@router.get("/strategies/{strategy_id}/files")
def get_strategy_files(strategy_id: str, request: Request, db: Session = Depends(get_db)):
    require_strategy_member(request, db, strategy_id)
    strategy = db.get(Strategy, strategy_id)
    if strategy is None:
        raise HTTPException(status_code=404, detail="strategy_not_found")
    return call_worker_rpc("/internal/strategies/files", {"strategy_id": strategy_id})


@router.get("/strategies/{strategy_id}/workspace/compare")
def get_strategy_workspace_compare(strategy_id: str, request: Request, db: Session = Depends(get_db)) -> dict[str, Any]:
    require_strategy_member(request, db, strategy_id)
    strategy = db.get(Strategy, strategy_id)
    if strategy is None:
        raise HTTPException(status_code=404, detail="strategy_not_found")
    return _build_workspace_compare(strategy_id, db)


@router.get("/strategies/{strategy_id}/workspace/compare/diff")
def get_strategy_workspace_compare_diff(
    strategy_id: str,
    request: Request,
    path: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    require_strategy_member(request, db, strategy_id)
    strategy = db.get(Strategy, strategy_id)
    if strategy is None:
        raise HTTPException(status_code=404, detail="strategy_not_found")
    return _build_workspace_diff(strategy_id, path, db)


@router.get("/strategies/{strategy_id}/git/compare")
def get_strategy_git_compare(strategy_id: str, request: Request, db: Session = Depends(get_db)) -> dict[str, Any]:
    require_strategy_member(request, db, strategy_id)
    strategy = db.get(Strategy, strategy_id)
    if strategy is None:
        raise HTTPException(status_code=404, detail="strategy_not_found")
    return call_worker_rpc("/internal/strategies/git/compare", {"strategy_id": strategy_id})


@router.get("/strategies/{strategy_id}/git/compare/diff")
def get_strategy_git_compare_diff(
    strategy_id: str,
    request: Request,
    path: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    require_strategy_member(request, db, strategy_id)
    strategy = db.get(Strategy, strategy_id)
    if strategy is None:
        raise HTTPException(status_code=404, detail="strategy_not_found")

    normalized = os.path.normpath(path).replace("\\", "/")
    if os.path.isabs(normalized) or normalized.startswith("../") or normalized == "..":
        raise HTTPException(status_code=400, detail="invalid_path")
    return call_worker_rpc(
        "/internal/strategies/git/compare/diff",
        {"strategy_id": strategy_id, "path": normalized},
    )
