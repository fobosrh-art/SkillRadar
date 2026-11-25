@echo off
REM SkillRadar - SYNTHETIC DEMO (no Softon API key, no ESCO download, no real data needed).
REM Uses a separate data folder (data-demo) so it never mixes with real analytics.
REM Usage: start-demo.cmd [port]      (default port 8000)
setlocal
cd /d "%~dp0"
set "PORT=8000"
if not "%~1"=="" set "PORT=%~1"
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
set "SKILLRADAR_DEMO=1"
set "SKILLRADAR_DATA_DIR=%~dp0data-demo"
set "SKILLRADAR_DB_PATH="
".venv\Scripts\python.exe" -m skillradar generate-demo-data || exit /b 1
".venv\Scripts\python.exe" -m skillradar init-db || exit /b 1
".venv\Scripts\python.exe" -m skillradar run
start "" "http://127.0.0.1:%PORT%"
".venv\Scripts\python.exe" -m skillradar web --host 127.0.0.1 --port %PORT%
