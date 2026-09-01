from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass
from typing import Any, Optional

import requests


# Langfuse OpenAI integration - automatically traces all LLM calls
# Falls back to standard OpenAI client if Langfuse is unavailable.
try:
    from langfuse.openai import OpenAI as LangfuseOpenAI
    _langfuse_available = True
except Exception:
    from openai import OpenAI as LangfuseOpenAI
    _langfuse_available = False

# Configure logging to output to stdout for Docker container log capture
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


# Global OpenAI client (lazy init)
_openai_client: LangfuseOpenAI | None = None


def _get_openai_client(base_url: str, api_key: str) -> LangfuseOpenAI:
    """Get or create OpenAI client with Langfuse integration.

    Args:
        base_url: API base URL.
        api_key: API key.

    Returns:
        OpenAI client instance (with Langfuse tracing if enabled).
    """
    global _openai_client

    # Create new client if base_url/api_key differs
    if _openai_client is None:
        _openai_client = LangfuseOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=180.0,
        )
    return _openai_client


@dataclass(frozen=True)
class ChatMessage:
    role: str
    content: str


@dataclass(frozen=True)
class ChatCompletionRequest:
    api_key: str
    base_url: str
    model: str
    messages: list[Any]
    temperature: float = 0.2
    timeout_s: int = 180
    tools: Optional[list[dict[str, Any]]] = None
    tool_choice: Optional[str | dict] = None


def _strip_code_fences(text: str) -> str:
    """Best-effort extraction of Python code from LLM output.

    Many models ignore "no markdown" and still wrap code in fences. Some even omit the closing fence.
    This helper tries to extract the code block if present, otherwise returns the trimmed text.
    """

    s = str(text or "").strip()
    if not s:
        return s

    # Prefer a complete fenced block with closing fence.
    fence_py = re.compile(r"```(?:python|py)?\s*([\s\S]*?)\s*```", re.IGNORECASE)
    m = fence_py.search(s)
    if m:
        return m.group(1).strip()

    # Any fenced block (language label may be present).
    fence_any = re.compile(r"```[a-zA-Z0-9_-]*\s*([\s\S]*?)\s*```", re.IGNORECASE)
    m = fence_any.search(s)
    if m:
        return m.group(1).strip()

    # Handle missing closing fence: drop the first fence line and an optional last fence line.
    if s.startswith("```"):
        lines = s.splitlines()
        if len(lines) <= 1:
            return ""
        lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        return "\n".join(lines).strip()

    # Handle missing closing fence with preamble: keep content after the first fence.
    fence_i = s.find("```")
    if fence_i != -1:
        tail = s[fence_i:]
        lines = tail.splitlines()
        if len(lines) <= 1:
            return ""
        lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        return "\n".join(lines).strip()

    return s


def _parse_timeout_s(env_key: str) -> Optional[float]:
    raw = (os.getenv(env_key) or "").strip()
    if not raw:
        return None
    try:
        val = float(raw)
        return val if val > 0 else None
    except Exception:
        logger.warning("[llm] invalid %s=%r; ignoring", env_key, raw)
        return None


def _get_request_timeout_s(req_timeout_s: float, *, stream: bool) -> float:
    """
    Resolve request timeout from env overrides.

    - Non-streaming: use LLM_HTTP_TIMEOUT_S if set, else req.timeout_s
    - Streaming: use LLM_STREAM_TIMEOUT_S if set, else LLM_HTTP_TIMEOUT_S if set, else req.timeout_s
    """
    http_timeout = _parse_timeout_s("LLM_HTTP_TIMEOUT_S")
    if stream:
        stream_timeout = _parse_timeout_s("LLM_STREAM_TIMEOUT_S")
        return float(stream_timeout or http_timeout or req_timeout_s)
    return float(http_timeout or req_timeout_s)


def _is_gemini_openai_compat(base_url: str, model: str) -> bool:
    host = (base_url or "").lower()
    model_name = (model or "").lower()
    return (
        "generativelanguage.googleapis.com" in host
        or model_name.startswith("gemini-")
    )


def _resolve_reasoning_effort(base_url: str, model: str) -> str | None:
    raw = (os.getenv("LLM_REASONING_EFFORT") or "").strip().lower()
    if raw:
        allowed = {"none", "minimal", "low", "medium", "high"}
        if raw in allowed:
            return raw
        logger.warning("[llm] invalid LLM_REASONING_EFFORT=%r; ignoring", raw)
        return None

    # Gemini OpenAI-compatible endpoint: default to low thinking level to reduce latency.
    if _is_gemini_openai_compat(base_url, model):
        return "low"
    return None


