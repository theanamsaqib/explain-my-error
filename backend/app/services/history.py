"""SQLite-backed debug history. Deliberately tiny: one table, JSON blob per session."""

from __future__ import annotations

import asyncio
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from app.models.schemas import DebugResponse, HistoryItem

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    mode TEXT NOT NULL,
    status TEXT NOT NULL,
    error_type TEXT NOT NULL,
    preview TEXT NOT NULL,
    response_json TEXT NOT NULL
)
"""


class HistoryStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as conn:
            conn.execute(_SCHEMA)
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=5)

    # -- sync implementations (run in a worker thread) --------------------------------
    def _save(self, resp: DebugResponse) -> int:
        # For tracebacks the last line (the actual error) is the useful preview.
        last_line = next((ln.strip() for ln in reversed(resp.error.splitlines()) if ln.strip()), "")
        first_code_line = (resp.code.strip().splitlines() or [""])[0]
        preview = (last_line or first_code_line)[:90]
        with closing(self._connect()) as conn:
            cur = conn.execute(
                "INSERT INTO sessions (created_at, mode, status, error_type, preview, response_json) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    resp.mode,
                    resp.status,
                    resp.error_type or "Unknown",
                    preview,
                    resp.model_dump_json(),
                ),
            )
            conn.commit()
            return int(cur.lastrowid)

    def _list(self, limit: int) -> list[HistoryItem]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT id, created_at, mode, status, error_type, preview FROM sessions "
                "ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            HistoryItem(id=r[0], created_at=r[1], mode=r[2], status=r[3], error_type=r[4], preview=r[5])
            for r in rows
        ]

    def _get(self, session_id: int) -> DebugResponse | None:
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT response_json FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if row is None:
            return None
        resp = DebugResponse.model_validate_json(row[0])
        resp.id = session_id
        return resp

    # -- async API --------------------------------------------------------------------
    async def save(self, resp: DebugResponse) -> int:
        return await asyncio.to_thread(self._save, resp)

    async def list(self, limit: int = 30) -> list[HistoryItem]:
        return await asyncio.to_thread(self._list, limit)

    async def get(self, session_id: int) -> DebugResponse | None:
        return await asyncio.to_thread(self._get, session_id)
