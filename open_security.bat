@echo off
rem Opens the bot's Security page in your browser (it only works from this PC).
cd /d "%~dp0"
set F=docker-data\security_panel_token.txt
if not exist "%F%" set F=security_panel_token.txt
if not exist "%F%" (
  echo The Security page isn't running yet. Start the bot first ^(run_docker.bat^), wait a minute, and try again.
  pause
  exit /b 1
)
set /p T=<"%F%"
start "" "http://localhost:8766/?t=%T%"
