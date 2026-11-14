@echo off
rem Updates the bot to the newest version on GitHub, then restarts it. Double-click it. Safe to run any time.
rem The work is done by updater.py, which is downloaded fresh each time. Keep this file short.
cd /d "%~dp0"
chcp 65001 >nul
if not exist tcg_bot.py (
  echo This needs to be in the bot folder, next to tcg_bot.py. Move it there and run it again.
  pause
  exit /b 1
)
set PY=python
where py >nul 2>&1 && set PY=py -3
echo Downloading the newest bot files from GitHub...
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { Invoke-WebRequest -UseBasicParsing -Uri 'https://raw.githubusercontent.com/leekouris00-maker/onepiece-restock/master/updater.py' -OutFile 'updater.py.download' -ErrorAction Stop; Move-Item 'updater.py.download' 'updater.py' -Force } catch { Write-Host '  could not download the updater' }"
if not exist updater.py goto failed
%PY% updater.py
if errorlevel 1 goto failed
echo.
echo Restarting the bot...
if exist restart_bot.bat call restart_bot.bat
echo.
echo Done. Your old files are in the backup-before-update folder.
pause
if exist update_bot.bat.new (move /y update_bot.bat.new update_bot.bat >nul & exit /b 0)
exit /b 0
:failed
echo.
echo The update did not finish. Nothing was changed. Check the internet and try again.
pause
exit /b 1
