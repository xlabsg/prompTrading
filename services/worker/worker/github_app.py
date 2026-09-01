from __future__ import annotations

import os
import time

import jwt
import requests

from worker.settings import settings


def _load_private_key() -> str:
    """Load the GitHub App private key from settings.
    
    The key can be:
    1. A file path to a PEM file
    2. The PEM content directly (with actual newlines)
    3. The PEM content with escaped \\n (will be converted to actual newlines)
    """
    key = settings.github_app_private_key
    if not key:
        raise RuntimeError("github_app_private_key_missing")
    if os.path.isfile(key):
        with open(key, "r", encoding="utf-8") as f:
            return f.read()
    # Handle escaped newlines in environment variable
    if "\\n" in key:
        key = key.replace("\\n", "\n")
    # Validate the key has proper PEM format
    if not key.strip().startswith("-----BEGIN"):
        raise RuntimeError(
            "github_app_private_key must be a valid PEM format starting with "
            "'-----BEGIN RSA PRIVATE KEY-----' or '-----BEGIN PRIVATE KEY-----'"
        )
    return key


def _app_jwt() -> str:
    app_id = settings.github_app_id
    if not app_id:
        raise RuntimeError("github_app_id_missing")
    key = _load_private_key()
    now = int(time.time())
    payload = {
        "iat": now - 60,
        "exp": now + 9 * 60,
        "iss": app_id,
    }
    return jwt.encode(payload, key, algorithm="RS256")


def get_installation_token(installation_id: str) -> str:
    token = _app_jwt()
    resp = requests.post(
        f"https://api.github.com/app/installations/{installation_id}/access_tokens",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        },
        timeout=20,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["token"]
