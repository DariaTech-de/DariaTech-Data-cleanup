from __future__ import annotations

import threading
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from threading import Event
from typing import Any

from app.enterprise_store import EnterpriseStore
from app.progress_scanner import scan_with_progress
from app.scanner import ScanOptions


class ScanJobRunner:
    def __init__(self, store: EnterpriseStore | None = None, workers: int = 2) -> None:
        self.store = store or EnterpriseStore()
        self.executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="duplicat-scan")
        self._lock = threading.RLock()
        self._futures: dict[str, Future] = {}
        self._events: dict[str, Event] = {}

    def start(self, options: ScanOptions) -> str:
        scan_id = str(uuid.uuid4())
        event = Event()
        self.store.create_scan(scan_id, options.__dict__)
        future = self.executor.submit(self._run, scan_id, options, event)
        with self._lock:
            self._futures[scan_id] = future
            self._events[scan_id] = event
        return scan_id

    def _progress(self, scan_id: str):
        def callback(stage: str, current: int, total: int | None, message: str) -> None:
            if hasattr(self.store, "set_progress"):
                self.store.set_progress(scan_id, stage, current, total, message)
            else:
                self.store.set_status(scan_id, "running", message)
        return callback

    def _run(self, scan_id: str, options: ScanOptions, event: Event) -> None:
        self.store.set_status(scan_id, "running", "Scan running")
        try:
            result = scan_with_progress(options, progress=self._progress(scan_id), cancel_event=event)
            result["scan_id"] = scan_id
            self.store.set_result(scan_id, result)
        except Exception as exc:
            self.store.set_status(scan_id, "failed", str(exc), error=str(exc))
        finally:
            with self._lock:
                self._futures.pop(scan_id, None)
                self._events.pop(scan_id, None)

    def request_stop(self, scan_id: str) -> bool:
        with self._lock:
            event = self._events.get(scan_id)
            future = self._futures.get(scan_id)
        if event is not None:
            event.set()
            self.store.set_status(scan_id, "stop_requested", "Stop requested")
            return True
        if future is not None:
            return future.cancel()
        return False

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