def _truncate_for_log(text: str, *, max_chars: int = 2000) -> str:
    value = (text or "").strip()
    if len(value) <= max_chars:
        return value
    return value[:max_chars] + "...(truncated)"


def _log_request_error(url: str, payload: dict[str, Any], resp: requests.Response) -> None:
    status = getattr(resp, "status_code", "unknown")
    body = _truncate_for_log(getattr(resp, "text", ""))
    logger.error(
        "[llm] request failed status=%s url=%s model=%s reasoning_effort=%s tools=%s messages=%s body=%s",
        status,
        url,
        payload.get("model"),
        payload.get("reasoning_effort"),
        bool(payload.get("tools")),
        len(payload.get("messages") or []),
        body,
    )


def _request_context_headers() -> dict[str, str]:
    """Build request correlation headers from environment context."""
    mapping = {
        "JOB_ID": "X-Job-ID",
        "STRATEGY_ID": "X-Strategy-ID",
        "VERSION_ID": "X-Version-ID",
        "RUN_ID": "X-Run-ID",
    }
    headers: dict[str, str] = {}
    for env_key, header_key in mapping.items():
        value = (os.getenv(env_key) or "").strip()
        if value:
            headers[header_key] = value
    return headers


def _request_context_for_log() -> str:
    parts = []
    for key in ("JOB_ID", "STRATEGY_ID", "VERSION_ID", "RUN_ID"):
        value = (os.getenv(key) or "").strip()
        if value:
            parts.append(f"{key.lower()}={value}")
    return " ".join(parts) if parts else "context=none"


def _normalize_messages(messages: list[Any]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for msg in messages or []:
        if isinstance(msg, dict):
            role = str(msg.get("role") or "").strip()
            if not role:
                continue
            item = dict(msg)
            item["role"] = role
            content = item.get("content")
            item["content"] = "" if content is None else str(content)
            normalized.append(item)
            continue

        role = getattr(msg, "role", None)
        if not isinstance(role, str) or not role.strip():
            continue
        content = getattr(msg, "content", "")
        normalized.append({"role": role.strip(), "content": "" if content is None else str(content)})
    return normalized


def _message_content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
                if text is not None:
                    parts.append(str(text))
            elif item is not None:
                parts.append(str(item))
        return "".join(parts)
    if content is None:
        return ""
    return str(content)


def chat_completion(req: ChatCompletionRequest) -> Any:
    url = req.base_url.rstrip("/") + "/chat/completions"
    messages = _normalize_messages(req.messages)
    payload: dict[str, Any] = {
        "model": req.model,
        "temperature": req.temperature,
        "messages": messages,
    }
    reasoning_effort = _resolve_reasoning_effort(req.base_url, req.model)
    if reasoning_effort:
        payload["reasoning_effort"] = reasoning_effort
    if req.tools:
        payload["tools"] = req.tools
    if req.tool_choice:
        payload["tool_choice"] = req.tool_choice

    headers = {"Authorization": f"Bearer {req.api_key}", "Content-Type": "application/json"}
    headers.update(_request_context_headers())
    timeout_s = _get_request_timeout_s(req.timeout_s, stream=False)
    context_str = _request_context_for_log()

    debug = os.getenv("LLM_DEBUG", "").strip().lower() in ("1", "true", "yes")
    if debug:
        logger.debug(f"Request to {url} with model={req.model} tools={bool(req.tools)}")

    logger.info(
        "[llm] request_start %s model=%s reasoning_effort=%s timeout_s=%.1f tools=%s messages=%s url=%s",
        context_str,
        req.model,
        reasoning_effort or "default",
        timeout_s,
        bool(req.tools),
        len(messages),
        url,
    )
    start_ts = time.monotonic()

    try:
        resp = requests.post(
            url,
            headers=headers,
            data=json.dumps(payload),
            timeout=timeout_s,
        )
        elapsed = time.monotonic() - start_ts
        logger.info(
            "[llm] request_done %s model=%s status=%s elapsed_s=%.2f",
            context_str,
            req.model,
            getattr(resp, "status_code", "unknown"),
            elapsed,
        )
        resp.raise_for_status()
    except requests.exceptions.HTTPError:
        _log_request_error(url, payload, resp)
        raise
    except requests.exceptions.RequestException as e:
        elapsed = time.monotonic() - start_ts
        logger.error(
            "[llm] request_exception %s model=%s elapsed_s=%.2f error=%s",
            context_str,
            req.model,
            elapsed,
            e,
        )
        raise

    data = resp.json()
    choice = data["choices"][0]
    message = choice["message"]

    # Tool-calling mode requires the full message payload.
    if req.tools:
        return message
    return _message_content_to_text(message.get("content"))
