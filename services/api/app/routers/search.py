from __future__ import annotations

import os
import sqlite3
from typing import Any, Optional

from fastapi import APIRouter
from app.schemas import SearchResponse, SearchHit
from app.settings import settings


router = APIRouter()


def _index_path() -> str:
    return settings.search_index_path or os.path.join(settings.workspaces_dir, "search", "search.sqlite")


def _open_db(path: str) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


@router.get("/search", response_model=SearchResponse)
def search(
    q: str,
    repo_id: Optional[str] = None,
    branch: Optional[str] = None,
    path_prefix: Optional[str] = None,
    ext: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
) -> SearchResponse:
    if not q or q.strip() == "":
        return SearchResponse(total=0, hits=[])

    idx = _index_path()
    if not os.path.exists(idx):
        return SearchResponse(total=0, hits=[])

    where = []
    params: list[Any] = []
    if repo_id:
        where.append("repo_id = ?")
        params.append(repo_id)
    if branch:
        where.append("branch = ?")
        params.append(branch)
    if path_prefix:
        where.append("path GLOB ?")
        # Convert prefix to sqlite GLOB pattern
        params.append(f"{path_prefix}*")
    if ext:
        where.append("path LIKE ?")
        params.append(f"%.{ext}")

    where_clause = " AND ".join(where)
    if where_clause:
        where_clause = " AND (" + where_clause + ")"

    # Use FTS5 with bm25. Prefix search supported via *.
    query = f"""
        SELECT rowid, repo_id, branch, path, lang, bm25(files_fts) as score,
               snippet(files_fts, 4, '[', ']', ' … ', 8) AS snippet
        FROM files_fts
        WHERE files_fts MATCH ? {where}
        ORDER BY score
        LIMIT ? OFFSET ?
    """.format(where=where_clause)

    count_query = f"SELECT count(1) as cnt FROM files_fts WHERE files_fts MATCH ? {where_clause}"

    with _open_db(idx) as conn:
        total = conn.execute(count_query, [q, *params]).fetchone()[0]
        rows = conn.execute(query, [q, *params, limit, offset]).fetchall()
        hits = [
            SearchHit(
                repo_id=row["repo_id"],
                branch=row["branch"],
                path=row["path"],
                lang=row["lang"],
                snippet=row["snippet"],
                score=float(row["score"]) if row["score"] is not None else None,
            )
            for row in rows
        ]
    return SearchResponse(total=int(total), hits=hits)
