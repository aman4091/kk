@echo off
REM ============================================================================
REM Local Video Worker - Windows Service Installer
REM ============================================================================
REM This script installs the video worker as a Windows Service
REM Service will auto-start when PC boots
REM ============================================================================

echo.
echo ============================================================
echo   Local Video Worker - Service Installer
echo ============================================================
echo.

REM Check if running as Administrator
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: This script must be run as Administrator!
    echo.
    echo Right-click this file and select "Run as administrator"
    echo.
    pause
    exit /b 1
)

echo [1/5] Checking Python installation...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python not found!
    echo Please install Python 3.10+ and add to PATH
    pause
    exit /b 1
)
python --version
echo.

echo [2/5] Downloading NSSM (Non-Sucking Service Manager)...
if not exist "nssm.exe" (
    curl -L https://nssm.cc/release/nssm-2.24.zip -o nssm.zip
    if %errorlevel% neq 0 (
        echo ERROR: Failed to download NSSM
        echo Please download manually from https://nssm.cc/download
        pause
        exit /b 1
    )

    echo Extracting NSSM...
    powershell -command "Expand-Archive -Path nssm.zip -DestinationPath . -Force"
    copy nssm-2.24\win64\nssm.exe nssm.exe
    del nssm.zip
    rmdir /s /q nssm-2.24
)
echo NSSM ready
echo.

echo [3/5] Installing Windows Service...
set SCRIPT_DIR=%~dp0
set PYTHON_EXE=%SCRIPT_DIR%venv\Scripts\python.exe

REM Check if venv Python exists, otherwise use system Python
if not exist "%PYTHON_EXE%" (
    set PYTHON_EXE=python
)

echo Python executable: %PYTHON_EXE%
echo Script directory: %SCRIPT_DIR%
echo Worker script: %SCRIPT_DIR%local_video_worker.py
echo.

REM Remove existing service if present
nssm stop VideoWorker >nul 2>&1
nssm remove VideoWorker confirm >nul 2>&1

REM Install service
nssm install VideoWorker "%PYTHON_EXE%" "%SCRIPT_DIR%local_video_worker.py"
if %errorlevel% neq 0 (
    echo ERROR: Service installation failed!
    pause
    exit /b 1
)

echo Service installed successfully
echo.

echo [4/5] Configuring service...

REM Set working directory
nssm set VideoWorker AppDirectory "%SCRIPT_DIR%"

REM Set display name and description
nssm set VideoWorker DisplayName "Local Video Worker (RTX 4060)"
nssm set VideoWorker Description "Processes video encoding jobs from cloud queue using RTX 4060 GPU"

REM Set auto-start
nssm set VideoWorker Start SERVICE_AUTO_START

REM Set restart on failure
nssm set VideoWorker AppExit Default Restart
nssm set VideoWorker AppRestartDelay 10000

REM Redirect output to log files
nssm set VideoWorker AppStdout "%SCRIPT_DIR%worker_stdout.log"
nssm set VideoWorker AppStderr "%SCRIPT_DIR%worker_stderr.log"

echo Service configured
echo.

echo [5/5] Starting service...
nssm start VideoWorker
if %errorlevel% neq 0 (
    echo ERROR: Service failed to start!
    echo Check logs in worker_stdout.log and worker_stderr.log
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   Installation Complete!
echo ============================================================
echo.
echo Service Name: VideoWorker
echo Status: Running
echo Startup: Automatic (starts on boot)
echo.
echo Log files:
echo   - worker_stdout.log (console output)
echo   - worker_stderr.log (errors)
echo.
echo Service Management Commands:
echo   - Check status:  nssm status VideoWorker
echo   - Stop service:  nssm stop VideoWorker
echo   - Start service: nssm start VideoWorker
echo   - Restart:       nssm restart VideoWorker
echo   - Remove:        nssm remove VideoWorker confirm
echo.
echo Or use Windows Services Manager (services.msc)
echo.
echo ============================================================
echo.
pause
