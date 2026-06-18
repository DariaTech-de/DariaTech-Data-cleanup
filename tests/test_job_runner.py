from __future__ import annotations

import time
from pathlib import Path

from app.enterprise_store import EnterpriseStore
from app.job_runner import ScanJobRunner
from app.scanner import ConsolidateOptions, ScanOptions


def _wait_for_job(runner: ScanJobRunner, job_id: str, timeout: float = 15.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        status = runner.status(job_id)
        if status and status["status"] in ("completed", "failed", "cancelled"):
            return status
        time.sleep(0.05)
    raise AssertionError(f"Job {job_id} did not finish in time")


def test_background_scan_completes_with_result(tmp_path: Path) -> None:
    src = tmp_path / "A"
    src.mkdir()
    (src / "a.txt").write_text("dup", encoding="utf-8")
    (src / "b.txt").write_text("dup", encoding="utf-8")

    runner = ScanJobRunner(store=EnterpriseStore(tmp_path / "jobs.sqlite3"), workers=1)
    job_id = runner.start(ScanOptions(folders=[str(src)], include_all_files=True))

    status = _wait_for_job(runner, job_id)
    assert status["status"] == "completed"

    result = runner.result(job_id)
    assert result["summary"]["duplicate_groups"] == 1


def test_background_consolidation_completes(tmp_path: Path) -> None:
    src = tmp_path / "A"
    src.mkdir()
    (src / "a.txt").write_text("dup", encoding="utf-8")
    (src / "b.txt").write_text("dup", encoding="utf-8")
    target = tmp_path / "Clean"

    runner = ScanJobRunner(store=EnterpriseStore(tmp_path / "jobs.sqlite3"), workers=1)
    job_id = runner.start_consolidation(
        ConsolidateOptions(folders=[str(src)], target=str(target), include_all_files=True, structure="flat")
    )

    status = _wait_for_job(runner, job_id)
    assert status["status"] == "completed"

    result = runner.result(job_id)
    assert result["summary"]["output_files"] == 1
    assert (target / "a.txt").exists() or (target / "b.txt").exists()


def test_failed_consolidation_reports_error(tmp_path: Path) -> None:
    src = tmp_path / "A"
    src.mkdir()
    (src / "a.txt").write_text("x", encoding="utf-8")

    runner = ScanJobRunner(store=EnterpriseStore(tmp_path / "jobs.sqlite3"), workers=1)
    # Target inside the source is rejected -> the job must fail cleanly, not hang.
    job_id = runner.start_consolidation(
        ConsolidateOptions(folders=[str(src)], target=str(src / "inside"), include_all_files=True)
    )

    status = _wait_for_job(runner, job_id)
    assert status["status"] == "failed"
    assert status["error"]
