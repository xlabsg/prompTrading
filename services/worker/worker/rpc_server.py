from __future__ import annotations

import os
import subprocess
from typing import Any, Optional

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from control_plane.workspaces import git_commit, init_git_repo, restore_version_to_current_strategy


class RpcSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

    app_workspaces_dir: str = "/workspaces"
    worker_rpc_token: Optional[str] = None


settings = RpcSettings()
app = FastAPI(title="Worker Internal RPC", version="0.1.0")


class StrategyRequest(BaseModel):
    strategy_id: str = Field(min_length=1)


class StrategyDiffRequest(BaseModel):
    strategy_id: str = Field(min_length=1)
    path: str = Field(min_length=1)


class StrategyRestoreRequest(BaseModel):
    strategy_id: str = Field(min_length=1)
    version_id: str = Field(min_length=1)
    prompt: str = ""


def _verify_token(x_worker_rpc_token: Optional[str]) -> None:
    expected = (settings.worker_rpc_token or "").strip()
    if not expected:
        return
    provided = (x_worker_rpc_token or "").strip()
    if not provided:
        raise HTTPException(status_code=401, detail="missing_worker_rpc_token")
    if provided != expected:
        raise HTTPException(status_code=403, detail="invalid_worker_rpc_token")


def _strategy_git_dir(strategy_id: str) -> str:
    return os.path.join(settings.app_workspaces_dir, strategy_id, "strategy")


def _run_git(strategy_dir: str, args: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=strategy_dir,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail="git_not_installed") from exc


def _latest_commit_compare(strategy_dir: str) -> dict[str, Any]:
    head_res = _run_git(strategy_dir, ["rev-parse", "--verify", "HEAD"])
    if head_res.returncode != 0:
        return {
            "head_commit": None,
            "base_commit": None,
            "subject": "",
            "files": [],
        }

    head_commit = head_res.stdout.strip()
    parent_res = _run_git(strategy_dir, ["rev-list", "--parents", "-n", "1", "HEAD"])
    if parent_res.returncode != 0:
        raise HTTPException(status_code=500, detail=f"git_parent_failed:{parent_res.stderr.strip()}")
    parent_parts = parent_res.stdout.strip().split()
    base_commit = parent_parts[1] if len(parent_parts) > 1 else None

    subject_res = _run_git(strategy_dir, ["show", "-s", "--format=%s", "HEAD"])
    if subject_res.returncode != 0:
        raise HTTPException(status_code=500, detail=f"git_subject_failed:{subject_res.stderr.strip()}")
    subject = subject_res.stdout.strip()

    status_res = _run_git(strategy_dir, ["show", "--name-status", "--format=", "--no-renames", "HEAD"])
    if status_res.returncode != 0:
        raise HTTPException(status_code=500, detail=f"git_name_status_failed:{status_res.stderr.strip()}")

    numstat_res = _run_git(strategy_dir, ["show", "--numstat", "--format=", "--no-renames", "HEAD"])
    if numstat_res.returncode != 0:
        raise HTTPException(status_code=500, detail=f"git_numstat_failed:{numstat_res.stderr.strip()}")

    stats_by_path: dict[str, tuple[int, int]] = {}
    for raw in numstat_res.stdout.splitlines():
        parts = raw.split("\t")
        if len(parts) < 3:
            continue
        add_s, del_s, path = parts[0], parts[1], parts[2].strip()
        additions = 0 if add_s == "-" else int(add_s or 0)
        deletions = 0 if del_s == "-" else int(del_s or 0)
        stats_by_path[path] = (additions, deletions)

    files: list[dict[str, Any]] = []
    for raw in status_res.stdout.splitlines():
        parts = raw.split("\t")
        if len(parts) < 2:
            continue
        status_token = parts[0].strip()
        path = parts[-1].strip()
        additions, deletions = stats_by_path.get(path, (0, 0))
        files.append(
            {
                "path": path,
                "status": status_token[:1] if status_token else "M",
                "additions": additions,
                "deletions": deletions,
            }
        )

    return {
        "head_commit": head_commit,
        "base_commit": base_commit,
        "subject": subject,
        "files": files,
    }


