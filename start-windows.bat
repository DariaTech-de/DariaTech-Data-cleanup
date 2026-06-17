@echo off
setlocal
cd /d "%~dp0"

if not exist .venv (
  echo [INFO] Erstelle virtuelle Python-Umgebung...
  py -m venv .venv
)

call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt

echo.
echo [OK] Duplicat-Clearner startet auf http://127.0.0.1:8787
echo.
python -m uvicorn app.main:app --host 127.0.0.1 --port 8787
pause
