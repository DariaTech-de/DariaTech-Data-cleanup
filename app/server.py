from __future__ import annotations

# Backwards-compatible entry point. Prefer app.asgi:app or app.main:app.
from app.main import app

__all__ = ["app"]
