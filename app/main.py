from __future__ import annotations

import mimetypes
import shutil
import sys
from pathlib import Path
from typing import List, Literal
from urllib.parse import unquote

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app import preview_guard
from app.api_v1 import router as api_v1_router
from app.scanner import (
    ScanOptions,
    clean_files,
    consolidate_clean,
    export_report,
    list_quarantine,
    restore_quarantine,
    scan_duplicates,
)


def _base_dir() -> Path:
    """Return project base path in development and PyInstaller bundle path in EXE mode."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent.parent


BASE_DIR = _base_dir()
STATIC_DIR = BASE_DIR / "web"
LAST_SCAN: dict | None = None

app = FastAPI(title="Duplicat-Clearner", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8787", "http://localhost:8787"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/assets", StaticFiles(directory=STATIC_DIR), name="assets")
app.include_router(api_v1_router)


class ScanRequest(BaseModel):
    folder: str | None = None
    folders: List[str] = Field(default_factory=list)
    include_all_files: bool = False
    categories: List[str] = Field(default_factory=list)
    min_size_mb: float = 0
    max_size_mb: float | None = None
    exclude_patterns: List[str] = Field(default_factory=list)
    keep_rule: Literal[
        "oldest", "newest", "largest", "smallest", "shortest_path", "longest_path", "highest_resolution"
    ] = "oldest"
    find_exact: bool = True
    find_similar_images: bool = False
    image_similarity: int = Field(default=8, ge=0, le=20)


class CleanRequest(BaseModel):
    folders: List[str] = Field(default_factory=list)
    folder: str | None = None
    file_paths: List[str] = Field(default_factory=list)
    mode: Literal["quarantine", "recycle_bin", "permanent"] = "quarantine"


class QuarantineRequest(BaseModel):
    folders: List[str] = Field(default_factory=list)
    quarantined_paths: List[str] = Field(default_factory=list)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


def _open_directory_dialog(title: str) -> str:
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        folder = filedialog.askdirectory(title=title, mustexist=True)
        root.destroy()
        return folder or ""
    except Exception as exc:  # pragma: no cover - depends on a desktop session
        raise HTTPException(
            status_code=500,
            detail=(
                "Ordnerauswahl konnte nicht geöffnet werden. Bitte den Pfad manuell eintragen. "
                f"Details: {exc}"
            ),
        ) from exc


@app.get("/api/select-folder")
def select_folder() -> dict:
    """Open a native folder picker and return the selected path (call repeatedly to add several)."""
    return {"folder": _open_directory_dialog("Quellordner für Duplicat-Clearner auswählen")}


@app.get("/api/select-target")
def select_target() -> dict:
    """Open a native folder picker for choosing the clean target folder."""
    return {"folder": _open_directory_dialog("Zielordner für saubere Dateien auswählen")}


@app.get("/api/disk-usage")
def disk_usage(path: str = Query(..., min_length=1)) -> dict:
    candidate = Path(unquote(path)).expanduser()
    probe = candidate
    while not probe.exists() and probe.parent != probe:
        probe = probe.parent
    try:
        usage = shutil.disk_usage(str(probe))
    except OSError as exc:
        raise HTTPException(status_code=400, detail=f"Speicherplatz konnte nicht ermittelt werden: {exc}") from exc
    return {"path": str(candidate), "total": usage.total, "used": usage.used, "free": usage.free}


def _request_to_options(request: ScanRequest) -> ScanOptions:
    folders = request.folders[:]
    if request.folder:
        folders.insert(0, request.folder)
    return ScanOptions(
        folders=folders,
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


@app.post("/api/scan")
def scan(request: ScanRequest) -> dict:
    global LAST_SCAN
    try:
        result = scan_duplicates(_request_to_options(request))
        LAST_SCAN = result
        preview_guard.register_result(result)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Scan fehlgeschlagen: {exc}") from exc


@app.post("/api/clean")
def clean(request: CleanRequest) -> dict:
    folders = request.folders[:]
    if request.folder:
        folders.insert(0, request.folder)
    if not request.file_paths:
        raise HTTPException(status_code=400, detail="Keine Dateien ausgewählt.")
    if request.mode == "permanent":
        raise HTTPException(
            status_code=400,
            detail="Endgültiges Löschen ist in dieser Version bewusst gesperrt. Nutze Quarantäne oder Papierkorb.",
        )
    try:
        return clean_files(folders, request.file_paths, mode=request.mode)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Bereinigung fehlgeschlagen: {exc}") from exc


@app.post("/api/quarantine")
def quarantine(request: CleanRequest) -> dict:
    request.mode = "quarantine"
    return clean(request)


@app.post("/api/quarantine/list")
def quarantine_list(request: QuarantineRequest) -> dict:
    if not request.folders:
        raise HTTPException(status_code=400, detail="Bitte mindestens einen Ordner angeben.")
    try:
        return list_quarantine(request.folders)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/quarantine/restore")
def quarantine_restore(request: QuarantineRequest) -> dict:
    if not request.folders:
        raise HTTPException(status_code=400, detail="Bitte mindestens einen Ordner angeben.")
    try:
        return restore_quarantine(request.folders, request.quarantined_paths or None)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/consolidate")
def consolidate(request: dict) -> dict:
    """Synchronous consolidation helper. The UI normally uses /api/v1/consolidations for live progress."""
    from app.api_v1 import ConsolidateRequestV1, _to_consolidate_options

    model = ConsolidateRequestV1(**request)
    try:
        return consolidate_clean(_to_consolidate_options(model))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Zusammenführung fehlgeschlagen: {exc}") from exc


@app.get("/api/preview")
def preview(path: str = Query(..., min_length=1)) -> FileResponse:
    decoded = unquote(path)
    resolved = str(Path(decoded).expanduser().resolve())
    if not preview_guard.is_allowed(resolved):
        raise HTTPException(status_code=403, detail="Vorschau ist nur für Dateien aus einem Scan erlaubt.")
    file_path = Path(resolved)
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Datei nicht gefunden.")
    media_type, _ = mimetypes.guess_type(str(file_path))
    return FileResponse(file_path, media_type=media_type or "application/octet-stream")


@app.get("/api/report")
def report(format: Literal["json", "csv"] = "json") -> Response:
    if LAST_SCAN is None:
        raise HTTPException(status_code=400, detail="Es gibt noch keinen Scan-Bericht.")
    data, filename, media_type = export_report(LAST_SCAN, format=format)
    return Response(
        content=data,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
