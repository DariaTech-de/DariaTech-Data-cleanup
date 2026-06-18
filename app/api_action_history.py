from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.apply_actions import apply_actions

router = APIRouter(prefix="/api/v1", tags=["actions"])


class ActionRequest(BaseModel):
    file_paths: list[str] = Field(default_factory=list)
    mode: str = "quarantine"


@router.get("/actions")
def list_actions(scan_id: str | None = None, limit: int = Query(default=200, ge=1, le=1000)) -> dict:
    return {"items": apply_actions.actions.list(scan_id=scan_id, limit=limit)}


@router.post("/scans/{scan_id}/actions")
def run_actions(scan_id: str, request: ActionRequest) -> dict:
    try:
        return apply_actions.run(scan_id, request.file_paths, mode=request.mode)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
