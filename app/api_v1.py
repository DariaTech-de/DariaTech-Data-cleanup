from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.job_runner import runner
from app.scanner import ConsolidateOptions, ScanOptions, export_report

router = APIRouter(prefix="/api/v1", tags=["enterprise"])

KEEP_RULES = {"oldest", "newest", "largest", "smallest", "shortest_path", "longest_path", "highest_resolution"}


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


class ConsolidateRequestV1(BaseModel):
    folders: list[str] = Field(default_factory=list)
    target: str = ""
    include_all_files: bool = False
    categories: list[str] = Field(default_factory=list)
    min_size_mb: float = 0
    max_size_mb: float | None = None
    exclude_patterns: list[str] = Field(default_factory=list)
    keep_rule: str = "highest_resolution"
    dedupe_similar_images: bool = False
    image_similarity: int = Field(default=8, ge=0, le=20)
    operation: str = Field(default="copy", pattern="^(copy|move)$")
    structure: str = Field(default="by_source", pattern="^(by_source|preserve|flat)$")
    on_conflict: str = Field(default="rename", pattern="^(rename|skip|overwrite)$")
    dry_run: bool = False


class ProfileRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    config: dict = Field(default_factory=dict)


def _normalized_keep_rule(value: str) -> str:
    return value if value in KEEP_RULES else "oldest"


def _to_scan_options(request: ScanRequestV1) -> ScanOptions:
    return ScanOptions(
        folders=request.folders,
        include_all_files=request.include_all_files,
        categories=request.categories or None,
        min_size_mb=request.min_size_mb,
        max_size_mb=request.max_size_mb,
        exclude_patterns=request.exclude_patterns or None,
        keep_rule=_normalized_keep_rule(request.keep_rule),
        find_exact=request.find_exact,
        find_similar_images=request.find_similar_images,
        image_similarity=request.image_similarity,
    )


def _to_consolidate_options(request: ConsolidateRequestV1) -> ConsolidateOptions:
    return ConsolidateOptions(
        folders=request.folders,
        target=request.target,
        include_all_files=request.include_all_files,
        categories=request.categories or None,
        min_size_mb=request.min_size_mb,
        max_size_mb=request.max_size_mb,
        exclude_patterns=request.exclude_patterns or None,
        keep_rule=_normalized_keep_rule(request.keep_rule),
        dedupe_similar_images=request.dedupe_similar_images,
        image_similarity=request.image_similarity,
        operation=request.operation,
        structure=request.structure,
        on_conflict=request.on_conflict,
        dry_run=request.dry_run,
    )


@router.get("/capabilities")
def capabilities() -> dict:
    return {
        "product": "Duplicat-Clearner Enterprise",
        "api_version": "v1",
        "local_first": True,
        "background_scans": True,
        "live_progress": True,
        "cancellable": True,
        "consolidation": True,
        "scan_history": True,
        "profiles": True,
        "quarantine_undo": True,
        "client_ready": True,
    }


@router.post("/scans", status_code=202)
def start_scan(request: ScanRequestV1) -> dict:
    scan_id = runner.start(_to_scan_options(request))
    return {"job_id": scan_id, "scan_id": scan_id, "status_url": f"/api/v1/jobs/{scan_id}"}


@router.post("/consolidations", status_code=202)
def start_consolidation(request: ConsolidateRequestV1) -> dict:
    job_id = runner.start_consolidation(_to_consolidate_options(request))
    return {"job_id": job_id, "status_url": f"/api/v1/jobs/{job_id}"}


@router.get("/jobs")
def list_jobs(limit: int = Query(default=25, ge=1, le=100), kind: str | None = None) -> dict:
    return {"items": runner.list(limit=limit, kind=kind)}


@router.get("/jobs/{job_id}")
def job_status(job_id: str) -> dict:
    item = runner.status(job_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Job nicht gefunden")
    return item


@router.get("/jobs/{job_id}/result")
def job_result(job_id: str) -> dict:
    result = runner.result(job_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Job-Ergebnis nicht verfügbar")
    return result


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str) -> dict:
    if not runner.cancel(job_id):
        raise HTTPException(status_code=404, detail="Job läuft nicht mehr oder existiert nicht")
    return {"job_id": job_id, "status": "cancelling"}


@router.get("/jobs/{job_id}/report")
def job_report(job_id: str, format: str = Query(default="json", pattern="^(json|csv)$")) -> Response:
    result = runner.result(job_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Job-Ergebnis nicht verfügbar")
    data, filename, media_type = export_report(result, format=format)  # type: ignore[arg-type]
    return Response(
        content=data,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# Backwards-compatible aliases for the original /scans paths.
@router.get("/scans")
def list_scans(limit: int = Query(default=25, ge=1, le=100)) -> dict:
    return {"items": runner.list(limit=limit, kind="scan")}


@router.get("/scans/{scan_id}")
def scan_status(scan_id: str) -> dict:
    return job_status(scan_id)


@router.get("/scans/{scan_id}/result")
def scan_result(scan_id: str) -> dict:
    return job_result(scan_id)


@router.get("/profiles")
def list_profiles() -> dict:
    return {"items": runner.store.list_profiles()}


@router.post("/profiles", status_code=201)
def save_profile(request: ProfileRequest) -> dict:
    runner.store.save_profile(request.name.strip(), request.config)
    return {"name": request.name.strip(), "saved": True}


@router.delete("/profiles/{name}")
def delete_profile(name: str) -> dict:
    deleted = runner.store.delete_profile(name)
    if not deleted:
        raise HTTPException(status_code=404, detail="Profil nicht gefunden")
    return {"name": name, "deleted": True}
