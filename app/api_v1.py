from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.job_runner import runner
from app.scanner import ScanOptions

router = APIRouter(prefix="/api/v1", tags=["enterprise"])


class ScanRequestV1(BaseModel):
    folders: list[str] = Field(default_factory=list)
    include_all_files: bool = False
    categories: list[str] = Field(default_factory=list)
    min_size_mb: float = 0
    max_size_mb: float | None = None
    exclude_patterns: list[str] = Field(default_factory=list)
    keep_rule: str = "oldest"
    find_exact: bool = True
    find_similar_images: bool = False
    image_similarity: int = Field(default=8, ge=0, le=20)


def _to_options(request: ScanRequestV1) -> ScanOptions:
    return ScanOptions(
        folders=request.folders,
        include_all_files=request.include_all_files,
        categories=request.categories or None,
        min_size_mb=request.min_size_mb,
        max_size_mb=request.max_size_mb,
        exclude_patterns=request.exclude_patterns or None,
        keep_rule=request.keep_rule,
        find_exact=request.find_exact,
        find_similar_images=request.find_similar_images,
        image_similarity=request.image_similarity,
    )


@router.get("/capabilities")
def capabilities() -> dict:
    return {
        "product": "Duplicat-Clearner Enterprise Foundation",
        "api_version": "v1",
        "local_first": True,
        "background_scans": True,
        "scan_history": True,
        "client_ready": True,
    }


@router.post("/scans", status_code=202)
def start_scan(request: ScanRequestV1) -> dict:
    scan_id = runner.start(_to_options(request))
    return {"scan_id": scan_id, "status_url": f"/api/v1/scans/{scan_id}"}


@router.get("/scans")
def list_scans(limit: int = Query(default=25, ge=1, le=100)) -> dict:
    return {"items": runner.list(limit=limit)}


@router.get("/scans/{scan_id}")
def scan_status(scan_id: str) -> dict:
    item = runner.status(scan_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Scan not found")
    return item


@router.get("/scans/{scan_id}/result")
def scan_result(scan_id: str) -> dict:
    result = runner.result(scan_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Scan result not available")
    return result
