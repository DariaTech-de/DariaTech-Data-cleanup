from __future__ import annotations

import threading
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from threading import Event
from typing import Any

from app.enterprise_store import EnterpriseStore
from app.progress_scanner import scan_with_progress
from app.runtime_status import RuntimeStatus
from app.scanner import ScanOptions


class ScanJobRunnerV2:
    def __init__(self, store: EnterpriseStore | None = None, workers: int = 2) -> None:
        self.store = store or EnterpriseStore()
        self.executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="duplicat-scan")
        self._lock = threading.RLock()
        self._futures: dict[str, Future] = {}
        self._events: dict[str, Event] = {}
        self._status: dict[str, RuntimeStatus] = {}

    def start(self, options: ScanOptions) -> str:
        scan_id = str(uuid.uuid4())
        event = Event()
        self.store.create_scan(scan_id, options.__dict__)
        with self._lock:
            self._status[scan_id] = RuntimeStatus("queued", 0, None, "Scan queued")
            self._events[scan_id] = event
            self._futures[scan_id] = self.executor.submit(self._run, scan_id, options, event)
        return scan_id

    def _remember(self, scan_id: str, stage: str, current: int, total: int | None, message: str) -> None:
        with self._lock:
            self._status[scan_id] = RuntimeStatus(stage, current, total, message)
        self.store.set_status(scan_id, "running", message)

    def _run(self, scan_id: str, options: ScanOptions, event: Event) -> None:
        try:
            result = scan_with_progress(options, progress=lambda s, c, t, m: self._remember(scan_id, s, c, t, m), cancel_event=event)
            result["scan_id"] = scan_id
            self.store.set_result(scan_id, result)
            self._remember(scan_id, "complete", 100, 100, "Scan completed")
        except Exception as exc:
            self.store.set_status(scan_id, "failed", str(exc), error=str(exc))
            with self._lock:
                self._status[scan_id] = RuntimeStatus("failed", 0, None, str(exc))
        finally:
            with self._lock:
                self._futures.pop(scan_id, None)
                self._events.pop(scan_id, None)

    def request_stop(self, scan_id: str) -> bool:
        with self._lock:
            event = self._events.get(scan_id)
        if event is None:
            return False
        event.set()
        self.store.set_status(scan_id, "stop_requested", "Stop requested")
        with self._lock:
            self._status[scan_id] = RuntimeStatus("stop_requested", 0, None, "Stop requested")
        return True

    def status(self, scan_id: str) -> dict[str, Any] | None:
        item = self.store.get_scan(scan_id, include_result=False)
        if item is None:
            return None
        with self._lock:
            runtime = self._status.get(scan_id)
        if runtime:
            item.update({
                "stage": runtime.stage,
                "progress_current": runtime.current,
                "progress_total": runtime.total,
                "message": runtime.message,
            })
        return item

    def result(self, scan_id: str) -> dict[str, Any] | None:
        scan = self.store.get_scan(scan_id, include_result=True)
        return None if scan is None else scan.get("result")

    def list(self, limit: int = 25) -> list[dict[str, Any]]:
        return self.store.list_scans(limit=limit)


runner = ScanJobRunnerV2()
