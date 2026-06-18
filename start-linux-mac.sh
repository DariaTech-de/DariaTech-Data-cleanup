#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  echo "[INFO] Erstelle virtuelle Python-Umgebung..."
  python3 -m venv .venv
fi

source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt

echo
echo "[OK] Duplicat-Clearner startet auf http://127.0.0.1:8787"
echo
python -m uvicorn app.asgi:app --host 127.0.0.1 --port 8787
