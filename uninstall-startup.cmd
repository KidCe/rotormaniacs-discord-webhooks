@echo off
title Road2Maniacs Discord Webhooks - Remove Startup Shortcut
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\startup-shortcut.ps1" -Uninstall
echo.
pause

