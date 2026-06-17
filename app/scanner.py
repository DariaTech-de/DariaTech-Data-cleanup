from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import shutil
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Literal

from PIL import Image, ImageOps, UnidentifiedImageError
from send2trash import send2trash

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tif", ".tiff", ".webp"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".wmv", ".m4v", ".mpeg", ".mpg", ".3gp"}
DOCUMENT_EXTENSIONS = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".csv"}
ARCHIVE_EXTENSIONS = {".zip", ".rar", ".7z", ".tar", ".gz"}
SUPPORTED_EXTENSIONS = IMAGE_EXTENSIONS | VIDEO_EXTENSIONS | DOCUMENT_EXTENSIONS | ARCHIVE_EXTENSIONS

QUARANTINE_DIR_NAME = ".quarantine-duplicates"
PROTECTED_DIRS = {
    str(Path.home()).lower(),
    str(Path.home().anchor).lower(),
    "c:\\".lower(),
    "c:\\windows".lower(),
    "c:\\program files".lower(),
    "c:\\program files (x86)".lower(),
}

KeepRule = Literal["oldest", "newest", "largest", "smallest", "shortest_path", "longest_path", "highest_resolution"]
DeleteMode = Literal["quarantine", "recycle_bin", "permanent"]


@dataclass(frozen=True)
class ScanOptions:
    folders: list[str]
    include_all_files: bool = False
    categories: list[str] | None = None
    min_size_mb: float = 0
    max_size_mb: float | None = None
    exclude_patterns: list[str] | None = None
    keep_rule: KeepRule = "oldest"
    find_exact: bool = True
    find_similar_images: bool = False
    image_similarity: int = 8


@dataclass(frozen=True)
class FileInfo:
    path: str
    root: str
    name: str
    extension: str
    category: str
    size: int
    modified: float
    sha256: str | None = None
    width: int | None = None
    height: int | None = None
    image_fingerprint: str | None = None


def _category(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in IMAGE_EXTENSIONS:
        return "image"
    if suffix in VIDEO_EXTENSIONS:
        return "video"
    if suffix in DOCUMENT_EXTENSIONS:
        return "document"
    if suffix in ARCHIVE_EXTENSIONS:
        return "archive"
    return "other"


def _is_protected_root(path: Path) -> bool:
    resolved = str(path.resolve()).rstrip("\\/").lower()
    return resolved in PROTECTED_DIRS


def _normalize_roots(folders: list[str]) -> list[Path]:
    roots: list[Path] = []
    seen: set[str] = set()
    for folder in folders:
        if not folder.strip():
            continue
        root = Path(folder).expanduser().resolve()
        if not root.exists() or not root.is_dir():
            raise ValueError(f"Ordner nicht gefunden: {folder}")
        if _is_protected_root(root):
            raise ValueError(f"Dieser Ordner ist aus Sicherheitsgründen gesperrt: {root}")
        key = str(root).lower()
        if key not in seen:
            seen.add(key)
            roots.append(root)
    if not roots:
        raise ValueError("Bitte mindestens einen gültigen Ordner angeben.")
    return roots


def _matches_exclude(path: Path, patterns: list[str] | None) -> bool:
    if not patterns:
        return False
    value = str(path).lower()
    return any(pattern.strip().lower() and pattern.strip().lower() in value for pattern in patterns)


def _iter_files(options: ScanOptions, roots: list[Path]) -> Iterable[Path]:
    selected_categories = set(options.categories or [])
    min_bytes = int(max(options.min_size_mb, 0) * 1024 * 1024)
    max_bytes = int(options.max_size_mb * 1024 * 1024) if options.max_size_mb else None

    for root in roots:
        for current_root, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if d != QUARANTINE_DIR_NAME and not _matches_exclude(Path(current_root) / d, options.exclude_patterns)]
            for filename in files:
                path = Path(current_root) / filename
                try:
                    if not path.is_file() or _matches_exclude(path, options.exclude_patterns):
                        continue
                    stat = path.stat()
                    suffix = path.suffix.lower()
                    category = _category(path)
                    if not options.include_all_files and suffix not in SUPPORTED_EXTENSIONS:
                        continue
                    if selected_categories and category not in selected_categories:
                        continue
                    if stat.st_size < min_bytes:
                        continue
                    if max_bytes is not None and stat.st_size > max_bytes:
                        continue
                    yield path
                except OSError:
                    continue


