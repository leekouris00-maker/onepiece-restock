@echo off
rem Double-click to add the #ebay-resale and #bot-status channels to the Discord server (run once).
cd /d "%~dp0"
chcp 65001 >nul
set PY=python
where py >nul 2>&1 && set PY=py -3
%PY% add_channels.py
echo.
pause
