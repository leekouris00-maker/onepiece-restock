@echo off
rem Restarts the restock bot AND its Discord commands so both load the newest files.
rem It stops them; run_forever.bat and run_commands.bat (still running in the background) start them again within about a minute.
rem If neither is running at all, this starts them.
cd /d "%~dp0"
powershell -NoProfile -Command "$p = Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^(py|pyw|python|pythonw)\.exe$' -and ($_.CommandLine -like '*tcg_bot.py*' -or $_.CommandLine -like '*commands_bot.py*') }; if ($p) { $p | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }; Write-Host 'Bot and Discord commands stopped. They start again by themselves within about a minute.' } else { Start-Process wscript.exe -ArgumentList '\"%~dp0start_bot_hidden.vbs\"'; Write-Host 'The bot was not running, so it has been started.' }"
echo.
echo Watch Discord for "Bot online (PC, v2.3.0)".
timeout /t 8 >nul
