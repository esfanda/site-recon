@echo off
REM Site Recon - start the dashboard and open it in the browser.
setlocal
cd /d "%~dp0"

where python >nul 2>&1
if errorlevel 1 (
    echo Python not found. Run install.cmd first.
    pause
    exit /b 1
)

if not exist "config\profile.md" (
    echo Setup has not been run yet. Run install.cmd first.
    pause
    exit /b 1
)

echo Starting Site Recon at http://localhost:8080
echo Close this window to stop the server.
echo.

REM Give the server a moment, then open the browser.
start "" /b cmd /c "timeout /t 3 >nul & start http://localhost:8080"

python dashboard\api.py 8080
