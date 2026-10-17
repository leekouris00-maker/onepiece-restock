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
rem Keep the log from growing forever: past about 5 MB it moves to commands_output.old.log
if exist commands_output.log for %%A in (commands_output.log) do if %%~zA GTR 5000000 move /y commands_output.log commands_output.old.log >nul
echo [%date% %time%] starting commands >> commands_output.log
%PY% -u commands_bot.py >> commands_output.log 2>&1
echo [%date% %time%] commands stopped (code %errorlevel%), restarting in 60s >> commands_output.log
ping -n 61 127.0.0.1 >nul
goto loop
