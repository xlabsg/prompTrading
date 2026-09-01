from __future__ import annotations

import re

from fastapi import HTTPException


_REJECT_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bimport\s+os\b", re.IGNORECASE), "disallowed_import"),
    (re.compile(r"\bimport\s+sys\b", re.IGNORECASE), "disallowed_import"),
    (re.compile(r"\bimport\s+subprocess\b", re.IGNORECASE), "disallowed_import"),
    (re.compile(r"\bimport\s+socket\b", re.IGNORECASE), "disallowed_import"),
    (re.compile(r"\bimport\s+requests\b", re.IGNORECASE), "disallowed_import"),
    (re.compile(r"\bos\.system\s*\(", re.IGNORECASE), "disallowed_call"),
    (re.compile(r"\bsubprocess\.", re.IGNORECASE), "disallowed_call"),
    (re.compile(r"\bexec\s*\(", re.IGNORECASE), "disallowed_call"),
    (re.compile(r"\beval\s*\(", re.IGNORECASE), "disallowed_call"),
    (re.compile(r"\bopen\s*\(", re.IGNORECASE), "disallowed_call"),
    (re.compile(r"\brequests\.", re.IGNORECASE), "disallowed_network"),
    (re.compile(r"\bhttp[s]?://", re.IGNORECASE), "disallowed_network"),
    (re.compile(r"\bcurl\b|\bwget\b", re.IGNORECASE), "disallowed_network"),
    (re.compile(r"\bpip\s+install\b|\bapt-?get\b", re.IGNORECASE), "disallowed_install"),
    (re.compile(r"/etc/|/proc/|/sys/", re.IGNORECASE), "disallowed_fs"),
    (re.compile(r"\.ssh\b|id_rsa\b", re.IGNORECASE), "disallowed_fs"),
    (re.compile(r"OPENAI_API_KEY|DEEPSEEK_API_KEY|AWS_SECRET|SECRET_KEY", re.IGNORECASE), "disallowed_secret"),
]


def validate_prompt(prompt: str) -> None:
    if not prompt or not prompt.strip():
        raise HTTPException(status_code=400, detail="prompt_empty")

    for pattern, code in _REJECT_RULES:
        if pattern.search(prompt):
            raise HTTPException(status_code=400, detail=f"prompt_rejected:{code}")
