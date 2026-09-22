@echo off
setlocal
cd /d "%~dp0"
if not defined CLASSFOX_API_TOKEN (
  echo Use ..\dev.bat for the desktop workspace, or set CLASSFOX_API_TOKEN for API-only development.
  exit /b 1
)
uv run --locked --extra audio python main.py
exit /b %errorlevel%
