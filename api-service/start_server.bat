@echo off
call F:\MyProgram\Anaconda3\Scripts\activate.bat
call conda activate class-assistant
cd /d %~dp0
python -m uvicorn main:app --host 127.0.0.1 --port 8765 --reload
