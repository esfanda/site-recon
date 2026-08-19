@echo off
REM Site Recon - one-time setup. Double-click this file, then use start.cmd.
setlocal
cd /d "%~dp0"

echo.
echo ==========================================
echo   Site Recon - Setup
echo ==========================================
echo.

REM --- Python check -------------------------------------------------------
where python >nul 2>&1
if errorlevel 1 (
    echo [X] Python is not installed.
    echo.
    echo     Install Python 3.11 or newer from:
    echo       https://www.python.org/downloads/
    echo.
    echo     IMPORTANT: on the first screen of the installer,
    echo     tick "Add python.exe to PATH" before clicking Install.
    echo.
    echo     Then run this file again.
    echo.
    pause
    exit /b 1
)

for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo [1/3] Python %PYVER% found.

REM --- Dependencies -------------------------------------------------------
echo [2/3] Installing dependencies. This takes a few minutes the first time...
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements.txt
if errorlevel 1 (
    echo.
    echo [X] Dependency install failed. Check your internet connection and retry.
    pause
    exit /b 1
)

REM --- Browser engine -----------------------------------------------------
echo [3/3] Installing the browser engine used for screenshots...
python -m playwright install chromium
if errorlevel 1 (
    echo.
    echo [X] Browser install failed. Check your internet connection and retry.
    pause
    exit /b 1
)

REM --- Profile ------------------------------------------------------------
if not exist "config\profile.md" (
    copy /y "config\profile.example.md" "config\profile.md" >nul
    echo     Created config\profile.md from the example.
)

echo.
echo ==========================================
echo   Setup complete.
echo.
echo   Next: double-click  start.cmd
echo   The dashboard opens at http://localhost:8080
echo ==========================================
echo.
pause
