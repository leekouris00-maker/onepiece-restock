@echo off
rem Double-click to add the Pokemon role, category and channels to the Discord server (safe to run again).
cd /d "%~dp0"
chcp 65001 >nul
set PY=python
where py >nul 2>&1 && set PY=py -3
%PY% add_pokemon_channels.py
echo.
pause
