@echo off
REM Deploy the capped public demo to home-pi (192.168.1.105).
REM Run this from your PC while you are on the home network.
setlocal
cd /d "%~dp0"

echo.
echo ==========================================
echo   Site Recon - Deploy public demo to Pi
echo ==========================================
echo.

where python >nul 2>&1
if errorlevel 1 (
    echo [X] Python is not installed or not on PATH.
    pause
    exit /b 1
)

if not exist "config\secrets.yaml" (
    echo [X] config\secrets.yaml not found.
    echo     Put your Gemini key there first, or set SITE_RECON_DEMO_KEY manually.
    pause
    exit /b 1
)

echo [1/3] Installing paramiko if needed...
python -m pip install --quiet paramiko
if errorlevel 1 (
    echo [X] pip install paramiko failed.
    pause
    exit /b 1
)

echo [2/3] Reading Gemini key from config\secrets.yaml...
for /f "usebackq tokens=1,* delims=:" %%A in (`findstr /r "gemini_api_key:" config\secrets.yaml`) do set GEMINI_LINE=%%B
set GEMINI_LINE=%GEMINI_LINE: =%
if "%GEMINI_LINE%"=="" (
    echo [X] Could not read gemini_api_key from config\secrets.yaml
    pause
    exit /b 1
)
set SITE_RECON_DEMO_KEY=%GEMINI_LINE%

echo [3/3] Uploading to Pi and running bootstrap (may take 10-20 min first time)...
python scripts\deploy_demo_to_pi.py
set ERR=%ERRORLEVEL%

if %ERR% NEQ 0 (
    echo.
    echo [X] Deploy failed. Check you are on the home Wi-Fi and Pi is on.
    pause
    exit /b %ERR%
)

echo.
echo ==========================================
echo   Deploy finished.
echo   Get the public URL:
echo   ssh erfan@192.168.1.105 "sudo journalctl -u site-recon-demo-tunnel -n 30 --no-pager | grep trycloudflare"
echo ==========================================
echo.
pause
