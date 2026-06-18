from __future__ import annotations

import threading
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any

from app.enterprise_store import EnterpriseStore
from app.scanner import ScanOptions, scan_duplicates


class ScanJobRunner:
    def __init__(self, store: EnterpriseStore | None = None, workers: int = 2) -> None:
        self.store = store or EnterpriseStore()
        self.executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="duplicat-scan")
        self._lock = threading.RLock()
        self._futures: dict[str, Future] = {}

    def start(self, options: ScanOptions) -> str:
        scan_id = str(uuid.uuid4())
        self.store.create_scan(scan_id, options.__dict__)
        future = self.executor.submit(self._run, scan_id, options)
        with self._lock:
            self._futures[scan_id] = future
        return scan_id

    def _run(self, scan_id: str, options: ScanOptions) -> None:
        self.store.set_status(scan_id, "running", "Scan running")
        try:
            result = scan_duplicates(options)
            result["scan_id"] = scan_id
            self.store.set_result(scan_id, result)
        except Exception as exc:
            self.store.set_status(scan_id, "failed", str(exc), error=str(exc))
        finally:
            with self._lock:
                self._futures.pop(scan_id, None)

    def status(self, scan_id: str) -> dict[str, Any] | None:
        return self.store.get_scan(scan_id, include_result=False)

    def result(self, scan_id: str) -> dict[str, Any] | None:
        scan = self.store.get_scan(scan_id, include_result=True)
        if scan is None:
            return None
        return scan.get("result")

    def list(self, limit: int = 25) -> list[dict[str, Any]]:
        return self.store.list_scans(limit=limit)


runner = ScanJobRunner()
