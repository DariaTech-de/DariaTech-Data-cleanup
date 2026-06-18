from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any


class EnterpriseStore:
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
                CREATE TABLE IF NOT EXISTS scans (
                    id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    message TEXT NOT NULL,
                    options_json TEXT NOT NULL,
                    result_json TEXT,
                    error TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )

    def create_scan(self, scan_id: str, options: dict[str, Any]) -> None:
        now = time.time()
        with self._lock, self._connect() as db:
            db.execute(
                "INSERT INTO scans(id, status, message, options_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                (scan_id, "queued", "Scan queued", json.dumps(options, ensure_ascii=False), now, now),
            )

    def set_status(self, scan_id: str, status: str, message: str, error: str | None = None) -> None:
        with self._lock, self._connect() as db:
            db.execute(
                "UPDATE scans SET status = ?, message = ?, error = ?, updated_at = ? WHERE id = ?",
                (status, message, error, time.time(), scan_id),
            )

    def set_result(self, scan_id: str, result: dict[str, Any]) -> None:
        with self._lock, self._connect() as db:
            db.execute(
                "UPDATE scans SET status = ?, message = ?, result_json = ?, updated_at = ? WHERE id = ?",
                ("completed", "Scan completed", json.dumps(result, ensure_ascii=False), time.time(), scan_id),
            )

    def get_scan(self, scan_id: str, include_result: bool = False) -> dict[str, Any] | None:
        with self._lock, self._connect() as db:
            row = db.execute("SELECT * FROM scans WHERE id = ?", (scan_id,)).fetchone()
        if row is None:
            return None
        data = dict(row)
        data["options"] = json.loads(data.pop("options_json") or "{}")
        result_json = data.pop("result_json")
        data["has_result"] = bool(result_json)
        if include_result and result_json:
            data["result"] = json.loads(result_json)
        return data

    def list_scans(self, limit: int = 25) -> list[dict[str, Any]]:
        limit = max(1, min(limit, 100))
        with self._lock, self._connect() as db:
            rows = db.execute("SELECT * FROM scans ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        result = []
        for row in rows:
            data = dict(row)
            data.pop("options_json", None)
            data["has_result"] = bool(data.pop("result_json"))
            result.append(data)
        return result
