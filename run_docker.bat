@echo off
rem Starts the restock bot in its isolated container, behind the VPN container. Safe to run any time:
rem it rebuilds the image from the bot files in this folder and restarts the containers.
rem Needs Docker Desktop (docker.com) installed and running.
cd /d "%~dp0"
chcp 65001 >nul
where docker >nul 2>&1
if errorlevel 1 (
  echo Docker isn't installed. Install Docker Desktop from https://www.docker.com/products/docker-desktop/ and run this again.
  pause
  exit /b 1
)
docker info >nul 2>&1
if errorlevel 1 (
  echo Docker Desktop isn't running. Start it, wait for the whale icon to settle, and run this again.
  pause
  exit /b 1
)
if not exist docker-data mkdir docker-data
rem First run: give the container a copy of your settings and the bot's memory, so nothing alerts twice.
if not exist docker-data\config.json (
  echo Copying your settings and the bot's memory into docker-data...
  for %%F in (config.json secrets.json seen.json known_products.json status.json price_history.json singles_prices.json events.jsonl recap.json controls.json watches.json ebay_watch.json market_picks.json tcgplayer_prices.json decks.json chain_state.json autobuy.json autobuy_list.json collection.json) do (
    if exist "%%F" copy /y "%%F" "docker-data\%%F" >nul
  )
)
if not exist .env (
  copy /y .env.example .env >nul
  echo.
  echo A file called .env was created. Open it in Notepad and fill in the two Mullvad lines
  echo ^(WIREGUARD_PRIVATE_KEY and WIREGUARD_ADDRESSES^), save it, then run this again.
  notepad .env
  exit /b 0
)
rem The Linux chosen on the Security page (docker-data\environment.txt): debian or alpine.
set BOT_BASE_IMAGE=python:3.12-slim-bookworm
if exist docker-data\environment.txt (
  findstr /i /x "alpine" docker-data\environment.txt >nul && set BOT_BASE_IMAGE=python:3.12-alpine
)
echo Building and starting (%BOT_BASE_IMAGE%)...
docker compose up -d --build
if errorlevel 1 (
  echo.
  echo Docker couldn't start the containers. The message above says why (often: a typo in .env).
  pause
  exit /b 1
)
echo.
echo Started. The old way of running the bot (run_forever.bat) should now be stopped: run remove_autostart.bat
echo and close its window, so two copies aren't checking at once.
echo.
echo   open_security.bat   the Security page (VPN, IP, CAPTCHA, emergency stop)
echo   run_pc_side.bat     auto-buy on this PC (only if you use auto-buy)
echo   stop_docker.bat     stop the containers
echo   docker compose logs -f bot    watch what the bot is doing
echo.
pause
