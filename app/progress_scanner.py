from __future__ import annotations

import time
import uuid
from dataclasses import asdict
from threading import Event
from typing import Callable

from app.scanner import (
    IMAGE_EXTENSIONS,
    FileInfo,
    ScanOptions,
    _format_file,
    _hamming_hex,
    _iter_files,
    _make_group,
    _normalize_roots,
    _root_for,
    _sha256,
)

ProgressCallback = Callable[[str, int, int | None, str], None]


class ScanCancelled(RuntimeError):
    """Raised when a scan receives a stop signal."""


class UnionFind:
    def __init__(self, size: int) -> None:
        self.parent = list(range(size))

    def find(self, value: int) -> int:
        while self.parent[value] != value:
            self.parent[value] = self.parent[self.parent[value]]
            value = self.parent[value]
        return value

    def union(self, left: int, right: int) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root != right_root:
            self.parent[right_root] = left_root


class BKTree:
    """BK-tree for scalable near-neighbour lookup on 64-bit image hashes."""

    def __init__(self) -> None:
        self.root: tuple[str, int, dict[int, object]] | None = None

    def add(self, value: str, index: int) -> None:
        node = (value, index, {})
        if self.root is None:
            self.root = node
            return
        current = self.root
        while True:
            current_value, _, children = current
            distance = _hamming_hex(value, current_value)
            child = children.get(distance)
            if child is None:
                children[distance] = node
                return
            current = child  # type: ignore[assignment]

    def query(self, value: str, limit: int) -> list[int]:
        if self.root is None:
            return []
        result: list[int] = []
        stack = [self.root]
        while stack:
            current_value, current_index, children = stack.pop()
            distance = _hamming_hex(value, current_value)
            if distance <= limit:
                result.append(current_index)
            lower = distance - limit
            upper = distance + limit
            for edge_distance, child in children.items():
                if lower <= edge_distance <= upper:
                    stack.append(child)  # type: ignore[arg-type]
        return result


def _emit(callback: ProgressCallback | None, stage: str, current: int, total: int | None, message: str) -> None:
    if callback:
        callback(stage, current, total, message)


def _check(cancel_event: Event | None) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise ScanCancelled("Scan wurde abgebrochen.")


def _discover(options: ScanOptions, roots: list, progress: ProgressCallback | None, cancel_event: Event | None) -> tuple[list, dict, dict, dict]:
    candidates = []
    by_size: dict[int, list] = {}
    by_category: dict[str, int] = {}
    by_root: dict[str, int] = {}
    _emit(progress, "discover", 0, None, "Dateien werden erfasst …")
    for index, path in enumerate(_iter_files(options, roots), start=1):
        _check(cancel_event)
        candidates.append(path)
        try:
            if options.find_exact:
                by_size.setdefault(path.stat().st_size, []).append(path)
            category = path.suffix.lower()
            by_category[category] = by_category.get(category, 0) + 1
            root = str(_root_for(path, roots))
            by_root[root] = by_root.get(root, 0) + 1
        except OSError:
            continue
        if index % 250 == 0:
            _emit(progress, "discover", index, None, f"{index} Dateien erfasst …")
    return candidates, by_size, by_category, by_root


def _exact_groups(options: ScanOptions, roots: list, by_size: dict, progress: ProgressCallback | None, cancel_event: Event | None) -> tuple[list[dict], int]:
    groups: list[dict] = []
    hashed_files = 0
    size_sets = [items for items in by_size.values() if len(items) > 1]
    total = sum(len(items) for items in size_sets)
    by_hash: dict[str, list[FileInfo]] = {}
    _emit(progress, "hash", 0, total, "Exakte Kandidaten werden per SHA-256 geprüft …")
    for paths in size_sets:
        for path in paths:
            _check(cancel_event)
            try:
                digest = _sha256(path)
                info = _format_file(path, _root_for(path, roots), digest=digest, with_image_meta=path.suffix.lower() in IMAGE_EXTENSIONS)
                by_hash.setdefault(digest, []).append(info)
                hashed_files += 1
            except OSError:
                continue
            if hashed_files % 100 == 0:
                _emit(progress, "hash", hashed_files, total, f"{hashed_files}/{total} Dateien geprüft …")
    for digest, files in by_hash.items():
        if len(files) > 1:
            groups.append(_make_group("exact", digest, files, options.keep_rule))
    return groups, hashed_files