def _list_strategy_files(strategy_dir: str) -> dict[str, Any]:
    files: list[dict[str, str]] = []
    entries = (
        ("strategy.py", "strategy/strategy.py"),
        ("strategy_spec.yaml", "strategy/strategy_spec.yaml"),
        ("overview.md", "strategy/overview.md"),
        ("params_schema.json", "strategy/params_schema.json"),
        ("strategy_meta.json", "strategy/strategy_meta.json"),
        ("strategy_protocol.json", "strategy/strategy_protocol.json"),
        ("strategy_live.py", "strategy/strategy_live.py"),
    )
    for name, path in entries:
        full_path = os.path.join(strategy_dir, name)
        if not os.path.isfile(full_path):
            continue
        with open(full_path, "r", encoding="utf-8") as f:
            files.append(
                {
                    "name": name,
                    "path": path,
                    "type": "file",
                    "content": f.read(),
                }
            )
    return {"files": files}


@app.post("/internal/strategies/files")
def strategy_files(
    req: StrategyRequest,
    x_worker_rpc_token: Optional[str] = Header(default=None, alias="X-Worker-RPC-Token"),
) -> dict[str, Any]:
    _verify_token(x_worker_rpc_token)
    strategy_dir = _strategy_git_dir(req.strategy_id)
    if not os.path.isdir(strategy_dir):
        raise HTTPException(status_code=404, detail="strategy_workspace_not_found")
    return _list_strategy_files(strategy_dir)


@app.post("/internal/strategies/git/compare")
def strategy_git_compare(
    req: StrategyRequest,
    x_worker_rpc_token: Optional[str] = Header(default=None, alias="X-Worker-RPC-Token"),
) -> dict[str, Any]:
    _verify_token(x_worker_rpc_token)
    strategy_dir = _strategy_git_dir(req.strategy_id)
    if not os.path.isdir(strategy_dir):
        raise HTTPException(status_code=404, detail="strategy_workspace_not_found")
    return _latest_commit_compare(strategy_dir)


@app.post("/internal/strategies/git/compare/diff")
def strategy_git_compare_diff(
    req: StrategyDiffRequest,
    x_worker_rpc_token: Optional[str] = Header(default=None, alias="X-Worker-RPC-Token"),
) -> dict[str, Any]:
    _verify_token(x_worker_rpc_token)
    normalized = os.path.normpath(req.path).replace("\\", "/")
    if os.path.isabs(normalized) or normalized.startswith("../") or normalized == "..":
        raise HTTPException(status_code=400, detail="invalid_path")

    strategy_dir = _strategy_git_dir(req.strategy_id)
    if not os.path.isdir(strategy_dir):
        raise HTTPException(status_code=404, detail="strategy_workspace_not_found")

    head_res = _run_git(strategy_dir, ["rev-parse", "--verify", "HEAD"])
    if head_res.returncode != 0:
        return {"path": normalized, "diff": ""}

    diff_res = _run_git(
        strategy_dir,
        ["show", "--format=", "--no-renames", "--unified=3", "HEAD", "--", normalized],
    )
    if diff_res.returncode != 0:
        raise HTTPException(status_code=500, detail=f"git_diff_failed:{diff_res.stderr.strip()}")

    return {"path": normalized, "diff": diff_res.stdout}


@app.post("/internal/strategies/versions/restore")
def strategy_restore_version(
    req: StrategyRestoreRequest,
    x_worker_rpc_token: Optional[str] = Header(default=None, alias="X-Worker-RPC-Token"),
) -> dict[str, Any]:
    _verify_token(x_worker_rpc_token)
    strategy_dir = _strategy_git_dir(req.strategy_id)
    try:
        restore_version_to_current_strategy(settings.app_workspaces_dir, req.strategy_id, req.version_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"version_files_missing:{exc}") from exc

    init_git_repo(strategy_dir)
    msg = f"Restore version: {req.version_id}"
    if req.prompt:
        msg = f"{msg} ({req.prompt[:60]})"
    sha = git_commit(strategy_dir, msg)
    return {"status": "ok", "commit": sha}
