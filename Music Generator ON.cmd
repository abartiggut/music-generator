@echo off
setlocal
cd /d "%~dp0"
if not exist "%~dp0.venv\Scripts\python.exe" (
  echo Die Windows-Umgebung fehlt. Bitte zuerst Install.cmd ausfuehren.
  exit /b 1
)
"%~dp0.venv\Scripts\python.exe" -m app.launcher start %*
exit /b %errorlevel%
