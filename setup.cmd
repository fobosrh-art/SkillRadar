@echo off
REM SkillRadar - reproducible setup on Windows (no Docker / WSL).
REM Requires: Python 3.13 and Node.js 22 on PATH. Safe to re-run.
setlocal
cd /d "%~dp0"

echo [1/5] Python virtual environment
if not exist ".venv\Scripts\python.exe" (
    python -m venv .venv || goto :error
)
".venv\Scripts\python.exe" -m pip install --upgrade pip >nul || goto :error
".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto :error

echo [2/5] Environment file
if not exist ".env" (
    copy ".env.example" ".env" >nul
    echo     Created .env - add SOFTON_API_KEY=... only if you want live fetches.
)

echo [3/5] Frontend dependencies
pushd frontend
call npm ci --no-audit --no-fund || call npm install --no-audit --no-fund || goto :error_pop

echo [4/5] Frontend type check + production build
call npm run build || goto :error_pop
popd

echo [5/5] Database schema and first local pipeline run (no network)
".venv\Scripts\python.exe" -m skillradar init-db || goto :error
if exist "data\raw\esco\skills_en.csv" (
    ".venv\Scripts\python.exe" -m skillradar run
    echo.
    echo Setup complete. Start the website with:  start.cmd
) else (
    echo.
    echo Setup complete. No private data found in data\raw ^(ESCO CSVs / Softon export^).
    echo Run the SYNTHETIC demo with:  start-demo.cmd
    echo For real analytics see docs\data_sources.md.
)
exit /b 0

:error_pop
popd
:error
echo.
echo Setup FAILED - see the messages above.
exit /b 1
