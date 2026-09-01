from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode, urlparse
import logging
import secrets
import requests

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import SESSION_COOKIE_NAME, create_session, get_current_user
from app.admin import is_admin_request
from app.deps import get_db
from app.schemas import (
    AuthMeResponse,
    InviteCreateRequest,
    InviteResponse,
    InviteValidateRequest,
    InviteValidateResponse,
    OAuthStartRequest,
    OAuthStartResponse,
)
from app.settings import settings
from control_plane.models import InviteCode, OAuthAccount, PendingOAuth, User, UserSession

router = APIRouter()
logger = logging.getLogger(__name__)

DEBUG_INVITE_CODE = "LOCAL_DEBUG_INVITE"


def _is_local_dev() -> bool:
    host = urlparse(settings.public_base_url).hostname
    return host in {"localhost", "127.0.0.1", "0.0.0.0"}


def _is_debug_invite(code: str) -> bool:
    return _is_local_dev() and code == DEBUG_INVITE_CODE


def _get_or_create_debug_user(db: Session) -> User:
    email = "dev@local.test"
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user is None:
        user = User(email=email, name="Local Dev")
        db.add(user)
        db.flush()
    return user


def _get_invite(db: Session, code: str) -> InviteCode:
    invite = db.execute(select(InviteCode).where(InviteCode.code == code)).scalar_one_or_none()
    if invite is None:
        raise HTTPException(status_code=400, detail="invalid_invite")
    if invite.expires_at and invite.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="invite_expired")
    if invite.used_count >= invite.max_uses:
        raise HTTPException(status_code=400, detail="invite_exhausted")
    return invite


def _consume_invite(invite: InviteCode) -> None:
    invite.used_count += 1


def _build_google_auth_url(state: str) -> str:
    if not settings.google_oauth_client_id or not settings.google_oauth_redirect_uri:
        raise HTTPException(status_code=500, detail="google_oauth_not_configured")
    query = urlencode(
        {
            "client_id": settings.google_oauth_client_id,
            "redirect_uri": settings.google_oauth_redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "prompt": "consent",
        }
    )
    return f"https://accounts.google.com/o/oauth2/v2/auth?{query}"


def _exchange_google_code(code: str) -> dict:
    if not settings.google_oauth_client_id or not settings.google_oauth_client_secret or not settings.google_oauth_redirect_uri:
        raise HTTPException(status_code=500, detail="google_oauth_not_configured")
    token_resp = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": settings.google_oauth_client_id,
            "client_secret": settings.google_oauth_client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": settings.google_oauth_redirect_uri,
        },
        timeout=20,
    )
    token_resp.raise_for_status()
    token_data = token_resp.json()
    access_token = token_data.get("access_token")
    if not access_token:
        raise HTTPException(status_code=400, detail="google_access_token_missing")
    user_resp = requests.get(
        "https://openidconnect.googleapis.com/v1/userinfo",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=20,
    )
    user_resp.raise_for_status()
    user_data = user_resp.json()
    if _is_local_dev():
        logger.info(
            "google_oauth_userinfo email=%s verified=%s",
            user_data.get("email"),
            bool(user_data.get("email_verified")),
        )
    return {
        "provider_user_id": user_data.get("sub"),
        "email": user_data.get("email"),
        "email_verified": bool(user_data.get("email_verified")),
        "name": user_data.get("name"),
        "avatar_url": user_data.get("picture"),
    }


def _build_github_auth_url(state: str) -> str:
    if not settings.github_oauth_client_id or not settings.github_oauth_redirect_uri:
        raise HTTPException(status_code=500, detail="github_oauth_not_configured")
    query = urlencode(
        {
            "client_id": settings.github_oauth_client_id,
            "redirect_uri": settings.github_oauth_redirect_uri,
            "state": state,
            "scope": "read:user user:email",
        }
    )
    return f"https://github.com/login/oauth/authorize?{query}"


