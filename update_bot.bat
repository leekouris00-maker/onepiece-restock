@echo off
rem Updates the bot to the newest version on GitHub, then restarts it.
rem Put this file in the bot folder (next to tcg_bot.py) and double-click it. Safe to run any time.
cd /d "%~dp0"
chcp 65001 >nul
if not exist tcg_bot.py (
  echo This needs to be in the bot folder, next to tcg_bot.py. Move it there and run it again.
  pause
  exit /b 1
)
echo Downloading the newest bot files from GitHub...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop';" ^
  "$base='https://raw.githubusercontent.com/leekouris00-maker/onepiece-restock/master/';" ^
  "$files='tcg_bot.py','commands_bot.py','value.py','tcgplayer.py','deck_price.py','link_watch.py','ebay_watch.py','pokemon_watch.py','fast_lane.py','misses.py','onepiece_instore.py','add_channels.py','add_channels.bat','add_pokemon_channels.py','HOW TO RUN.txt';" ^
  "New-Item -ItemType Directory -Force -Path 'backup-before-update' | Out-Null;" ^
  "foreach($f in $files){" ^
  "  $tmp=$f+'.download';" ^
  "  try { Invoke-WebRequest -UseBasicParsing -Uri ($base+[uri]::EscapeDataString($f)) -OutFile $tmp }" ^
  "  catch { Write-Host ('  could not download '+$f+' - kept the old one'); continue }" ^
  "  if(Test-Path $f){ Copy-Item $f ('backup-before-update\'+$f) -Force }" ^
  "  Move-Item $tmp $f -Force; Write-Host ('  updated '+$f) }"
if errorlevel 1 (
  echo.
  echo Something went wrong downloading. Nothing was changed. Check the internet and try again.
  pause
  exit /b 1
)
echo.
echo Restarting the bot...
if exist restart_bot.bat call restart_bot.bat
echo.
echo Done. Your old files are in the backup-before-update folder.
echo Within a minute or two Discord's #bot-status should say "Bot online (PC, v2.10.1)".
echo.
choice /m "Add the #onepiece-in-store (and #tcgplayer-prices) channels to Discord now"
if errorlevel 2 goto end
call add_channels.bat
exit /b 0
:end
echo.
pause
