@echo off
cd /d "%~dp0"
title Local Prompt Studio - install auto-start
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install-auto-start.ps1"
echo.
echo ============================================================
echo  Done. Prompt Studio will now start by itself at sign-in.
echo  Bookmark http://localhost:3000
echo ============================================================
echo.
pause
