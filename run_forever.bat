@echo off
rem Keeps the One Piece restock bot running. If it crashes, it restarts after 60 seconds.
rem Only one copy can run: a second copy can't grab bot.lock, so it quits straight away.
rem Output goes to bot_output.log in this folder.
cd /d "%~dp0"

set PY=python
where py >nul 2>&1 && set PY=py -3

(call :loop) 9>"bot.lock" || exit /b
exit /b

:loop
rem Keep the log from growing forever: past about 5 MB it moves to bot_output.old.log
if exist bot_output.log for %%A in (bot_output.log) do if %%~zA GTR 5000000 move /y bot_output.log bot_output.old.log >nul
echo [%date% %time%] starting bot >> bot_output.log
%PY% -u tcg_bot.py --loop 5 >> bot_output.log 2>&1
echo [%date% %time%] bot stopped (code %errorlevel%), restarting in 60s >> bot_output.log
ping -n 61 127.0.0.1 >nul
goto loop
