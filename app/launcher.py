from __future__ import annotations

import socket
import sys
import threading
import time
import traceback
import webbrowser

HOST = "127.0.0.1"
PORT = 8787
URL = f"http://{HOST}:{PORT}"


def _port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.4)
        return sock.connect_ex((host, port)) == 0


def _open_browser_when_ready() -> None:
    """Open the default browser once the local server accepts connections."""
    for _ in range(80):
        if _port_open(HOST, PORT):
            try:
                webbrowser.open(URL)
            except Exception:
                pass
            return
        time.sleep(0.4)


def main() -> None:
    print("=" * 52)
    print("  DariaTech Data Cleanup")
    print(f"  Lokaler Start auf {URL}")
    print("  Dieses Fenster bitte geöffnet lassen.")
    print("=" * 52)

    if _port_open(HOST, PORT):
        print(f"\nEs läuft bereits eine Instanz auf {URL}.")
        webbrowser.open(URL)
        input("\nEnter zum Schließen …")
        return

    # Import here so any import error is caught by the guarded runner and shown.
    import uvicorn

    from app.asgi import app

    threading.Thread(target=_open_browser_when_ready, daemon=True).start()
    # Force the dependency-free asyncio loop and h11 HTTP so the frozen EXE does
    # not rely on optional native extensions (uvloop/httptools/websockets).
    uvicorn.run(app, host=HOST, port=PORT, log_level="info", loop="asyncio", http="h11")


def _run_guarded() -> None:
    try:
        main()
    except SystemExit:
        raise
    except BaseException:
        print("\n=== Fehler beim Start von DariaTech Data Cleanup ===")
        traceback.print_exc()
        print(
            "\nBitte diesen Text an den Support senden. "
            "Häufige Ursachen: Port 8787 belegt oder fehlende Schreibrechte."
        )
        try:
            input("\nEnter zum Schließen …")
        except EOFError:
            pass
        sys.exit(1)


if __name__ == "__main__":
    _run_guarded()
