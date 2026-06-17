from __future__ import annotations

import sys
import threading
import time
import traceback
import webbrowser
from pathlib import Path

import uvicorn

from app.main import app

APP_URL = "http://127.0.0.1:8787"


def _log_path() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).with_name("Duplicat-Clearner-error.log")
    return Path(__file__).resolve().parent.parent / "Duplicat-Clearner-error.log"


def _write_error_log(exc: BaseException) -> None:
    log_file = _log_path()
    log_file.write_text(
        "Duplicat-Clearner konnte nicht gestartet werden.\n\n"
        f"Fehler: {exc}\n\n"
        f"Details:\n{traceback.format_exc()}\n",
        encoding="utf-8",
    )


def _open_browser() -> None:
    time.sleep(1.5)
    webbrowser.open(APP_URL)


def main() -> None:
    print("Duplicat-Clearner startet ...")
    print(f"Wenn der Browser nicht automatisch aufgeht, bitte öffnen: {APP_URL}")
    try:
        threading.Thread(target=_open_browser, daemon=True).start()
        uvicorn.run(app, host="127.0.0.1", port=8787, log_level="info")
    except BaseException as exc:
        _write_error_log(exc)
        print("\nFEHLER: Duplicat-Clearner konnte nicht gestartet werden.")
        print(f"Details stehen hier: {_log_path()}")
        print("\nDieses Fenster bleibt offen, damit der Fehler sichtbar ist.")
        input("Drücke Enter zum Schließen ...")
        raise


if __name__ == "__main__":
    main()
