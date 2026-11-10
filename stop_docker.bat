@echo off
rem Stops the bot's containers (the bot, the Discord commands and the VPN). run_docker.bat starts them again.
cd /d "%~dp0"
docker compose -f docker-compose.yml -f docker-compose.novpn.yml down --remove-orphans 2>nul
if errorlevel 1 docker compose -f docker-compose.novpn.yml down --remove-orphans
pause
