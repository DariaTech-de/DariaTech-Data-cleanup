from __future__ import annotations

from pathlib import Path
from typing import List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.scanner import scan_duplicates, quarantine_files

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "web"

app = FastAPI(title="Duplicat-Clearner", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8787", "http://localhost:8787"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/assets", StaticFiles(directory=STATIC_DIR), name="assets")


class ScanRequest(BaseModel):
    folder: str = Field(..., min_length=1)
    include_all_files: bool = False


class QuarantineRequest(BaseModel):
    folder: str = Field(..., min_length=1)
    file_paths: List[str] = Field(default_factory=list)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/api/scan")
def scan(request: ScanRequest) -> dict:
    try:
        return scan_duplicates(request.folder, include_all_files=request.include_all_files)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # defensive: user-facing tool should not crash with tracebacks
        raise HTTPException(status_code=500, detail=f"Scan fehlgeschlagen: {exc}") from exc


@app.post("/api/quarantine")
def quarantine(request: QuarantineRequest) -> dict:
    if not request.file_paths:
        raise HTTPException(status_code=400, detail="Keine Dateien ausgewählt.")
    try:
        return quarantine_files(request.folder, request.file_paths)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Verschieben fehlgeschlagen: {exc}") from exc
