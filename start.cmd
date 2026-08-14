@echo off
title Road2Maniacs Discord Webhooks
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\setup.ps1"
  if errorlevel 1 goto :failed
)
".venv\Scripts\python.exe" -u run.py serve
goto :end

:failed
echo Setup failed. Review the messages above.

:end
echo.
pause

