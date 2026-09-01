from __future__ import annotations

import json
import os

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from control_plane.enums import ChatStatus, JobType, StrategyRole
from control_plane.models import Job, Repository, Strategy, StrategyMember
from control_plane.queue import QUEUE_NAME
from app.auth import get_current_user, require_strategy_member
from app.deps import get_db
from app.schemas import RepoImportRequest, RepoResponse, StrategyResponse, TriggerJobResponse
from app.settings import settings


router = APIRouter()
_SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "node_modules",
    "dist",
    "build",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".next",
    ".turbo",
}


def _repos_root() -> str:
    base = settings.repos_dir or os.path.join(settings.workspaces_dir, "repos")
    os.makedirs(base, exist_ok=True)
    return base


def _repo_worktree_path(repo: Repository, branch: str) -> str:
    return os.path.join(_repos_root(), "github", repo.owner, repo.name, "worktrees", branch)


def _resolve_repo_branch(repo: Repository) -> str | None:
    if repo.tracked_branches:
        return repo.tracked_branches[0]
    if repo.default_branch:
        return repo.default_branch
    return None


def _assert_repo_strategy_member(request: Request, db: Session, repo: Repository) -> Strategy:
    strategy = db.query(Strategy).filter(Strategy.repo_id == repo.id).one_or_none()
    if strategy is None:
        raise HTTPException(status_code=404, detail="strategy_not_found")
    require_strategy_member(request, db, strategy.id)
    return strategy


def _list_repo_files(root: str, max_entries: int) -> tuple[list[dict[str, str | int]], bool]:
    entries: list[dict[str, str | int]] = []
    truncated = False
    for current_root, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
        for name in files:
            if len(entries) >= max_entries:
                truncated = True
                break
            rel_path = os.path.relpath(os.path.join(current_root, name), root)
            try:
                size = os.path.getsize(os.path.join(current_root, name))
            except OSError:
                size = 0
            entries.append({"path": rel_path, "type": "file", "size": size})
        if truncated:
            break
    return entries, truncated


def _read_repo_file(root: str, rel_path: str, max_bytes: int) -> str:
    normalized = os.path.normpath(rel_path).lstrip(os.sep)
    abs_path = os.path.abspath(os.path.join(root, normalized))
    root_abs = os.path.abspath(root)
    if not abs_path.startswith(root_abs + os.sep) and abs_path != root_abs:
        raise HTTPException(status_code=400, detail="invalid_path")
    if not os.path.exists(abs_path) or not os.path.isfile(abs_path):
        raise HTTPException(status_code=404, detail="file_not_found")
    if os.path.getsize(abs_path) > max_bytes:
        raise HTTPException(status_code=413, detail="file_too_large")
    with open(abs_path, "rb") as f:
        raw = f.read(max_bytes + 1)
    if b"\x00" in raw:
        raise HTTPException(status_code=415, detail="binary_file")
    return raw.decode("utf-8", errors="replace")


@router.post("/repos/import", response_model=TriggerJobResponse)
def import_repo(req: RepoImportRequest, request: Request, db: Session = Depends(get_db)) -> TriggerJobResponse:
    user = get_current_user(request, db)
    # Basic upsert by (owner, name)
    repo = (
        db.query(Repository)
        .filter(Repository.provider == "github", Repository.owner == req.owner, Repository.name == req.name)
        .one_or_none()
    )
    if repo is None:
        repo = Repository(
            provider="github",
            owner=req.owner,
            name=req.name,
            github_installation_id=req.installation_id,  # Store GitHub's installation ID
            tracked_branches=req.branches or None,
        )
        db.add(repo)
        db.flush()
    else:
        # Update tracked branches if provided
        if req.branches:
            repo.tracked_branches = req.branches
        if req.installation_id:
            repo.github_installation_id = req.installation_id  # Store GitHub's installation ID
        db.flush()

    # Create or find linked Strategy
    strategy = (
        db.query(Strategy)
        .filter(Strategy.repo_id == repo.id)
        .one_or_none()
    )
    if strategy is None:
        # Create a new strategy linked to this repo
        strategy = Strategy(
            name=f"{req.owner}/{req.name}",  # Will be updated by worker with AI-generated name
            repo_id=repo.id,
            chat_status=ChatStatus.DONE,  # Skip chat for imported repos
        )
        db.add(strategy)
        db.flush()

    # Ensure importing user is a member of the strategy
    member = (
        db.query(StrategyMember)
        .filter(StrategyMember.strategy_id == strategy.id, StrategyMember.user_id == user.id)
        .one_or_none()
    )
    if member is None:
        db.add(StrategyMember(strategy_id=strategy.id, user_id=user.id, role=StrategyRole.ADMIN))
        db.flush()

    # Enqueue a repo import job
    job = Job(type=JobType.REPO_IMPORT, payload={
        "repo_id": repo.id,
        "strategy_id": strategy.id,  # Include strategy_id for worker to update
        "provider": "github",
        "owner": req.owner,
        "name": req.name,
        "branches": req.branches or [],  # empty => default only
        "installation_id": req.installation_id,  # GitHub's installation ID for API calls
        "repos_root": _repos_root(),
        "search_index_path": settings.search_index_path or os.path.join(settings.workspaces_dir, "search", "search.sqlite"),
    })
    db.add(job)
    db.flush()

    # Push to queue
    rds = request.app.state.redis
    rds.rpush(QUEUE_NAME, json.dumps({"job_id": job.id}))

    db.commit()
    
    # Refresh to get complete objects
    db.refresh(job)
    db.refresh(strategy)
    
    return TriggerJobResponse(job=job, strategy=StrategyResponse.model_validate(strategy))


