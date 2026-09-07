@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Python virtual environment was not found.
  echo Run: python -m venv .venv
  pause
  exit /b 1
)

powershell -NoProfile -Command "try { $response = Invoke-WebRequest -Uri 'http://127.0.0.1:54810/api/health' -UseBasicParsing -TimeoutSec 2; if ($response.StatusCode -eq 200) { exit 0 } } catch { exit 1 }"
if errorlevel 1 (
  start "Video to Article Server" cmd /k ".venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 54810"
  timeout /t 2 /nobreak >nul
)

start "" "http://127.0.0.1:54810/"
endlocal
