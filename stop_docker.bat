@echo off
rem Stops the bot's containers (the bot, the Discord commands and the VPN). run_docker.bat starts them again.
cd /d "%~dp0"
docker compose down
pause
