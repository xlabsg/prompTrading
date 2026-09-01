from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import RedirectResponse

from app.github_app import list_installations, list_installation_repos
from app.settings import settings


router = APIRouter()


@router.get("/github/install-url")
def get_install_url() -> dict:
    """Get the GitHub App installation URL with redirect back to our app."""
    app_slug = settings.github_app_slug
    public_base_url = settings.public_base_url.rstrip("/")
    
    if app_slug:
        # Include state parameter with redirect info for the callback
        # GitHub will redirect to our callback URL after installation
        callback_url = f"{public_base_url}/api/github/callback"
        install_url = f"https://github.com/apps/{app_slug}/installations/new"
    else:
        # Fallback to settings page if slug not configured
        install_url = "https://github.com/settings/installations"

    return {
        "install_url": install_url,
        "settings_url": "https://github.com/settings/installations"
    }


@router.get("/github/callback")
def github_app_callback(
    installation_id: int | None = Query(default=None),
    setup_action: str | None = Query(default=None),
) -> RedirectResponse:
    """Handle GitHub App installation callback.
    
    After a user installs/updates the GitHub App, GitHub redirects here with:
    - installation_id: The ID of the newly created/updated installation
    - setup_action: 'install', 'update', or 'request' (for permission requests)
    
    We redirect the user back to the frontend dashboard.
    """
    public_base_url = settings.public_base_url.rstrip("/")
    
    # Redirect back to the frontend with the installation info
    redirect_url = f"{public_base_url}/"
    if installation_id:
        redirect_url = f"{public_base_url}/?github_installation_id={installation_id}"
        if setup_action:
            redirect_url += f"&setup_action={setup_action}"
    
    return RedirectResponse(url=redirect_url, status_code=302)


@router.get("/github/installations")
def get_installations() -> list[dict]:
    try:
        return list_installations()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/github/installation/{installation_id}/repos")
def get_installation_repos(installation_id: str) -> list[dict]:
    try:
        return list_installation_repos(installation_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

