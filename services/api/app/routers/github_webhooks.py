from __future__ import annotations

import hmac
import hashlib
import json
import os
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Request, Depends
from sqlalchemy.orm import Session

from control_plane.enums import JobType
from control_plane.models import Job, Repository
from control_plane.queue import QUEUE_NAME, enqueue_job
from app.deps import get_db
from app.settings import settings


router = APIRouter()


def _verify_signature(secret: str, body: bytes, signature: str) -> bool:
    try:
        sha_name, sig = signature.split("=", 1)
        if sha_name != "sha256":
            return False
    except Exception:
        return False
    mac = hmac.new(secret.encode("utf-8"), msg=body, digestmod=hashlib.sha256)
    return hmac.compare_digest(mac.hexdigest(), sig)


@router.post("/webhooks/github")
async def github_webhook(
    request: Request,
    x_hub_signature_256: Optional[str] = Header(default=None),
    x_github_event: Optional[str] = Header(default=None),
    x_github_delivery: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
) -> dict:
    body = await request.body()
    secret = settings.github_app_webhook_secret
    if secret:
        if not x_hub_signature_256 or not _verify_signature(secret, body, x_hub_signature_256):
            raise HTTPException(status_code=401, detail="invalid_signature")
    try:
        payload = json.loads(body.decode("utf-8"))
    except Exception:
        payload = {}

    event = x_github_event or ""
    if event == "ping":
        return {"ok": True, "event": event, "delivery_id": x_github_delivery or "", "received": True}

    repo_info = payload.get("repository") or {}
    owner_info = repo_info.get("owner") or {}
    owner = owner_info.get("login")
    name = repo_info.get("name")
    provider_repo_id = repo_info.get("id")
    installation = payload.get("installation") or {}
    installation_id = installation.get("id")

    repo = None
    if provider_repo_id:
        repo = db.query(Repository).filter(Repository.provider_repo_id == str(provider_repo_id)).one_or_none()
    if repo is None and owner and name:
        repo = (
            db.query(Repository)
            .filter(Repository.provider == "github", Repository.owner == owner, Repository.name == name)
            .one_or_none()
        )
    if repo is None:
        return {"ok": True, "event": event, "delivery_id": x_github_delivery or "", "received": bool(payload)}

    if provider_repo_id and not repo.provider_repo_id:
        repo.provider_repo_id = str(provider_repo_id)
    if installation_id:
        repo.github_installation_id = str(installation_id)
    db.flush()

    branches: list[str] = []
    if event == "push":
        ref = payload.get("ref") or ""
        if ref.startswith("refs/heads/"):
            branches = [ref.split("/", 2)[2]]

    job = Job(
        type=JobType.REPO_SYNC,
        payload={
            "repo_id": repo.id,
            "provider": "github",
            "owner": repo.owner,
            "name": repo.name,
            "branches": branches,
            "installation_id": repo.github_installation_id,
            "repos_root": settings.repos_dir or os.path.join(settings.workspaces_dir, "repos"),
        },
    )
    db.add(job)
    db.flush()
    rds = getattr(request.app.state, "redis", None)
    enqueue_job(settings.workspaces_dir, job.id, job.type, job.payload, redis_client=rds)

    return {"ok": True, "event": event, "delivery_id": x_github_delivery or "", "received": bool(payload)}
