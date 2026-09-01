from __future__ import annotations

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.settings import settings


def _parse_admin_emails(raw: str | None) -> set[str]:
    if raw is None:
        return set()
    s = str(raw).strip()
    if not s:
        return set()
    if s.startswith("["):
        try:
            import json

            arr = json.loads(s)
            if isinstance(arr, list):
                return {str(x).strip().lower() for x in arr if str(x).strip()}
        except Exception:
            pass
    parts = [p.strip().lower() for p in s.replace("\n", ",").replace(" ", ",").split(",")]
    return {p for p in parts if p}


def is_admin_request(request: Request, *, db: Session) -> bool:
    """Temporary admin gate.

    - If X-Admin-Key matches APP_ADMIN_API_KEY, allow.
    - Else require a logged-in user whose email is in APP_ADMIN_EMAILS.
    """
    admin_header = request.headers.get("X-Admin-Key")
    if admin_header and settings.admin_api_key:
        return admin_header == settings.admin_api_key

    user = get_current_user(request, db)
    email = (user.email or "").strip().lower()
    allow = _parse_admin_emails(settings.admin_emails)
    return bool(email and email in allow)


def require_admin(request: Request, *, db: Session) -> None:
    if not is_admin_request(request, db=db):
        raise HTTPException(status_code=403, detail="admin_required")