@router.get("/repos", response_model=list[RepoResponse])
def list_repos(db: Session = Depends(get_db)) -> list[RepoResponse]:
    items = (
        db.query(Repository)
        .filter(Repository.provider == "github")
        .order_by(Repository.created_at.desc())
        .all()
    )
    return items


@router.get("/repos/{repo_id}", response_model=RepoResponse)
def get_repo(repo_id: str, request: Request, db: Session = Depends(get_db)) -> RepoResponse:
    repo = db.get(Repository, repo_id)
    if repo is None:
        raise HTTPException(status_code=404, detail="repo_not_found")
    _assert_repo_strategy_member(request, db, repo)
    return repo


@router.get("/repos/{repo_id}/tree")
def get_repo_tree(
    repo_id: str,
    request: Request,
    db: Session = Depends(get_db),
    branch: str | None = None,
    max_entries: int = 2000,
):
    repo = db.get(Repository, repo_id)
    if repo is None:
        raise HTTPException(status_code=404, detail="repo_not_found")
    _assert_repo_strategy_member(request, db, repo)
    branch_name = branch or _resolve_repo_branch(repo)
    if not branch_name:
        raise HTTPException(status_code=409, detail="repo_branch_unknown")
    worktree_path = _repo_worktree_path(repo, branch_name)
    if not os.path.isdir(worktree_path):
        raise HTTPException(status_code=409, detail="repo_not_synced")
    entries, truncated = _list_repo_files(worktree_path, max_entries=max_entries)
    return {"branch": branch_name, "entries": entries, "truncated": truncated}


@router.get("/repos/{repo_id}/file")
def get_repo_file(
    repo_id: str,
    request: Request,
    path: str,
    db: Session = Depends(get_db),
    branch: str | None = None,
    max_bytes: int = 200_000,
):
    repo = db.get(Repository, repo_id)
    if repo is None:
        raise HTTPException(status_code=404, detail="repo_not_found")
    _assert_repo_strategy_member(request, db, repo)
    branch_name = branch or _resolve_repo_branch(repo)
    if not branch_name:
        raise HTTPException(status_code=409, detail="repo_branch_unknown")
    worktree_path = _repo_worktree_path(repo, branch_name)
    if not os.path.isdir(worktree_path):
        raise HTTPException(status_code=409, detail="repo_not_synced")
    content = _read_repo_file(worktree_path, path, max_bytes=max_bytes)
    return {"path": path, "branch": branch_name, "content": content}


@router.post("/repos/{repo_id}/sync", response_model=TriggerJobResponse)
def sync_repo(repo_id: str, request: Request, db: Session = Depends(get_db)) -> TriggerJobResponse:
    repo = db.get(Repository, repo_id)
    if repo is None:
        raise HTTPException(status_code=404, detail="repo_not_found")

    job = Job(
        type=JobType.REPO_SYNC,
        payload={
            "repo_id": repo.id,
            "provider": repo.provider,
            "owner": repo.owner,
            "name": repo.name,
            "branches": repo.tracked_branches or [],
            "installation_id": repo.github_installation_id,
            "repos_root": _repos_root(),
            "search_index_path": settings.search_index_path or os.path.join(settings.workspaces_dir, "search", "search.sqlite"),
        },
    )
    db.add(job)
    db.flush()
    rds = request.app.state.redis
    rds.rpush(QUEUE_NAME, json.dumps({"job_id": job.id}))
    db.commit()
    return TriggerJobResponse(job=job)
