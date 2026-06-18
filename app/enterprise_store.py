from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any


class EnterpriseStore:
    """SQLite-backed persistence for background jobs (scan/consolidate) and saved profiles."""

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or self.default_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init_db()

    @staticmethod
    def default_path() -> Path:
        if os.name == "nt":
            base = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Duplicat-Clearner"
        else:
            base = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))) / "duplicat-cleaner"
        return base / "enterprise.sqlite3"

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        return connection

    def _init_db(self) -> None:
        with self._lock, self._connect() as db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL DEFAULT 'scan',
                    status TEXT NOT NULL,
                    message TEXT NOT NULL,
                    phase TEXT NOT NULL DEFAULT 'queued',
                    processed INTEGER NOT NULL DEFAULT 0,
                    total INTEGER NOT NULL DEFAULT 0,
                    percent REAL NOT NULL DEFAULT 0,
                    options_json TEXT NOT NULL,
                    result_json TEXT,
                    error TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS profiles (
                    name TEXT PRIMARY KEY,
                    config_json TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )

    # -- jobs ---------------------------------------------------------------
    def create_job(self, job_id: str, kind: str, options: dict[str, Any]) -> None:
        now = time.time()
        with self._lock, self._connect() as db:
            db.execute(
                """
                INSERT INTO jobs(id, kind, status, message, phase, options_json, created_at, updated_at)
                VALUES (?, ?, 'queued', 'In Warteschlange', 'queued', ?, ?, ?)
                """,
                (job_id, kind, json.dumps(options, ensure_ascii=False), now, now),
            )

    def set_status(self, job_id: str, status: str, message: str, error: str | None = None) -> None:
        with self._lock, self._connect() as db:
            db.execute(
                "UPDATE jobs SET status = ?, message = ?, error = ?, updated_at = ? WHERE id = ?",
                (status, message, error, time.time(), job_id),
            )

    def set_progress(self, job_id: str, phase: str, processed: int, total: int, percent: float, message: str) -> None:
        with self._lock, self._connect() as db:
            db.execute(
                """
                UPDATE jobs
                SET status = 'running', phase = ?, processed = ?, total = ?, percent = ?, message = ?, updated_at = ?
                WHERE id = ?
                """,
                (phase, processed, total, percent, message, time.time(), job_id),
            )

    def set_result(self, job_id: str, result: dict[str, Any], message: str = "Fertig") -> None:
        with self._lock, self._connect() as db:
            db.execute(
                """
                UPDATE jobs
                SET status = 'completed', phase = 'done', percent = 100, message = ?, result_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (message, json.dumps(result, ensure_ascii=False), time.time(), job_id),
            )

    def get_job(self, job_id: str, include_result: bool = False) -> dict[str, Any] | None:
        with self._lock, self._connect() as db:
            row = db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            return None
        data = dict(row)
        data["options"] = json.loads(data.pop("options_json") or "{}")
        result_json = data.pop("result_json")
        data["has_result"] = bool(result_json)
        if include_result and result_json:
            data["result"] = json.loads(result_json)
        return data

    def list_jobs(self, limit: int = 25, kind: str | None = None) -> list[dict[str, Any]]:
        limit = max(1, min(limit, 100))
        with self._lock, self._connect() as db:
            if kind:
                rows = db.execute(
                    "SELECT * FROM jobs WHERE kind = ? ORDER BY created_at DESC LIMIT ?", (kind, limit)
                ).fetchall()
            else:
                rows = db.execute("SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        result = []
        for row in rows:
            data = dict(row)
            data.pop("options_json", None)
            data["has_result"] = bool(data.pop("result_json"))
            result.append(data)
        return result

    # -- profiles -----------------------------------------------------------
    def save_profile(self, name: str, config: dict[str, Any]) -> None:
        now = time.time()
        with self._lock, self._connect() as db:
            db.execute(
                """
                INSERT INTO profiles(name, config_json, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET config_json = excluded.config_json, updated_at = excluded.updated_at
                """,
                (name, json.dumps(config, ensure_ascii=False), now, now),
            )

    def list_profiles(self) -> list[dict[str, Any]]:
        with self._lock, self._connect() as db:
            rows = db.execute("SELECT * FROM profiles ORDER BY name ASC").fetchall()
        profiles = []
        for row in rows:
            data = dict(row)
            data["config"] = json.loads(data.pop("config_json") or "{}")
            profiles.append(data)
        return profiles

    def delete_profile(self, name: str) -> bool:
        with self._lock, self._connect() as db:
            cursor = db.execute("DELETE FROM profiles WHERE name = ?", (name,))
            return cursor.rowcount > 0
