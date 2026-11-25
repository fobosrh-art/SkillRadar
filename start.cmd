@echo off
REM SkillRadar - start the website + API on http://127.0.0.1:8000 (localhost only).
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Virtual environment missing. Run setup.cmd first.
    exit /b 1
)
if not exist "frontend\dist\index.html" (
    echo Frontend not built yet - building...
    pushd frontend
    call npm run build || (popd & exit /b 1)
    popd
)
start "" "http://127.0.0.1:8000"
".venv\Scripts\python.exe" -m skillradar web --host 127.0.0.1 --port 8000
