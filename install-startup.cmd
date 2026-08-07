@echo off
title SV 07 Eich Pitch Bot - Install Startup Shortcut
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\startup-shortcut.ps1" -Install
echo.
pause

