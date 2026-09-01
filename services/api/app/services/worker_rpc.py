from __future__ import annotations

from typing import Any

import requests
from fastapi import HTTPException

from app.settings import settings


def _extract_detail(resp: requests.Response) -> str:
    try:
        payload = resp.json()
    except Exception:
        text = resp.text.strip()
        return text or "worker_rpc_error"
    if isinstance(payload, dict) and payload.get("detail") is not None:
        return str(payload["detail"])
    return str(payload)


def call_worker_rpc(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    base_url = (settings.worker_rpc_base_url or "").strip().rstrip("/")
    if not base_url:
        raise HTTPException(status_code=500, detail="worker_rpc_base_url_not_configured")

    url = f"{base_url}{path}"
    headers: dict[str, str] = {}
    token = (settings.worker_rpc_token or "").strip()
    if token:
        headers["X-Worker-RPC-Token"] = token

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=settings.worker_rpc_timeout_s)
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail="worker_rpc_unreachable") from exc

    if resp.status_code >= 400:
        detail = _extract_detail(resp)
        if resp.status_code in (400, 404):
            raise HTTPException(status_code=resp.status_code, detail=detail)
        raise HTTPException(status_code=502, detail=f"worker_rpc_failed:{resp.status_code}:{detail}")

    try:
        data = resp.json()
    except Exception as exc:
        raise HTTPException(status_code=502, detail="worker_rpc_invalid_json") from exc

    if not isinstance(data, dict):
        raise HTTPException(status_code=502, detail="worker_rpc_invalid_payload")
    return data
