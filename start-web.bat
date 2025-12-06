@echo off
echo ========================================
echo   AutoDescribe Images - Web Interface
echo ========================================
echo.

cd /d "%~dp0"

echo [1/4] Checking if UV is installed...
where uv >nul 2>nul && goto :uv_found

echo UV not found. Installing UV...
powershell -ExecutionPolicy ByPass -NoProfile -Command "irm https://astral.sh/uv/install.ps1 | iex"

REM Add UV to PATH for current session
set "Path=%USERPROFILE%\.local\bin;%Path%"

REM Verify UV is now available
where uv >nul 2>nul && goto :uv_installed
echo ERROR: UV installation failed or not found in PATH.
echo Please restart your terminal and run this script again.
pause
exit /b 1

:uv_installed
echo UV installed successfully!
goto :uv_continue

:uv_found
echo UV is already installed.

:uv_continue

echo.
echo [2/4] Updating repository...
git pull

echo.
echo [3/4] Checking dependencies...
uv sync

echo.
echo [4/4] Launching web interface...
echo.
uv run python -m image_describer --web

pause
