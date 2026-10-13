@echo off
rem Keeps the Discord slash commands (/deals, /boxes, /card ...) running. Restarts after 60s if they stop.
rem Only one copy can run: a second copy can't grab commands.lock, so it quits straight away.
rem Output goes to commands_output.log in this folder.
cd /d "%~dp0"

set PY=python
where py >nul 2>&1 && set PY=py -3

(call :loop) 9>"commands.lock" || exit /b
exit /b

:loop
echo [%date% %time%] starting commands >> commands_output.log
%PY% -u commands_bot.py >> commands_output.log 2>&1
echo [%date% %time%] commands stopped (code %errorlevel%), restarting in 60s >> commands_output.log
ping -n 61 127.0.0.1 >nul
goto loop
