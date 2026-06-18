from __future__ import annotations

import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any


class ActionLog:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=30)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_db(self) -> None:
        with self._connect() as db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS file_actions (
                    id TEXT PRIMARY KEY,
                    scan_id TEXT NOT NULL,
                    source_path TEXT NOT NULL,
                    target_path TEXT NOT NULL,
                    action_mode TEXT NOT NULL,
                    status TEXT NOT NULL,
                    error TEXT,
                    created_at REAL NOT NULL,
                    restored_at REAL
                )
                """
            )

    def record(self, scan_id: str, source_path: str, target_path: str, action_mode: str, status: str, error: str | None = None) -> str:
        action_id = str(uuid.uuid4())
        with self._connect() as db:
            db.execute(
                """
                INSERT INTO file_actions(id, scan_id, source_path, target_path, action_mode, status, error, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (action_id, scan_id, source_path, target_path, action_mode, status, error, time.time()),
            )
        return action_id

    def list(self, scan_id: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
        limit = max(1, min(limit, 1000))
        with self._connect() as db:
            if scan_id:
                rows = db.execute("SELECT * FROM file_actions WHERE scan_id = ? ORDER BY created_at DESC LIMIT ?", (scan_id, limit)).fetchall()
            else:
                rows = db.execute("SELECT * FROM file_actions ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [dict(row) for row in rows]

    def get(self, action_id: str) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM file_actions WHERE id = ?", (action_id,)).fetchone()
        return dict(row) if row else None

    def mark_restored(self, action_id: str, target_path: str) -> None:
        with self._connect() as db:
            db.execute("UPDATE file_actions SET status = ?, target_path = ?, restored_at = ? WHERE id = ?", ("restored", target_path, time.time(), action_id))
