from __future__ import annotations

import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import asdict
from typing import Any

from app import preview_guard
from app.enterprise_store import EnterpriseStore
from app.scanner import (
    ConsolidateOptions,
    Progress,
    ScanCancelled,
    ScanOptions,
    consolidate_clean,
    scan_duplicates,
)


class ScanJobRunner:
    """Runs scan and consolidation work on a background thread pool with live progress."""

    def __init__(self, store: EnterpriseStore | None = None, workers: int = 2) -> None:
        self.store = store or EnterpriseStore()
        self.executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="duplicat-job")
        self._lock = threading.RLock()
        self._futures: dict[str, Future] = {}
        self._cancels: dict[str, threading.Event] = {}

    # -- scan ---------------------------------------------------------------
    def start(self, options: ScanOptions) -> str:
        return self._start("scan", options, lambda job_id, cancel: self._run_scan(job_id, options, cancel))

    # -- consolidate --------------------------------------------------------
    def start_consolidation(self, options: ConsolidateOptions) -> str:
        return self._start(
            "consolidate", options, lambda job_id, cancel: self._run_consolidation(job_id, options, cancel)
        )

    def _start(self, kind: str, options: Any, work) -> str:
        job_id = str(uuid.uuid4())
        self.store.create_job(job_id, kind, asdict(options))
        cancel_event = threading.Event()
        future = self.executor.submit(work, job_id, cancel_event)
        with self._lock:
            self._futures[job_id] = future
            self._cancels[job_id] = cancel_event
        return job_id

    def _progress_writer(self, job_id: str):
        last = {"at": 0.0}

        def writer(progress: Progress) -> None:
            now = time.time()
            # Throttle DB writes so very fast phases do not hammer SQLite.
            if now - last["at"] < 0.25 and progress.processed not in (0, progress.total):
                return
            last["at"] = now
            self.store.set_progress(
                job_id, progress.phase, progress.processed, progress.total, progress.percent, progress.message
            )

        return writer

    def _run_scan(self, job_id: str, options: ScanOptions, cancel_event: threading.Event) -> None:
        self.store.set_status(job_id, "running", "Scan läuft")
        try:
            result = scan_duplicates(options, progress=self._progress_writer(job_id), cancel_event=cancel_event)
            result["scan_id"] = job_id
            preview_guard.register_result(result)
            self.store.set_result(job_id, result, message="Scan abgeschlossen")
        except ScanCancelled:
            self.store.set_status(job_id, "cancelled", "Scan abgebrochen")
        except Exception as exc:
            self.store.set_status(job_id, "failed", f"Scan fehlgeschlagen: {exc}", error=str(exc))
        finally:
            self._cleanup(job_id)

    def _run_consolidation(self, job_id: str, options: ConsolidateOptions, cancel_event: threading.Event) -> None:
        verb = "Vorschau" if options.dry_run else "Zusammenführung"
        self.store.set_status(job_id, "running", f"{verb} läuft")
        try:
            result = consolidate_clean(options, progress=self._progress_writer(job_id), cancel_event=cancel_event)
            result["scan_id"] = job_id
            message = "Vorschau abgeschlossen" if options.dry_run else "Zusammenführung abgeschlossen"
            self.store.set_result(job_id, result, message=message)
        except ScanCancelled:
            self.store.set_status(job_id, "cancelled", "Vorgang abgebrochen")
        except ValueError as exc:
            self.store.set_status(job_id, "failed", str(exc), error=str(exc))
        except Exception as exc:
            self.store.set_status(job_id, "failed", f"Zusammenführung fehlgeschlagen: {exc}", error=str(exc))
        finally:
            self._cleanup(job_id)

    def _cleanup(self, job_id: str) -> None:
        with self._lock:
            self._futures.pop(job_id, None)
            self._cancels.pop(job_id, None)

    # -- control ------------------------------------------------------------
    def cancel(self, job_id: str) -> bool:
        with self._lock:
            event = self._cancels.get(job_id)
        if event is None:
            return False
        event.set()
        return True

    def status(self, job_id: str) -> dict[str, Any] | None:
        return self.store.get_job(job_id, include_result=False)

    def result(self, job_id: str) -> dict[str, Any] | None:
        job = self.store.get_job(job_id, include_result=True)
        if job is None:
            return None
        return job.get("result")

    def list(self, limit: int = 25, kind: str | None = None) -> list[dict[str, Any]]:
        return self.store.list_jobs(limit=limit, kind=kind)


runner = ScanJobRunner()
