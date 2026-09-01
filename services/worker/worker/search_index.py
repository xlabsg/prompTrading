from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from typing import Iterator


DEFAULT_EXCLUDED_DIRS = {
    ".git",
    ".github",
    ".vscode",
    ".idea",
    ".venv",
    "node_modules",
    "dist",
    "build",
    "out",
    ".next",
    ".cache",
    "target",
    "vendor",
    "coverage",
    ".pytest_cache",
}

DEFAULT_EXCLUDED_EXTS = {
    "lock",
    "png",
    "jpg",
    "jpeg",
    "gif",
    "webp",
    "svg",
    "pdf",
    "zip",
    "tar",
    "gz",
    "tgz",
    "rar",
    "7z",
    "exe",
    "dll",
    "so",
    "dylib",
    "mp3",
    "mp4",
    "mov",
    "avi",
    "woff",
    "woff2",
    "ttf",
}

MAX_FILE_BYTES = 1_000_000  # 1MB


def _lang_from_ext(ext: str) -> str | None:
    m = {
        "py": "python",
        "ts": "typescript",
        "tsx": "tsx",
        "js": "javascript",
        "jsx": "jsx",
        "json": "json",
        "md": "markdown",
        "yml": "yaml",
        "yaml": "yaml",
        "txt": "text",
        "java": "java",
        "go": "go",
        "rs": "rust",
        "c": "c",
        "h": "c",
        "cpp": "cpp",
        "hpp": "cpp",
        "cs": "csharp",
        "rb": "ruby",
        "php": "php",
        "sh": "shell",
        "sql": "sql",
    }
    return m.get(ext)


def _is_binary_bytes(buf: bytes) -> bool:
    if not buf:
        return False
    # Heuristic: if null byte present or many non-text bytes
    if b"\x00" in buf:
        return True
    textchars = bytearray({7, 8, 9, 10, 12, 13, 27} | set(range(0x20, 0x100)))
    # If >30% of bytes are non-text
    nontext = sum(b not in textchars for b in buf)
    return (nontext / max(1, len(buf))) > 0.3


def _should_exclude(path: str) -> bool:
    parts = path.strip("/").split("/")
    for p in parts[:-1]:
        if p in DEFAULT_EXCLUDED_DIRS:
            return True
    ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    if ext in DEFAULT_EXCLUDED_EXTS:
        return True
    name = os.path.basename(path)
    if name.endswith(".min.js"):
        return True
    return False


def ensure_db(path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS files_fts
            USING fts5(
                repo_id, branch, path, lang, content,
                tokenize = 'unicode61'
            );
            """
        )


@contextmanager
def open_db(path: str) -> Iterator[sqlite3.Connection]:
    ensure_db(path)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def index_full(conn: sqlite3.Connection, *, repo_id: str, branch: str, worktree_path: str) -> int:
    # Remove previous docs for this repo+branch
    conn.execute("DELETE FROM files_fts WHERE repo_id = ? AND branch = ?", (repo_id, branch))
    total = 0
    cur = conn.cursor()
    for root, dirs, files in os.walk(worktree_path):
        # Prune excluded directories
        dirs[:] = [d for d in dirs if d not in DEFAULT_EXCLUDED_DIRS]
        for name in files:
            rel_path = os.path.relpath(os.path.join(root, name), worktree_path)
            # Normalize path separator
            rel_path = rel_path.replace("\\", "/")
            if _should_exclude(rel_path):
                continue
            full = os.path.join(worktree_path, rel_path)
            try:
                size = os.path.getsize(full)
            except OSError:
                continue
            if size > MAX_FILE_BYTES:
                continue
            try:
                with open(full, "rb") as f:
                    head = f.read(min(size, 4096))
                    if _is_binary_bytes(head):
                        continue
                    f.seek(0)
                    content_bytes = f.read()
                content = content_bytes.decode("utf-8", errors="ignore")
            except Exception:
                continue
            ext = rel_path.rsplit(".", 1)[-1].lower() if "." in rel_path else ""
            lang = _lang_from_ext(ext)
            cur.execute(
                "INSERT INTO files_fts (repo_id, branch, path, lang, content) VALUES (?, ?, ?, ?, ?)",
                (repo_id, branch, rel_path, lang or "", content),
            )
            total += 1
    conn.commit()
    return total
