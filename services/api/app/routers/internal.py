from __future__ import annotations

from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from control_plane.enums import SandboxStatus
from control_plane.models import SandboxSession
from app.deps import get_db

router = APIRouter()


@router.get("/sandbox/forward-auth")
def sandbox_forward_auth(request: Request, response: Response, db: Session = Depends(get_db)) -> dict:
    """Traefik forward-auth endpoint.

    We validate token embedded in the URL path against the sandbox session secret.
    """
    uri = request.headers.get("X-Forwarded-Uri") or ""
    if not uri:
        raise HTTPException(status_code=401, detail="missing_forwarded_uri")

    split = urlsplit(uri)
    path = split.path or ""

    # expected: /sandbox/<session_id>/<token>/...
    parts = [p for p in path.split("/") if p]
    if len(parts) < 3 or parts[0] != "sandbox":
        raise HTTPException(status_code=401, detail="invalid_path")
    session_id = parts[1]
    token = parts[2]

    session = db.get(SandboxSession, session_id)
    if session is None:
        raise HTTPException(status_code=401, detail="invalid_session")
    if session.status != SandboxStatus.RUNNING:
        raise HTTPException(status_code=401, detail="session_not_running")
    if session.secret_token != token:
        raise HTTPException(status_code=401, detail="invalid_token")

    response.headers["X-Sandbox-Session-Id"] = session_id
    return {"ok": True}

