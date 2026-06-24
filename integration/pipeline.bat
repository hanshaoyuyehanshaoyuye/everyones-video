@echo off
:: pipeline.bat — Windows launcher for pipeline.sh (requires Git Bash)
setlocal
cd /d %~dp0..
if not exist "%~dp0pipeline.sh" (
    echo Error: pipeline.sh not found in integration\
    exit /b 1
)
where bash >nul 2>&1 || (
    echo Error: Git Bash (bash.exe) not in PATH. Install Git for Windows.
    exit /b 1
)
bash "%~dp0pipeline.sh" %*
