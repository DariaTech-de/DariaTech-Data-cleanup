from __future__ import annotations

from pathlib import Path

from app.scanner import ScanOptions, scan_duplicates


def test_exact_hash_groups_are_found(tmp_path: Path) -> None:
    left = tmp_path / "left.txt"
    right = tmp_path / "right.txt"
    unique = tmp_path / "unique.txt"

    left.write_text("same content", encoding="utf-8")
    right.write_text("same content", encoding="utf-8")
    unique.write_text("other content", encoding="utf-8")

    result = scan_duplicates(
        ScanOptions(
            folders=[str(tmp_path)],
            include_all_files=True,
            find_exact=True,
            find_similar_images=False,
        )
    )

    assert result["summary"]["duplicate_groups"] == 1
    assert result["summary"]["duplicate_files"] == 1
    assert len(result["groups"][0]["all_files"]) == 2


def test_min_size_filter_excludes_small_files(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("x", encoding="utf-8")
    (tmp_path / "b.txt").write_text("x", encoding="utf-8")

    result = scan_duplicates(
        ScanOptions(
            folders=[str(tmp_path)],
            include_all_files=True,
            min_size_mb=1,
            find_exact=True,
        )
    )

    assert result["summary"]["scanned_files"] == 0
    assert result["summary"]["duplicate_groups"] == 0
