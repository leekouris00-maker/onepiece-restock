@echo off
rem Stops the restock bot starting by itself at login. It keeps running until you log off or restart.
del "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\OnePieceRestockBot.vbs" 2>nul
echo Autostart is off. The bot keeps running until you log off or restart.
echo install_autostart.bat turns it back on.
pause