def _exchange_github_code(code: str, state: str) -> dict:
    if not settings.github_oauth_client_id or not settings.github_oauth_client_secret or not settings.github_oauth_redirect_uri:
        raise HTTPException(status_code=500, detail="github_oauth_not_configured")
    token_resp = requests.post(
        "https://github.com/login/oauth/access_token",
        headers={"Accept": "application/json"},
        data={
            "client_id": settings.github_oauth_client_id,
            "client_secret": settings.github_oauth_client_secret,
            "code": code,
            "redirect_uri": settings.github_oauth_redirect_uri,
            "state": state,
        },
        timeout=20,
    )
    token_resp.raise_for_status()
    token_data = token_resp.json()
    access_token = token_data.get("access_token")
    if not access_token:
        raise HTTPException(status_code=400, detail="github_access_token_missing")

    user_resp = requests.get(
        "https://api.github.com/user",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=20,
    )
    user_resp.raise_for_status()
    user_data = user_resp.json()

    email = user_data.get("email")
    if not email:
        emails_resp = requests.get(
            "https://api.github.com/user/emails",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=20,
        )
        emails_resp.raise_for_status()
        emails = emails_resp.json() or []
        primary_email = next((item for item in emails if item.get("primary") and item.get("verified")), None)
        email = (primary_email or emails[0]).get("email") if emails else None

    return {
        "provider_user_id": str(user_data.get("id")),
        "email": email,
        "name": user_data.get("name") or user_data.get("login"),
        "avatar_url": user_data.get("avatar_url"),
    }


@router.get("/auth/me", response_model=AuthMeResponse)
def auth_me(request: Request, db: Session = Depends(get_db)) -> AuthMeResponse:
    user = get_current_user(request, db)
    return AuthMeResponse(user=user, is_admin=is_admin_request(request, db=db))


@router.post("/auth/invites/validate", response_model=InviteValidateResponse)
def validate_invite(req: InviteValidateRequest, db: Session = Depends(get_db)) -> InviteValidateResponse:
    code = req.code.strip()
    if _is_debug_invite(code):
        return InviteValidateResponse(valid=True)
    _get_invite(db, code)
    return InviteValidateResponse(valid=True)


@router.post("/auth/invites", response_model=InviteResponse)
def create_invite(
    req: InviteCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> InviteResponse:
    existing_user = db.execute(select(User).limit(1)).scalar_one_or_none()
    user = None
    if existing_user is not None:
        user = get_current_user(request, db)
    code = (req.code or secrets.token_urlsafe(6)).strip()
    if not code:
        raise HTTPException(status_code=400, detail="invalid_invite_code")
    existing = db.execute(select(InviteCode).where(InviteCode.code == code)).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="invite_code_exists")
    invite = InviteCode(
        code=code,
        max_uses=req.max_uses or 1,
        expires_at=req.expires_at,
        created_by_user_id=user.id if user else None,
    )
    db.add(invite)
    db.commit()
    db.refresh(invite)
    return invite


@router.post("/auth/oauth/{provider}/start", response_model=OAuthStartResponse)
def oauth_start(
    provider: str,
    req: OAuthStartRequest,
    response: Response,
    db: Session = Depends(get_db),
) -> OAuthStartResponse:
    invite_code = req.invite_code.strip()
    if _is_debug_invite(invite_code):
        user = _get_or_create_debug_user(db)
        token = create_session(db, user)
        db.commit()
        response.set_cookie(
            SESSION_COOKIE_NAME,
            token,
            httponly=True,
            samesite="lax",
            secure=False,
            max_age=settings.auth_session_days * 24 * 60 * 60,
        )
        redirect_path = req.redirect_path or "/"
        return OAuthStartResponse(auth_url=f"{settings.public_base_url}{redirect_path}")

    # Validate invite code only if provided (for registration)
    # If empty, allow login attempt (will be validated in callback for new users)
    invite_id = None
    if invite_code:
        invite = _get_invite(db, invite_code)
        invite_id = invite.id

    state = secrets.token_urlsafe(32)
    redirect_path = req.redirect_path or "/"
    pending = PendingOAuth(
        provider=provider,
        state=state,
        invite_id=invite_id,
        redirect_path=redirect_path,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
    )
    db.add(pending)
    db.commit()

    if provider == "google":
        url = _build_google_auth_url(state)
    elif provider == "github":
        url = _build_github_auth_url(state)
    else:
        raise HTTPException(status_code=400, detail="unsupported_provider")

    return OAuthStartResponse(auth_url=url)


