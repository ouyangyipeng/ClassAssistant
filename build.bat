@echo off
setlocal
cd /d "%~dp0"
uv run --no-project --python 3.12 scripts/build.py %*
exit /b %errorlevel%
