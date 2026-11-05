@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Create environment: py -m venv .venv
  echo Install dependencies: .venv\Scripts\python.exe -m pip install -r requirements.txt
  pause
  exit /b 1
)
".venv\Scripts\python.exe" run.py
pause