@router.get("/auth/oauth/{provider}/callback")
def oauth_callback(
    provider: str,
    request: Request,
    response: Response,
    code: str,
    state: str,
    db: Session = Depends(get_db),
) -> Response:
    pending = db.execute(
        select(PendingOAuth)
        .where(PendingOAuth.state == state)
        .where(PendingOAuth.provider == provider)
    ).scalar_one_or_none()
    if pending is None:
        # Redirect to frontend with error
        error_url = f"{settings.public_base_url}/auth/error?error=invalid_state"
        response = Response(status_code=302)
        response.headers["Location"] = error_url
        return response
    if pending.expires_at < datetime.now(timezone.utc):
        error_url = f"{settings.public_base_url}/auth/error?error=state_expired"
        response = Response(status_code=302)
        response.headers["Location"] = error_url
        return response

    if provider == "google":
        oauth_profile = _exchange_google_code(code)
    elif provider == "github":
        oauth_profile = _exchange_github_code(code, state)
    else:
        error_url = f"{settings.public_base_url}/auth/error?error=unsupported_provider"
        response = Response(status_code=302)
        response.headers["Location"] = error_url
        return response

    provider_user_id = oauth_profile.get("provider_user_id")
    if not provider_user_id:
        error_url = f"{settings.public_base_url}/auth/error?error=provider_user_id_missing"
        response = Response(status_code=302)
        response.headers["Location"] = error_url
        return response

    account = db.execute(
        select(OAuthAccount)
        .where(OAuthAccount.provider == provider)
        .where(OAuthAccount.provider_user_id == provider_user_id)
    ).scalar_one_or_none()

    if account is None:
        # Auto-merge: if verified email matches an existing user, link account
        email = (oauth_profile.get("email") or "").strip().lower()
        email_verified = bool(oauth_profile.get("email_verified")) if provider == "google" else bool(email)
        existing_user = None
        if email and email_verified:
            existing_user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()

        if existing_user is not None:
            user = existing_user
            account = OAuthAccount(
                provider=provider,
                provider_user_id=provider_user_id,
                user_id=user.id,
                email=oauth_profile.get("email"),
                name=oauth_profile.get("name"),
                avatar_url=oauth_profile.get("avatar_url"),
            )
            db.add(account)
        else:
            # New user registration - invite code is required
            if pending.invite_id is None:
                # Redirect to frontend with registration error
                error_url = f"{settings.public_base_url}/auth/error?error=registration_required&provider={provider}"
                response = Response(status_code=302)
                response.headers["Location"] = error_url
                return response

            invite = db.get(InviteCode, pending.invite_id)
            if invite is None:
                error_url = f"{settings.public_base_url}/auth/error?error=invite_missing"
                response = Response(status_code=302)
                response.headers["Location"] = error_url
                return response
            _get_invite(db, invite.code)
            _consume_invite(invite)

            user = User(
                email=oauth_profile.get("email"),
                name=oauth_profile.get("name"),
                avatar_url=oauth_profile.get("avatar_url"),
            )
            db.add(user)
            db.flush()

            account = OAuthAccount(
                provider=provider,
                provider_user_id=provider_user_id,
                user_id=user.id,
                email=oauth_profile.get("email"),
                name=oauth_profile.get("name"),
                avatar_url=oauth_profile.get("avatar_url"),
            )
            db.add(account)
    else:
        # Existing user login - no invite code needed
        user = db.get(User, account.user_id)
        if user is None:
            error_url = f"{settings.public_base_url}/auth/error?error=user_missing"
            response = Response(status_code=302)
            response.headers["Location"] = error_url
            return response

    token = create_session(db, user)
    db.delete(pending)
    db.commit()

    redirect_url = f"{settings.public_base_url}{pending.redirect_path}"
    response = Response(status_code=302)
    response.headers["Location"] = redirect_url
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        httponly=True,
        samesite="lax",
        secure=False,
        max_age=settings.auth_session_days * 24 * 60 * 60,
    )
    return response


@router.post("/auth/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)) -> dict:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token:
        session = db.execute(select(UserSession).where(UserSession.token == token)).scalar_one_or_none()
        if session:
            db.delete(session)
    response.delete_cookie(SESSION_COOKIE_NAME)
    db.commit()
    return {"ok": True}
