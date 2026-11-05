@echo off
rem v2.11 auto-buy: installs Playwright (once) and opens the buyer Chrome profile so you can sign in to Shop Pay.
cd /d "%~dp0"
chcp 65001 >nul
set PY=python
where py >nul 2>&1 && set PY=py -3
echo Installing Playwright (only slow the first time)...
%PY% -m pip install --quiet --upgrade playwright
if errorlevel 1 (
  echo Could not install Playwright. Check the internet and try again.
  pause
  exit /b 1
)
rem The bot uses your installed Chrome; this adds a spare Chromium in case it can't
%PY% -m playwright install chromium
echo.
%PY% auto_buy.py --setup
echo.
echo Done. Next, in Discord:  /autobuy try link:^<a product page^>
pause
