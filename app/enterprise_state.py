from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ScanRecord:
    id: str
    status: str
    message: str
    created_at: float
    result: dict[str, Any] | None = None


class InMemoryScanState:
    def __init__(self) -> None:
        self.records: dict[str, ScanRecord] = {}

    def create(self) -> str:
        record_id = str(uuid.uuid4())
        self.records[record_id] = ScanRecord(
            id=record_id,
            status="queued",
            message="created",
            created_at=time.time(),
        )
        return record_id


state = InMemoryScanState()