def _root_for(path: Path, roots: list[Path]) -> Path:
    resolved = path.resolve()
    matches = [root for root in roots if root == resolved or root in resolved.parents]
    return max(matches, key=lambda p: len(str(p))) if matches else roots[0]


def _sha256(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _image_metadata(path: Path) -> tuple[int | None, int | None, str | None]:
    if path.suffix.lower() not in IMAGE_EXTENSIONS:
        return None, None, None
    try:
        with Image.open(path) as image:
            image = ImageOps.exif_transpose(image)
            width, height = image.size
            fingerprint = _dhash(image)
            return width, height, fingerprint
    except (OSError, UnidentifiedImageError):
        return None, None, None


def _dhash(image: Image.Image) -> str:
    # Difference hash: stable enough for resized/compressed versions of the same image.
    gray = image.convert("L").resize((9, 8), Image.Resampling.LANCZOS)
    pixels = list(gray.getdata())
    bits = []
    for row in range(8):
        start = row * 9
        for col in range(8):
            bits.append(1 if pixels[start + col] > pixels[start + col + 1] else 0)
    value = 0
    for bit in bits:
        value = (value << 1) | bit
    return f"{value:016x}"


def _hamming_hex(a: str, b: str) -> int:
    return (int(a, 16) ^ int(b, 16)).bit_count()


def _format_file(path: Path, root: Path, digest: str | None = None, with_image_meta: bool = False) -> FileInfo:
    stat = path.stat()
    width = height = None
    fingerprint = None
    if with_image_meta:
        width, height, fingerprint = _image_metadata(path)
    return FileInfo(
        path=str(path),
        root=str(root),
        name=path.name,
        extension=path.suffix.lower(),
        category=_category(path),
        size=stat.st_size,
        modified=stat.st_mtime,
        sha256=digest,
        width=width,
        height=height,
        image_fingerprint=fingerprint,
    )


def _score(file: FileInfo, rule: KeepRule) -> tuple:
    resolution = (file.width or 0) * (file.height or 0)
    if rule == "newest":
        return (-file.modified, -resolution, -file.size, file.path.lower())
    if rule == "largest":
        return (-file.size, -resolution, file.modified, file.path.lower())
    if rule == "smallest":
        return (file.size, file.modified, file.path.lower())
    if rule == "shortest_path":
        return (len(file.path), file.modified, file.path.lower())
    if rule == "longest_path":
        return (-len(file.path), file.modified, file.path.lower())
    if rule == "highest_resolution":
        return (-resolution, -file.size, file.modified, file.path.lower())
    return (file.modified, -resolution, -file.size, file.path.lower())


def _make_group(group_type: str, group_id: str, files: list[FileInfo], keep_rule: KeepRule, similarity_distance: int | None = None) -> dict:
    ordered = sorted(files, key=lambda item: _score(item, keep_rule))
    keep = ordered[0]
    remove_candidates = ordered[1:]
    return {
        "type": group_type,
        "id": group_id,
        "keep_rule": keep_rule,
        "similarity_distance": similarity_distance,
        "keep": asdict(keep),
        "duplicates": [asdict(item) for item in remove_candidates],
        "all_files": [asdict(item) for item in ordered],
        "wasted_bytes": sum(item.size for item in remove_candidates),
    }


def scan_duplicates(options: ScanOptions) -> dict:
    roots = _normalize_roots(options.folders)
    started = time.time()

    all_candidates = list(_iter_files(options, roots))
    scanned_files = len(all_candidates)

    groups: list[dict] = []
    exact_paths_in_groups: set[str] = set()
    hashed_files = 0

    if options.find_exact:
        by_size: dict[int, list[Path]] = {}
        for path in all_candidates:
            try:
                by_size.setdefault(path.stat().st_size, []).append(path)
            except OSError:
                continue

        by_hash: dict[str, list[FileInfo]] = {}
        for same_size_files in by_size.values():
            if len(same_size_files) < 2:
                continue
            for path in same_size_files:
                try:
                    digest = _sha256(path)
                    root = _root_for(path, roots)
                    info = _format_file(path, root, digest=digest, with_image_meta=path.suffix.lower() in IMAGE_EXTENSIONS)
                    by_hash.setdefault(digest, []).append(info)
                    hashed_files += 1
                except OSError:
                    continue

        for digest, files in by_hash.items():
            if len(files) < 2:
                continue
            groups.append(_make_group("exact", digest, files, options.keep_rule))
            exact_paths_in_groups.update(file.path for file in files)

    similar_checked = 0
    if options.find_similar_images:
        image_infos: list[FileInfo] = []
        for path in all_candidates:
            if path.suffix.lower() not in IMAGE_EXTENSIONS:
                continue
            try:
                root = _root_for(path, roots)
                info = _format_file(path, root, with_image_meta=True)
                if info.image_fingerprint:
                    image_infos.append(info)
            except OSError:
                continue

        used: set[str] = set()
        for i, base in enumerate(image_infos):
            if base.path in used:
                continue
            cluster = [base]
            for other in image_infos[i + 1 :]:
                if other.path in used:
                    continue
                similar_checked += 1
                distance = _hamming_hex(base.image_fingerprint or "0", other.image_fingerprint or "0")
                if distance <= options.image_similarity:
                    cluster.append(other)
            if len(cluster) > 1:
                for item in cluster:
                    used.add(item.path)
                group_id = cluster[0].image_fingerprint or str(len(groups))
                groups.append(_make_group("similar_image", group_id, cluster, options.keep_rule, options.image_similarity))

    groups.sort(key=lambda group: group["wasted_bytes"], reverse=True)
    duplicate_count = sum(len(group["duplicates"]) for group in groups)
    duplicate_bytes = sum(group["wasted_bytes"] for group in groups)

    by_category: dict[str, int] = {}
    by_root: dict[str, int] = {}
    for path in all_candidates:
        by_category[_category(path)] = by_category.get(_category(path), 0) + 1
        by_root[str(_root_for(path, roots))] = by_root.get(str(_root_for(path, roots)), 0) + 1

    return {
        "folders": [str(root) for root in roots],
        "groups": groups,
        "summary": {
            "scanned_files": scanned_files,
            "hashed_files": hashed_files,
            "similar_images_checked": similar_checked,
            "duplicate_groups": len(groups),
            "duplicate_files": duplicate_count,
            "wasted_bytes": duplicate_bytes,
            "duration_seconds": round(time.time() - started, 2),
            "by_category": by_category,
            "by_root": by_root,
        },
        "options": asdict(options),
    }


def clean_files(roots: list[str], file_paths: list[str], mode: DeleteMode = "quarantine") -> dict:
    root_paths = _normalize_roots(roots)
    moved = []
    skipped = []

    for raw_path in file_paths:
        source = Path(raw_path).expanduser().resolve()
        try:
            if not source.exists() or not source.is_file():
                skipped.append({"path": raw_path, "reason": "Datei nicht gefunden"})
                continue
            root = _root_for(source, root_paths)
            if root not in source.parents and source != root:
                skipped.append({"path": raw_path, "reason": "Datei liegt nicht in den Scan-Ordnern"})
                continue
            if QUARANTINE_DIR_NAME in source.parts:
                skipped.append({"path": raw_path, "reason": "Datei liegt bereits in Quarantäne"})
                continue

            if mode == "recycle_bin":
                send2trash(str(source))
                moved.append({"from": str(source), "to": "Windows-Papierkorb"})
                continue
            if mode == "permanent":
                source.unlink()
                moved.append({"from": str(source), "to": "endgültig gelöscht"})
                continue

            quarantine_root = root / QUARANTINE_DIR_NAME
            quarantine_root.mkdir(exist_ok=True)
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

    return {"changed": moved, "skipped": skipped, "mode": mode}


def export_report(scan_result: dict, format: Literal["json", "csv"] = "json") -> tuple[bytes, str, str]:
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    if format == "csv":
        handle = io.StringIO()
        writer = csv.writer(handle, delimiter=";")
        writer.writerow(["group_type", "group_id", "recommendation", "path", "root", "size", "modified", "category", "width", "height"])
        for group in scan_result.get("groups", []):
            for item in group.get("all_files", []):
                recommendation = "KEEP" if item.get("path") == group.get("keep", {}).get("path") else "REMOVE"
                writer.writerow([
                    group.get("type"), group.get("id"), recommendation, item.get("path"), item.get("root"), item.get("size"),
                    item.get("modified"), item.get("category"), item.get("width"), item.get("height"),
                ])
        return handle.getvalue().encode("utf-8-sig"), f"duplicate-report-{timestamp}.csv", "text/csv"

    payload = json.dumps(scan_result, indent=2, ensure_ascii=False).encode("utf-8")
    return payload, f"duplicate-report-{timestamp}.json", "application/json"
