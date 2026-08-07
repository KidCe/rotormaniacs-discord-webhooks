@echo off
title SV 07 Eich Pitch Bot - Remove Startup Shortcut
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\startup-shortcut.ps1" -Uninstall
echo.
pause