def _similar_image_groups(options: ScanOptions, roots: list, candidates: list, progress: ProgressCallback | None, cancel_event: Event | None) -> tuple[list[dict], int]:
    image_paths = [path for path in candidates if path.suffix.lower() in IMAGE_EXTENSIONS]
    image_infos: list[FileInfo] = []
    _emit(progress, "image_fingerprint", 0, len(image_paths), "Bild-Fingerprints werden berechnet …")
    for index, path in enumerate(image_paths, start=1):
        _check(cancel_event)
        try:
            info = _format_file(path, _root_for(path, roots), with_image_meta=True)
            if info.image_fingerprint:
                image_infos.append(info)
        except OSError:
            continue
        if index % 100 == 0:
            _emit(progress, "image_fingerprint", index, len(image_paths), f"{index}/{len(image_paths)} Bilder analysiert …")

    tree = BKTree()
    union_find = UnionFind(len(image_infos))
    checked = 0
    _emit(progress, "image_cluster", 0, len(image_infos), "Ähnliche Bilder werden gruppiert …")
    for index, info in enumerate(image_infos):
        _check(cancel_event)
        matches = tree.query(info.image_fingerprint or "0", options.image_similarity)
        checked += len(matches)
        for other_index in matches:
            union_find.union(index, other_index)
        tree.add(info.image_fingerprint or "0", index)
        if (index + 1) % 250 == 0:
            _emit(progress, "image_cluster", index + 1, len(image_infos), f"{index + 1}/{len(image_infos)} Bilder gruppiert …")

    clusters: dict[int, list[FileInfo]] = {}
    for index, info in enumerate(image_infos):
        clusters.setdefault(union_find.find(index), []).append(info)
    groups = [
        _make_group("similar_image", cluster[0].image_fingerprint or str(uuid.uuid4()), cluster, options.keep_rule, options.image_similarity)
        for cluster in clusters.values()
        if len(cluster) > 1
    ]
    return groups, checked


def scan_with_progress(options: ScanOptions, progress: ProgressCallback | None = None, cancel_event: Event | None = None) -> dict:
    started = time.time()
    roots = _normalize_roots(options.folders)
    candidates, by_size, by_category, by_root = _discover(options, roots, progress, cancel_event)
    groups: list[dict] = []
    hashed_files = 0
    similar_checked = 0
    if options.find_exact:
        exact, hashed_files = _exact_groups(options, roots, by_size, progress, cancel_event)
        groups.extend(exact)
    if options.find_similar_images:
        similar, similar_checked = _similar_image_groups(options, roots, candidates, progress, cancel_event)
        groups.extend(similar)
    groups.sort(key=lambda group: group["wasted_bytes"], reverse=True)
    _emit(progress, "complete", len(candidates), len(candidates), "Scan abgeschlossen.")
    return {
        "scan_id": str(uuid.uuid4()),
        "folders": [str(root) for root in roots],
        "groups": groups,
        "summary": {
            "scanned_files": len(candidates),
            "hashed_files": hashed_files,
            "similar_images_checked": similar_checked,
            "duplicate_groups": len(groups),
            "duplicate_files": sum(len(group["duplicates"]) for group in groups),
            "wasted_bytes": sum(group["wasted_bytes"] for group in groups),
            "duration_seconds": round(time.time() - started, 2),
            "by_category": by_category,
            "by_root": by_root,
        },
        "options": asdict(options),
    }
