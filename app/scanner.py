from __future__ import annotations

import hashlib
import os
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

SUPPORTED_EXTENSIONS = {
    # images
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tif", ".tiff", ".webp", ".heic", ".heif", ".raw", ".svg",
    # videos
    ".mp4", ".mov", ".avi", ".mkv", ".webm", ".wmv", ".m4v", ".mpeg", ".mpg", ".3gp",
    # documents and common files
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".csv", ".zip", ".rar", ".7z",
}

QUARANTINE_DIR_NAME = ".quarantine-duplicates"


@dataclass(frozen=True)
class FileInfo:
    path: str
    name: str
    size: int
    modified: float
    sha256: str


def _iter_files(root: Path, include_all_files: bool = False) -> Iterable[Path]:
    root = root.resolve()
    for current_root, dirs, files in os.walk(root):
        # do not scan quarantine folders again
        dirs[:] = [d for d in dirs if d != QUARANTINE_DIR_NAME]
        for filename in files:
            path = Path(current_root) / filename
            try:
                if not path.is_file():
                    continue
                if include_all_files or path.suffix.lower() in SUPPORTED_EXTENSIONS:
                    yield path
            except OSError:
                continue


def _sha256(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _format_file(path: Path, digest: str) -> FileInfo:
    stat = path.stat()
    return FileInfo(
        path=str(path),
        name=path.name,
        size=stat.st_size,
        modified=stat.st_mtime,
        sha256=digest,
    )


def scan_duplicates(folder: str, include_all_files: bool = False) -> dict:
    root = Path(folder).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise ValueError("Der Ordner existiert nicht oder ist kein gültiger Ordner.")

    started = time.time()

    # First group by file size. Files with unique sizes cannot be duplicates.
    by_size: dict[int, list[Path]] = {}
    scanned_files = 0
    for path in _iter_files(root, include_all_files=include_all_files):
        try:
            by_size.setdefault(path.stat().st_size, []).append(path)
            scanned_files += 1
        except OSError:
            continue

    by_hash: dict[str, list[FileInfo]] = {}
    hashed_files = 0
    for same_size_files in by_size.values():
        if len(same_size_files) < 2:
            continue
        for path in same_size_files:
            try:
                digest = _sha256(path)
                by_hash.setdefault(digest, []).append(_format_file(path, digest))
                hashed_files += 1
            except OSError:
                continue

    groups = []
    duplicate_count = 0
    duplicate_bytes = 0

    for digest, files in by_hash.items():
        if len(files) < 2:
            continue

        ordered = sorted(files, key=lambda item: (item.modified, len(item.path), item.path.lower()))
        keep = ordered[0]
        remove_candidates = ordered[1:]
        duplicate_count += len(remove_candidates)
        duplicate_bytes += sum(item.size for item in remove_candidates)

        groups.append(
            {
                "hash": digest,
                "keep": keep.__dict__,
                "duplicates": [item.__dict__ for item in remove_candidates],
                "all_files": [item.__dict__ for item in ordered],
                "wasted_bytes": sum(item.size for item in remove_candidates),
            }
        )

    groups.sort(key=lambda group: group["wasted_bytes"], reverse=True)

    return {
        "folder": str(root),
        "groups": groups,
        "summary": {
            "scanned_files": scanned_files,
            "hashed_files": hashed_files,
            "duplicate_groups": len(groups),
            "duplicate_files": duplicate_count,
            "wasted_bytes": duplicate_bytes,
            "duration_seconds": round(time.time() - started, 2),
        },
    }


def quarantine_files(folder: str, file_paths: list[str]) -> dict:
    root = Path(folder).expanduser().resolve()
    quarantine_root = root / QUARANTINE_DIR_NAME
    quarantine_root.mkdir(exist_ok=True)

    moved = []
    skipped = []

    for raw_path in file_paths:
        source = Path(raw_path).expanduser().resolve()
        try:
            if not source.exists() or not source.is_file():
                skipped.append({"path": raw_path, "reason": "Datei nicht gefunden"})
                continue
            if root not in source.parents and source != root:
                skipped.append({"path": raw_path, "reason": "Datei liegt nicht im Scan-Ordner"})
                continue
            if QUARANTINE_DIR_NAME in source.parts:
                skipped.append({"path": raw_path, "reason": "Datei liegt bereits in Quarantäne"})
                continue

            relative = source.relative_to(root)
            target = quarantine_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)

            if target.exists():
                stem = target.stem
                suffix = target.suffix
                counter = 1
                while True:
                    candidate = target.with_name(f"{stem}__duplicate_{counter}{suffix}")
                    if not candidate.exists():
                        target = candidate
                        break
                    counter += 1

            shutil.move(str(source), str(target))
            moved.append({"from": str(source), "to": str(target)})
        except OSError as exc:
            skipped.append({"path": raw_path, "reason": str(exc)})

    return {"moved": moved, "skipped": skipped, "quarantine_folder": str(quarantine_root)}
