from __future__ import annotations

import threading
from collections import deque
from pathlib import Path
from typing import Iterable

# Preview is only allowed for files that appeared in a recent scan result. We keep a
# bounded, thread-safe registry so background scans and the synchronous endpoint both
# stay safe without leaking arbitrary filesystem access through the preview endpoint.
_MAX_PATHS = 200_000
_lock = threading.RLock()
_allowed: set[str] = set()
_order: deque[str] = deque()


def register(paths: Iterable[str]) -> None:
    with _lock:
        for raw in paths:
            try:
                resolved = str(Path(raw).expanduser().resolve())
            except (OSError, ValueError):
                continue
            if resolved in _allowed:
                continue
            _allowed.add(resolved)
            _order.append(resolved)
        while len(_order) > _MAX_PATHS:
            oldest = _order.popleft()
            _allowed.discard(oldest)


def register_result(result: dict) -> None:
    paths: list[str] = []
    for group in result.get("groups", []):
        for item in group.get("all_files", []):
            path = item.get("path")
            if path:
                paths.append(path)
    if paths:
        register(paths)


def is_allowed(resolved_path: str) -> bool:
    with _lock:
        return resolved_path in _allowed
