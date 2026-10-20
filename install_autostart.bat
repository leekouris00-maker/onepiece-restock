@echo off
rem Makes the restock bot AND its Discord commands start by themselves (hidden, no windows) every time
rem you log in to Windows, and starts them right now with the newest files.
rem Safe to run again: it never starts a second copy. Undo with remove_autostart.bat.
cd /d "%~dp0"
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
if not exist "%STARTUP%\" (
  echo Couldn't find your Startup folder: %STARTUP%
  pause
  exit /b 1
)
> "%STARTUP%\OnePieceRestockBot.vbs" (
  echo ' Starts the restock bot and its Discord commands at login, hidden. Made by install_autostart.bat.
  echo ' Delete this file ^(or run remove_autostart.bat^) to stop that.
  echo CreateObject^("WScript.Shell"^).Run "wscript.exe ""%~dp0start_bot_hidden.vbs""", 0, False
)
echo Autostart is on: the bot and its Discord commands will start by themselves at every login.
echo.
call "%~dp0restart_bot.bat"
echo.
echo All done. Discord's #bot-status should show "Bot online (PC, v2.2.0)" within a minute or two.
pause
