from __future__ import annotations

# The full application (including the versioned /api/v1 router) is assembled in app.main.
# This module stays as the stable ASGI entry point used by uvicorn and the EXE launcher.
from app.main import app

__all__ = ["app"]
