@echo off
rem The PC's half of auto-buy when the bot runs in its container: watches for restocks the container hands
rem over and does the checkout in your signed-in Chrome profile, on your normal connection. Keep it open.
cd /d "%~dp0"
chcp 65001 >nul
set PY=python
where py >nul 2>&1 && set PY=py -3
set BOT_DATA_DIR=%~dp0docker-data
set BOT_CONTAINER=
:loop
%PY% -u auto_buy_host.py
echo [%date% %time%] stopped (code %errorlevel%), restarting in 30s
ping -n 31 127.0.0.1 >nul
goto loop
