@echo off
REM Full Kraitos Sports setup: Python tests + mobile APK build
setlocal
cd /d "%~dp0.."
set NODE_DIR=%CD%\.tools\node
set PATH=%NODE_DIR%;%PATH%

echo === Kraitos Sports Setup ===

if exist "%NODE_DIR%\node.exe" (
    "%NODE_DIR%\npm.cmd" config set strict-ssl false
) else (
    echo Run scripts\setup_and_build_sports.ps1 first to install Node
    exit /b 1
)

echo.
echo [1/3] Python tests...
where python >nul 2>&1
if %ERRORLEVEL%==0 (
    python -m pip install fastapi uvicorn numpy pandas pytest -q 2>nul
    python -m pytest tests\test_sports_brain.py -v --tb=short
    if errorlevel 1 echo WARNING: Some tests failed
) else (
    echo Python not found - skipping tests. Install Python 3.11+ to run tests.
)

echo.
echo [2/3] Export demo data...
where python >nul 2>&1
if %ERRORLEVEL%==0 (
    python scripts\export_sports_demo.py
)

echo.
echo [3/3] Mobile APK build...
powershell -ExecutionPolicy Bypass -File "%~dp0setup_and_build_sports.ps1"
exit /b %ERRORLEVEL%
