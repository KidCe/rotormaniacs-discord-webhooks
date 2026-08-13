@echo off
title SV Aich Discord Bot - Remove Startup Shortcut
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\startup-shortcut.ps1" -Uninstall
echo.
pause

