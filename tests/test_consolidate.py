from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from app.scanner import ConsolidateOptions, consolidate_clean


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _gradient_image(path: Path, size: tuple[int, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", size)
    pixels = image.load()
    for y in range(size[1]):
        for x in range(size[0]):
            pixels[x, y] = ((x * 5) % 256, (y * 7) % 256, (x + y) % 256)
    image.save(path)


def test_consolidate_dedupes_across_folders(tmp_path: Path) -> None:
    src_a = tmp_path / "A"
    src_b = tmp_path / "B"
    target = tmp_path / "Clean"
    _write(src_a / "photo.jpg", b"IMAGE-CONTENT-1")
    _write(src_b / "photo_copy.jpg", b"IMAGE-CONTENT-1")  # exact duplicate of the file in A
    _write(src_b / "unique.jpg", b"IMAGE-CONTENT-2")

    result = consolidate_clean(
        ConsolidateOptions(
            folders=[str(src_a), str(src_b)],
            target=str(target),
            include_all_files=True,
            operation="copy",
            structure="flat",
            keep_rule="oldest",
        )
    )

    summary = result["summary"]
    assert summary["source_files"] == 3
    assert summary["output_files"] == 2
    assert summary["removed_exact"] == 1
    assert summary["removed_total"] == 1
    copied = [p for p in target.rglob("*") if p.is_file()]
    assert len(copied) == 2
    # Sources stay untouched when copying.
    assert (src_a / "photo.jpg").exists()
    assert (src_b / "photo_copy.jpg").exists()


def test_consolidate_by_source_structure_keeps_folders(tmp_path: Path) -> None:
    src_a = tmp_path / "Kunde-Fotos"
    src_b = tmp_path / "Backup"
    target = tmp_path / "Clean"
    _write(src_a / "sub" / "a.txt", b"AAA")
    _write(src_b / "b.txt", b"BBB")

    result = consolidate_clean(
        ConsolidateOptions(
            folders=[str(src_a), str(src_b)],
            target=str(target),
            include_all_files=True,
            structure="by_source",
            keep_rule="oldest",
        )
    )

    assert result["summary"]["output_files"] == 2
    assert (target / "Kunde-Fotos" / "sub" / "a.txt").exists()
    assert (target / "Backup" / "b.txt").exists()


def test_consolidate_flat_renames_on_name_conflict(tmp_path: Path) -> None:
    src_a = tmp_path / "A"
    src_b = tmp_path / "B"
    target = tmp_path / "Clean"
    _write(src_a / "report.txt", b"FIRST")
    _write(src_b / "report.txt", b"SECOND")  # same name, different content

    result = consolidate_clean(
        ConsolidateOptions(
            folders=[str(src_a), str(src_b)],
            target=str(target),
            include_all_files=True,
            structure="flat",
            on_conflict="rename",
        )
    )

    assert result["summary"]["output_files"] == 2
    files = sorted(p.name for p in target.iterdir() if p.is_file())
    assert files == ["report (1).txt", "report.txt"]


def test_consolidate_dry_run_creates_no_files(tmp_path: Path) -> None:
    src = tmp_path / "A"
    target = tmp_path / "Clean"
    _write(src / "a.txt", b"same-bytes")
    _write(src / "b.txt", b"same-bytes")

    result = consolidate_clean(
        ConsolidateOptions(
            folders=[str(src)],
            target=str(target),
            include_all_files=True,
            structure="flat",
            dry_run=True,
        )
    )

    assert result["summary"]["output_files"] == 1
    assert result["executed_count"] == 0
    assert len(result["operations"]) == 1
    assert not target.exists() or not any(target.iterdir())


def test_consolidate_move_removes_representative_from_source(tmp_path: Path) -> None:
    src = tmp_path / "A"
    target = tmp_path / "Clean"
    only = src / "only.txt"
    _write(only, b"hello-world")

    result = consolidate_clean(
        ConsolidateOptions(
            folders=[str(src)],
            target=str(target),
            include_all_files=True,
            operation="move",
            structure="flat",
        )
    )

    assert result["summary"]["output_files"] == 1
    assert not only.exists()
    assert (target / "only.txt").exists()


def test_consolidate_rejects_target_inside_source(tmp_path: Path) -> None:
    src = tmp_path / "A"
    _write(src / "a.txt", b"x")
    target = src / "Clean"

    with pytest.raises(ValueError):
        consolidate_clean(
            ConsolidateOptions(folders=[str(src)], target=str(target), include_all_files=True)
        )


def test_consolidate_dedupes_similar_images(tmp_path: Path) -> None:
    src = tmp_path / "A"
    target = tmp_path / "Clean"
    _gradient_image(src / "original.png", (64, 64))
    # Same picture, re-encoded as JPEG: different bytes/size but a near-identical fingerprint.
    Image.open(src / "original.png").save(src / "copy.jpg", quality=85)

    result = consolidate_clean(
        ConsolidateOptions(
            folders=[str(src)],
            target=str(target),
            include_all_files=True,
            dedupe_similar_images=True,
            image_similarity=10,
            keep_rule="highest_resolution",
            structure="flat",
        )
    )

    assert result["summary"]["source_files"] == 2
    assert result["summary"]["output_files"] == 1
    assert result["summary"]["removed_similar"] == 1
