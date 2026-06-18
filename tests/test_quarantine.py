from __future__ import annotations

import threading
from pathlib import Path

import pytest

from app.scanner import (
    ScanCancelled,
    ScanOptions,
    clean_files,
    list_quarantine,
    restore_quarantine,
    scan_duplicates,
)


def test_quarantine_then_restore_roundtrip(tmp_path: Path) -> None:
    root = tmp_path / "data"
    target_file = root / "sub" / "dup.txt"
    target_file.parent.mkdir(parents=True)
    target_file.write_text("duplicate content", encoding="utf-8")

    cleaned = clean_files([str(root)], [str(target_file)], mode="quarantine")
    assert len(cleaned["changed"]) == 1
    assert not target_file.exists()

    listing = list_quarantine([str(root)])
    assert len(listing["items"]) == 1
    quarantined_path = listing["items"][0]["quarantined"]

    restored = restore_quarantine([str(root)], [quarantined_path])
    assert len(restored["restored"]) == 1
    assert target_file.exists()
    assert target_file.read_text(encoding="utf-8") == "duplicate content"


def test_clean_skips_files_outside_roots(tmp_path: Path) -> None:
    root = tmp_path / "data"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("nope", encoding="utf-8")

    result = clean_files([str(root)], [str(outside)], mode="quarantine")
    assert result["changed"] == []
    assert len(result["skipped"]) == 1
    assert outside.exists()


def test_progress_callback_reports_phases(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("same", encoding="utf-8")
    (tmp_path / "b.txt").write_text("same", encoding="utf-8")

    phases: list[str] = []
    scan_duplicates(
        ScanOptions(folders=[str(tmp_path)], include_all_files=True, find_exact=True),
        progress=lambda progress: phases.append(progress.phase),
    )

    assert "enumerate" in phases
    assert "hash" in phases


def test_scan_can_be_cancelled(tmp_path: Path) -> None:
    for index in range(60):
        (tmp_path / f"file_{index}.bin").write_bytes(b"x" * 2048)

    cancel = threading.Event()
    cancel.set()

    with pytest.raises(ScanCancelled):
        scan_duplicates(
            ScanOptions(folders=[str(tmp_path)], include_all_files=True, find_exact=True),
            cancel_event=cancel,
        )
