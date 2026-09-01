from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from typing import Optional


@dataclass
class RepoInfo:
    default_branch: str
    repo_path: str


def _run(cmd: list[str], cwd: Optional[str] = None) -> str:
    p = subprocess.run(
        cmd,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=True,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
    )
    return p.stdout.decode("utf-8", errors="replace")


def _repo_dir(root: str, owner: str, name: str) -> str:
    path = os.path.join(root, "github", owner, name)
    os.makedirs(path, exist_ok=True)
    return path


def _remote_url(owner: str, name: str) -> str:
    return f"https://github.com/{owner}/{name}.git"


def _auth_remote_url(owner: str, name: str, token: str) -> str:
    return f"https://x-access-token:{token}@github.com/{owner}/{name}.git"


def _fetch_with_token(repo_root: str, owner: str, name: str, token: str) -> None:
    public_url = _remote_url(owner, name)
    auth_url = _auth_remote_url(owner, name, token)
    _run(["git", "-C", repo_root, "remote", "set-url", "origin", auth_url])
    try:
        _run(["git", "-C", repo_root, "fetch", "--filter=blob:none", "--prune", "--force", "--depth=1", "origin"])
    finally:
        _run(["git", "-C", repo_root, "remote", "set-url", "origin", public_url])


def clone_or_update(root: str, owner: str, name: str, token: Optional[str] = None) -> RepoInfo:
    repo_root = _repo_dir(root, owner, name)
    git_dir = os.path.join(repo_root, ".git")
    if not os.path.exists(git_dir):
        # Initial partial, shallow clone
        parent = os.path.dirname(repo_root)
        os.makedirs(parent, exist_ok=True)
        url = _auth_remote_url(owner, name, token) if token else _remote_url(owner, name)
        _run(["git", "clone", "--filter=blob:none", "--no-tags", "--depth=1", url, repo_root], cwd=None)
        if token:
            _run(["git", "-C", repo_root, "remote", "set-url", "origin", _remote_url(owner, name)])
    else:
        # Fetch updates
        if token:
            _fetch_with_token(repo_root, owner, name, token)
        else:
            _run(["git", "fetch", "--filter=blob:none", "--prune", "--force", "--depth=1", "origin"], cwd=repo_root)

    # Determine default branch via origin/HEAD
    try:
        out = _run(["git", "symbolic-ref", "refs/remotes/origin/HEAD"], cwd=repo_root).strip()
        # refs/remotes/origin/HEAD -> refs/remotes/origin/<branch>
        default_branch = out.rsplit("/", 1)[-1]
    except Exception:
        default_branch = "main"
    return RepoInfo(default_branch=default_branch, repo_path=repo_root)


def ensure_worktree(repo_path: str, branch: str, token: Optional[str] = None) -> str:
    """Create or update a worktree for a branch under worktrees/<branch>."""
    worktrees_root = os.path.join(repo_path, "worktrees")
    os.makedirs(worktrees_root, exist_ok=True)
    wt_path = os.path.join(worktrees_root, branch)
    if os.path.exists(wt_path):
        # Update
        try:
            if token:
                owner = os.path.basename(os.path.dirname(repo_path))
                name = os.path.basename(repo_path)
                _fetch_with_token(repo_path, owner, name, token)
            else:
                _run(["git", "-C", repo_path, "fetch", "--filter=blob:none", "--prune", "--force", "--depth=1", "origin"])
            _run(["git", "-C", wt_path, "reset", "--hard", f"origin/{branch}"])
        except Exception:
            # If branch missing remotely, keep as is
            pass
        return wt_path
    # Create
    # Make sure branch exists locally
    try:
        _run(["git", "-C", repo_path, "show-ref", f"refs/heads/{branch}"])
    except Exception:
        _run(["git", "-C", repo_path, "branch", branch, f"origin/{branch}"])
    _run(["git", "-C", repo_path, "worktree", "add", "-f", wt_path, branch])
    return wt_path
