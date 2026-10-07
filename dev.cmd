@echo off
if not exist "%~dp0.venv\Scripts\python.exe" (
  echo Missing .venv. Follow the backend installation instructions in README.md.
  exit /b 1
)
"%~dp0.venv\Scripts\python.exe" "%~dp0scripts\dev.py" %*
