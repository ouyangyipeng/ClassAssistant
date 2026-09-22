@echo off
setlocal
cd /d "%~dp0"
uv run --no-project --python 3.12 scripts/dev.py %*
exit /b %errorlevel%
