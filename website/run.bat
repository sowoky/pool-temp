@echo off
setlocal
cd /d "%~dp0"

if not exist .venv\Scripts\python.exe (
    echo creating venv...
    python -m venv .venv
    .venv\Scripts\python -m pip install --upgrade pip
    .venv\Scripts\pip install -r requirements.txt
)

set POOL_API_KEY=dev-key
.venv\Scripts\waitress-serve --listen=0.0.0.0:18080 app:app
