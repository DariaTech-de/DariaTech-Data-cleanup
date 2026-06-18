from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import shutil
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Iterable, Literal

from PIL import Image, ImageOps, UnidentifiedImageError
from send2trash import send2trash

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tif", ".tiff", ".webp", ".heic", ".heif"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".wmv", ".m4v", ".mpeg", ".mpg", ".3gp", ".flv"}
AUDIO_EXTENSIONS = {".mp3", ".flac", ".wav", ".aac", ".ogg", ".m4a", ".wma", ".aiff"}
DOCUMENT_EXTENSIONS = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".csv", ".odt", ".rtf"}
ARCHIVE_EXTENSIONS = {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz"}
SUPPORTED_EXTENSIONS = (
    IMAGE_EXTENSIONS | VIDEO_EXTENSIONS | AUDIO_EXTENSIONS | DOCUMENT_EXTENSIONS | ARCHIVE_EXTENSIONS
)

QUARANTINE_DIR_NAME = ".quarantine-duplicates"
MANIFEST_NAME = ".manifest.jsonl"
PROTECTED_DIRS = {
    str(Path.home()).lower(),
    str(Path.home().anchor).lower(),
    "c:\\".lower(),
    "c:\\windows".lower(),
    "c:\\program files".lower(),
    "c:\\program files (x86)".lower(),
    "/".lower(),
}

KeepRule = Literal[
    "oldest", "newest", "largest", "smallest", "shortest_path", "longest_path", "highest_resolution"
]
DeleteMode = Literal["quarantine", "recycle_bin", "permanent"]
ConsolidateOperation = Literal["copy", "move"]
ConsolidateStructure = Literal["by_source", "preserve", "flat"]
ConflictPolicy = Literal["rename", "skip", "overwrite"]


class ScanCancelled(Exception):
    """Raised when a running scan or consolidation is cancelled by the user."""


@dataclass
class Progress:
    phase: str
    processed: int
    total: int
    message: str = ""

    @property
    def percent(self) -> float:
        if self.total <= 0:
            return 0.0
        return round(min(100.0, (self.processed / self.total) * 100), 1)

    def as_dict(self) -> dict:
        return {
            "phase": self.phase,
            "processed": self.processed,
            "total": self.total,
            "percent": self.percent,
            "message": self.message,
        }


ProgressCallback = Callable[[Progress], None]


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
class ConsolidateOptions:
    folders: list[str]
    target: str
    include_all_files: bool = False
    categories: list[str] | None = None
    min_size_mb: float = 0
    max_size_mb: float | None = None
    exclude_patterns: list[str] | None = None
    keep_rule: KeepRule = "highest_resolution"
    dedupe_similar_images: bool = False
    image_similarity: int = 8
    operation: ConsolidateOperation = "copy"
    structure: ConsolidateStructure = "by_source"
    on_conflict: ConflictPolicy = "rename"
    dry_run: bool = False


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


def _emit(progress: ProgressCallback | None, phase: str, processed: int, total: int, message: str = "") -> None:
    if progress is None:
        return
    try:
        progress(Progress(phase=phase, processed=processed, total=total, message=message))
    except Exception:
        # Progress reporting must never break the actual work.
        pass


def _check_cancel(cancel_event: threading.Event | None) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise ScanCancelled("Vorgang wurde abgebrochen.")


def _category(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in IMAGE_EXTENSIONS:
        return "image"
    if suffix in VIDEO_EXTENSIONS:
        return "video"
    if suffix in AUDIO_EXTENSIONS:
        return "audio"
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


def _iter_files(options: ScanOptions | ConsolidateOptions, roots: list[Path]) -> Iterable[Path]:
    selected_categories = set(options.categories or [])
    min_bytes = int(max(options.min_size_mb, 0) * 1024 * 1024)
    max_bytes = int(options.max_size_mb * 1024 * 1024) if options.max_size_mb else None

    for root in roots:
        for current_root, dirs, files in os.walk(root):
            dirs[:] = [
                d
                for d in dirs
                if d != QUARANTINE_DIR_NAME
                and not _matches_exclude(Path(current_root) / d, options.exclude_patterns)
            ]
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


def _collect_files(
    options: ScanOptions | ConsolidateOptions,
    roots: list[Path],
    progress: ProgressCallback | None = None,
    cancel_event: threading.Event | None = None,
) -> list[Path]:
    files: list[Path] = []
    for path in _iter_files(options, roots):
        files.append(path)
        if len(files) % 250 == 0:
            _check_cancel(cancel_event)
            _emit(progress, "enumerate", len(files), 0, f"{len(files):,} Dateien erfasst …")
    _emit(progress, "enumerate", len(files), len(files), f"{len(files):,} Dateien erfasst")
    return files


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
    except (OSError, UnidentifiedImageError, ValueError):
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


def _make_group(
    group_type: str,
    group_id: str,
    files: list[FileInfo],
    keep_rule: KeepRule,
    similarity_distance: int | None = None,
) -> dict:
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


def _cluster_similar_images(
    image_infos: list[FileInfo],
    threshold: int,
    cancel_event: threading.Event | None = None,
) -> list[list[FileInfo]]:
    clusters: list[list[FileInfo]] = []
    used: set[str] = set()
    for i, base in enumerate(image_infos):
        if base.path in used:
            continue
        cluster = [base]
        for other in image_infos[i + 1:]:
            if other.path in used:
                continue
            distance = _hamming_hex(base.image_fingerprint or "0", other.image_fingerprint or "0")
            if distance <= threshold:
                cluster.append(other)
        if len(cluster) > 1:
            for item in cluster:
                used.add(item.path)
            clusters.append(cluster)
        if i % 200 == 0:
            _check_cancel(cancel_event)
    return clusters


def scan_duplicates(
    options: ScanOptions,
    progress: ProgressCallback | None = None,
    cancel_event: threading.Event | None = None,
) -> dict:
    roots = _normalize_roots(options.folders)
    started = time.time()

    all_candidates = _collect_files(options, roots, progress, cancel_event)
    scanned_files = len(all_candidates)

    groups: list[dict] = []
    hashed_files = 0

    if options.find_exact:
        by_size: dict[int, list[Path]] = {}
        for path in all_candidates:
            try:
                by_size.setdefault(path.stat().st_size, []).append(path)
            except OSError:
                continue

        hash_targets = [path for bucket in by_size.values() if len(bucket) > 1 for path in bucket]
        total_to_hash = len(hash_targets)
        by_hash: dict[str, list[FileInfo]] = {}
        for index, path in enumerate(hash_targets, start=1):
            try:
                digest = _sha256(path)
                root = _root_for(path, roots)
                info = _format_file(
                    path, root, digest=digest, with_image_meta=path.suffix.lower() in IMAGE_EXTENSIONS
                )
                by_hash.setdefault(digest, []).append(info)
                hashed_files += 1
            except OSError:
                continue
            if index % 25 == 0 or index == total_to_hash:
                _check_cancel(cancel_event)
                _emit(progress, "hash", index, total_to_hash, f"Prüfe Inhalte: {index:,}/{total_to_hash:,}")

        for digest, files in by_hash.items():
            if len(files) < 2:
                continue
            groups.append(_make_group("exact", digest, files, options.keep_rule))

    similar_checked = 0
    if options.find_similar_images:
        image_paths = [p for p in all_candidates if p.suffix.lower() in IMAGE_EXTENSIONS]
        image_infos: list[FileInfo] = []
        total_images = len(image_paths)
        for index, path in enumerate(image_paths, start=1):
            try:
                root = _root_for(path, roots)
                info = _format_file(path, root, with_image_meta=True)
                if info.image_fingerprint:
                    image_infos.append(info)
            except OSError:
                continue
            if index % 25 == 0 or index == total_images:
                _check_cancel(cancel_event)
                _emit(progress, "fingerprint", index, total_images, f"Bild-Fingerprints: {index:,}/{total_images:,}")

        similar_checked = len(image_infos)
        for cluster in _cluster_similar_images(image_infos, options.image_similarity, cancel_event):
            group_id = cluster[0].image_fingerprint or str(len(groups))
            groups.append(
                _make_group("similar_image", group_id, cluster, options.keep_rule, options.image_similarity)
            )

    _emit(progress, "finalize", 1, 1, "Ergebnisse werden aufbereitet …")
    groups.sort(key=lambda group: group["wasted_bytes"], reverse=True)
    duplicate_count = sum(len(group["duplicates"]) for group in groups)
    duplicate_bytes = sum(group["wasted_bytes"] for group in groups)

    by_category: dict[str, int] = {}
    by_root: dict[str, int] = {}
    total_bytes = 0
    for path in all_candidates:
        category = _category(path)
        by_category[category] = by_category.get(category, 0) + 1
        root_key = str(_root_for(path, roots))
        by_root[root_key] = by_root.get(root_key, 0) + 1
        try:
            total_bytes += path.stat().st_size
        except OSError:
            continue

    return {
        "folders": [str(root) for root in roots],
        "groups": groups,
        "summary": {
            "scanned_files": scanned_files,
            "scanned_bytes": total_bytes,
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


def _validate_target(target_raw: str, roots: list[Path]) -> Path:
    if not target_raw or not target_raw.strip():
        raise ValueError("Bitte einen Zielordner angeben.")
    target = Path(target_raw).expanduser().resolve()
    if _is_protected_root(target):
        raise ValueError(f"Dieser Zielordner ist aus Sicherheitsgründen gesperrt: {target}")
    for root in roots:
        if target == root:
            raise ValueError("Der Zielordner darf nicht einer der Quellordner sein.")
        if root in target.parents:
            raise ValueError("Der Zielordner darf nicht innerhalb eines Quellordners liegen.")
        if target in root.parents:
            raise ValueError("Ein Quellordner darf nicht innerhalb des Zielordners liegen.")
    return target


def _safe_component(name: str) -> str:
    cleaned = name.strip().strip(".") or "Ordner"
    for char in '<>:"/\\|?*':
        cleaned = cleaned.replace(char, "_")
    return cleaned


def _relative_to_root(file: FileInfo) -> Path:
    src_root = Path(file.root)
    try:
        return Path(file.path).relative_to(src_root)
    except ValueError:
        return Path(file.name)


def _target_path(file: FileInfo, target: Path, structure: ConsolidateStructure) -> Path:
    relative = _relative_to_root(file)
    if structure == "flat":
        return target / file.name
    if structure == "by_source":
        return target / _safe_component(Path(file.root).name) / relative
    return target / relative


def _resolve_destination(
    desired: Path, used: set[str], on_conflict: ConflictPolicy
) -> Path | None:
    key = str(desired).lower()
    if key not in used and not desired.exists():
        return desired
    if on_conflict == "overwrite":
        return desired
    if on_conflict == "skip":
        return None
    stem = desired.stem
    suffix = desired.suffix
    counter = 1
    while True:
        candidate = desired.with_name(f"{stem} ({counter}){suffix}")
        if str(candidate).lower() not in used and not candidate.exists():
            return candidate
        counter += 1


def consolidate_clean(
    options: ConsolidateOptions,
    progress: ProgressCallback | None = None,
    cancel_event: threading.Event | None = None,
) -> dict:
    """Scan multiple source folders and build a clean, duplicate-free copy in a new target folder."""
    roots = _normalize_roots(options.folders)
    target = _validate_target(options.target, roots)
    started = time.time()

    candidates = _collect_files(options, roots, progress, cancel_event)
    source_files = len(candidates)
    source_bytes = 0

    needs_image_meta = options.keep_rule == "highest_resolution" or options.dedupe_similar_images

    # Group exact duplicates by size + hash; unique sizes are unique by definition.
    by_size: dict[int, list[Path]] = {}
    for path in candidates:
        try:
            size = path.stat().st_size
        except OSError:
            continue
        source_bytes += size
        by_size.setdefault(size, []).append(path)

    representatives: list[FileInfo] = []
    exact_removed = 0
    total = len(candidates)
    processed = 0

    for size, bucket in by_size.items():
        if len(bucket) == 1:
            path = bucket[0]
            try:
                info = _format_file(path, _root_for(path, roots), with_image_meta=needs_image_meta)
                representatives.append(info)
            except OSError:
                pass
            processed += 1
            continue

        by_hash: dict[str, list[FileInfo]] = {}
        for path in bucket:
            try:
                digest = _sha256(path)
                info = _format_file(path, _root_for(path, roots), digest=digest, with_image_meta=needs_image_meta)
                by_hash.setdefault(digest, []).append(info)
            except OSError:
                pass
            processed += 1
            if processed % 25 == 0 or processed == total:
                _check_cancel(cancel_event)
                _emit(progress, "hash", processed, total, f"Vergleiche Inhalte: {processed:,}/{total:,}")
        for files in by_hash.values():
            ordered = sorted(files, key=lambda item: _score(item, options.keep_rule))
            representatives.append(ordered[0])
            exact_removed += len(ordered) - 1

    similar_removed = 0
    if options.dedupe_similar_images:
        images = [info for info in representatives if info.category == "image" and info.image_fingerprint]
        non_images = [info for info in representatives if info.category != "image" or not info.image_fingerprint]
        clusters = _cluster_similar_images(images, options.image_similarity, cancel_event)
        clustered_paths: set[str] = set()
        kept_images: list[FileInfo] = []
        for cluster in clusters:
            ordered = sorted(cluster, key=lambda item: _score(item, options.keep_rule))
            kept_images.append(ordered[0])
            similar_removed += len(ordered) - 1
            clustered_paths.update(item.path for item in cluster)
        kept_images.extend(info for info in images if info.path not in clustered_paths)
        representatives = non_images + kept_images

    representatives.sort(key=lambda info: info.path.lower())

    # Build the copy/move plan with conflict-safe destinations.
    used: set[str] = set()
    operations: list[dict] = []
    skipped: list[dict] = []
    planned_bytes = 0
    for info in representatives:
        desired = _target_path(info, target, options.structure)
        destination = _resolve_destination(desired, used, options.on_conflict)
        if destination is None:
            skipped.append({"path": info.path, "reason": "Ziel existiert bereits (übersprungen)"})
            continue
        used.add(str(destination).lower())
        planned_bytes += info.size
        operations.append({"from": info.path, "to": str(destination), "size": info.size})

    executed: list[dict] = []
    errors: list[dict] = []
    if not options.dry_run:
        if not target.exists():
            target.mkdir(parents=True, exist_ok=True)
        total_ops = len(operations)
        for index, op in enumerate(operations, start=1):
            source = Path(op["from"])
            destination = Path(op["to"])
            try:
                destination.parent.mkdir(parents=True, exist_ok=True)
                if options.operation == "move":
                    shutil.move(str(source), str(destination))
                else:
                    shutil.copy2(str(source), str(destination))
                executed.append(op)
            except OSError as exc:
                errors.append({"path": str(source), "reason": str(exc)})
            if index % 10 == 0 or index == total_ops:
                _check_cancel(cancel_event)
                verb = "Verschiebe" if options.operation == "move" else "Kopiere"
                _emit(progress, "consolidate", index, total_ops, f"{verb}: {index:,}/{total_ops:,}")

    output_files = len(operations)
    output_bytes = planned_bytes
    sample_limit = 1000
    return {
        "target": str(target),
        "operations": operations[:sample_limit],
        "operations_truncated": len(operations) > sample_limit,
        "executed_count": len(executed),
        "skipped": skipped[:sample_limit],
        "errors": errors[:sample_limit],
        "summary": {
            "source_files": source_files,
            "source_bytes": source_bytes,
            "output_files": output_files,
            "output_bytes": output_bytes,
            "removed_exact": exact_removed,
            "removed_similar": similar_removed,
            "removed_total": exact_removed + similar_removed,
            "saved_bytes": max(source_bytes - output_bytes, 0),
            "errors": len(errors),
            "skipped": len(skipped),
            "operation": options.operation,
            "structure": options.structure,
            "dry_run": options.dry_run,
            "duration_seconds": round(time.time() - started, 2),
        },
        "options": asdict(options),
    }


def _append_manifest(quarantine_root: Path, entry: dict) -> None:
    try:
        with (quarantine_root / MANIFEST_NAME).open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


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
            _append_manifest(
                quarantine_root,
                {"original": str(source), "quarantined": str(target), "moved_at": time.time()},
            )
            moved.append({"from": str(source), "to": str(target)})
        except OSError as exc:
            skipped.append({"path": raw_path, "reason": str(exc)})

    return {"changed": moved, "skipped": skipped, "mode": mode}


def list_quarantine(roots: list[str]) -> dict:
    root_paths = _normalize_roots(roots)
    entries: list[dict] = []
    for root in root_paths:
        manifest = root / QUARANTINE_DIR_NAME / MANIFEST_NAME
        if not manifest.exists():
            continue
        try:
            for line in manifest.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                quarantined = Path(record.get("quarantined", ""))
                record["available"] = quarantined.exists()
                record["root"] = str(root)
                entries.append(record)
        except (OSError, json.JSONDecodeError):
            continue
    entries.sort(key=lambda item: item.get("moved_at", 0), reverse=True)
    return {"items": entries}


def restore_quarantine(roots: list[str], quarantined_paths: list[str] | None = None) -> dict:
    root_paths = _normalize_roots(roots)
    wanted = {str(Path(p).expanduser().resolve()) for p in quarantined_paths} if quarantined_paths else None
    restored: list[dict] = []
    skipped: list[dict] = []
    for root in root_paths:
        manifest = root / QUARANTINE_DIR_NAME / MANIFEST_NAME
        if not manifest.exists():
            continue
        try:
            lines = manifest.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            quarantined = Path(record.get("quarantined", ""))
            original = Path(record.get("original", ""))
            if wanted is not None and str(quarantined.resolve()) not in wanted:
                continue
            if not quarantined.exists():
                skipped.append({"path": str(quarantined), "reason": "Datei nicht mehr in Quarantäne"})
                continue
            try:
                original.parent.mkdir(parents=True, exist_ok=True)
                final = original
                if final.exists():
                    counter = 1
                    while True:
                        candidate = final.with_name(f"{final.stem}__restored_{counter}{final.suffix}")
                        if not candidate.exists():
                            final = candidate
                            break
                        counter += 1
                shutil.move(str(quarantined), str(final))
                restored.append({"from": str(quarantined), "to": str(final)})
            except OSError as exc:
                skipped.append({"path": str(quarantined), "reason": str(exc)})
    return {"restored": restored, "skipped": skipped}


def export_report(scan_result: dict, format: Literal["json", "csv"] = "json") -> tuple[bytes, str, str]:
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    if format == "csv":
        handle = io.StringIO()
        writer = csv.writer(handle, delimiter=";")
        writer.writerow(
            ["group_type", "group_id", "recommendation", "path", "root", "size", "modified", "category", "width", "height"]
        )
        for group in scan_result.get("groups", []):
            for item in group.get("all_files", []):
                recommendation = "KEEP" if item.get("path") == group.get("keep", {}).get("path") else "REMOVE"
                writer.writerow(
                    [
                        group.get("type"),
                        group.get("id"),
                        recommendation,
                        item.get("path"),
                        item.get("root"),
                        item.get("size"),
                        item.get("modified"),
                        item.get("category"),
                        item.get("width"),
                        item.get("height"),
                    ]
                )
        return handle.getvalue().encode("utf-8-sig"), f"duplicate-report-{timestamp}.csv", "text/csv"

    payload = json.dumps(scan_result, indent=2, ensure_ascii=False).encode("utf-8")
    return payload, f"duplicate-report-{timestamp}.json", "application/json"
