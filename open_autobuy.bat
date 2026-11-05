@echo off
rem v2.11.2: opens the auto-buy page (mode, limits, list, screenshots) in your browser.
cd /d "%~dp0"
chcp 65001 >nul
set PY=python
where py >nul 2>&1 && set PY=py -3
%PY% auto_buy_web.py
if errorlevel 1 pause
