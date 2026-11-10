# Security and privacy (v2.15)

Everything here is **off by default**. The bot runs exactly as before until you either start it with
`run_docker.bat` or add `"security": {"enabled": true}` to `config.json`. The cloud copy (GitHub) is not
affected: it already runs off your PC and never shows your home address.

## What runs where

| Part | Where | Network |
|---|---|---|
| Restock checker, alerts, Security page | `bot` container | only through the VPN container |
| Discord slash commands | `commands` container | only through the VPN container |
| VPN (Gluetun + Mullvad WireGuard, kill switch) | `vpn` container | the only container with internet |
| Auto-buy, the auto-buy page, your signed-in Chrome profile | Windows (`run_pc_side.bat`) | your normal connection |

Desk mode (opening restocks in your browser) and the 15-second fast lane's desk tabs do not work from the
container. Auto-buy still does, through the hand-over below.

## 1. Isolation (Docker)

`run_docker.bat` builds the image and starts three containers (`docker-compose.yml`).

- **Linux choice:** Debian (`python:3.12-slim-bookworm`, default) or Alpine (`python:3.12-alpine`). Pick it
  on the Security page or set `BOT_BASE_IMAGE` in `.env`; it applies at the next `run_docker.bat`.
- **Can't change the host:** the only folder shared with Windows is `docker-data\`. The container's own
  system is read-only, the code inside it is read-only, it runs as an unprivileged user (uid 10001), has
  no Linux capabilities, and can't gain privileges.
- **Limits:** memory (`BOT_MEMORY`, 768m), CPU (`BOT_CPUS`, 1.5), 256 processes, 64 MB temp space.
- **Files and dependencies:** only `*.py` and `docker-requirements.txt` go into the image. No config,
  secrets or memory files.
- **First run:** your `config.json`, `secrets.json` and the bot's memory files are copied into
  `docker-data\` so nothing alerts twice. After that the container's copy is the live one.
- Stop the old bot (`remove_autostart.bat`, close its window) so two copies aren't checking at once.

## 2. VPN / proxy

- The bot container sits on a private Docker network with no gateway. Its only way out is the VPN
  container's proxy (`http://vpn:8888`). If the VPN drops, Gluetun's kill switch closes and the bot is
  simply cut off. There is no fallback to your home connection, by design and by wiring.
- **Endpoint selection:** `BOT_ENDPOINTS` in `.env` (`name=address`, comma separated) or
  `security.network.endpoints` in `config.json`. Choose the one in use on the Security page.
- **Verification:** every `verify_minutes` (10) and after any change, the bot asks
  `https://am.i.mullvad.net/json` what address it has. A failed check, an address in `never_ips`, or (with
  `require_vpn_flag`) a non-VPN address puts the bot in **disconnected**: it sends nothing until a check
  passes. Put your home IP in `never_ips`.
- **Rotation:** needs two or more endpoints (copy the `vpn` service as `vpn2` with another
  `SERVER_CITIES`). `rotate_minutes` 0 = never; otherwise at least 60. Rotation is a timer only. A shop
  slowing, refusing or challenging the bot never triggers a switch, and those pauses carry over to the
  new address. It is a privacy feature, not a way past a block.
- Endpoint addresses and passwords are never printed, logged or shown on the page (only their names).

## 3. CAPTCHA detection

When a shop answers with a human-verification page (Cloudflare, Turnstile, hCaptcha, reCAPTCHA,
PerimeterX, DataDome, Shopify's challenge), the bot pauses that shop, tells you once in #bot-status and
on the Security page, and waits. Press **Resume** there to let it try again; if it is challenged again
it pauses again. The bot never solves, skips or works around a challenge and never copies cookies from
your browser. `recheck_hours` (0 = wait for you; otherwise at least 6) lets it try once by itself.

## 4. Monitoring

- **Security log:** `security_events.jsonl` in the data folder, also on the Security page. Secrets,
  proxy passwords, webhook links, keys and the second half of public IP addresses are removed first.
- **Allowed sites:** the bot may only talk to its shops, Discord, eBay's API, TCGCSV, ntfy, GitHub and the
  IP-check page, plus `allowlist.extra_hosts`. Enforced three ways: in the bot's own request code, in
  Python's `urllib`, and at the socket level.
- **Automatic shutdown:** `allowlist.max_violations` (5) different unexpected sites within an hour
  triggers an emergency stop.
- **Secrets:** `.env` (container) or `secrets.json` / environment variables (PC). Neither is ever
  committed, copied into the image or logged.
- **File checks:** writes, deletes and renames are only allowed inside the data folder (and temp).
  In the container, starting other programs is refused too.
- **Emergency stop:** the button on the Security page, or automatic. Nothing is sent and auto-buy is
  switched off until you press Resume. It survives a restart.

## 5. The Security page

`open_security.bat` (http://localhost:8766, this PC only, needs the key the .bat passes). Shows and
controls: execution environment, VPN/proxy status, current public IP, IP rotation interval, CAPTCHA
detection and paused shops, monitoring and the latest events, emergency stop.

## 6. Auto-buy hand-over

In the container, auto-buy never opens a browser. Restocks it would take are written to
`docker-data\autobuy_offers.jsonl`. `run_pc_side.bat` (on Windows) reads them, drops anything older than
two minutes or whose links aren't https links to a shop in your config, and passes the rest to auto-buy
as before: your list, limits and budgets still decide. Known limit: the auto-buy list and budget ledger
live in the shared folder so the Discord /autobuy panel can edit them, which means the container can
too. The browser profile with your sign-ins is not shared.

## All settings

```json
"security": {
  "enabled": false,
  "panel_port": 8766,
  "network": {
    "mode": "direct",
    "endpoints": {"melbourne": "http://vpn:8888", "sydney": "env:VPN_SYDNEY"},
    "endpoint": "",
    "rotate_minutes": 0,
    "verify_minutes": 10,
    "ip_check_url": "https://am.i.mullvad.net/json",
    "never_ips": [],
    "require_vpn_flag": false
  },
  "allowlist": {"enforce": true, "extra_hosts": [], "max_violations": 5},
  "captcha": {"enabled": true, "recheck_hours": 0},
  "files": {"enforce": true, "extra_write_dirs": []}
}
```

Environment variables (set by `docker-compose.yml` / `.env`): `BOT_SECURITY`, `BOT_CONTAINER`,
`BOT_DATA_DIR`, `BOT_NET_MODE`, `BOT_ENDPOINTS`, `BOT_ENDPOINT`, `BOT_BASE_IMAGE`, `BOT_MEMORY`,
`BOT_CPUS`, `BOT_EVERY_MINUTES`, `VPN_SERVICE_PROVIDER`, `VPN_CITY`, `WIREGUARD_PRIVATE_KEY`,
`WIREGUARD_ADDRESSES`, plus the Discord names in `.env.example`.

## Files

New: `netguard.py`, `captcha_watch.py`, `fileguard.py`, `security_log.py`, `security_panel.py`,
`auto_buy_host.py`, `Dockerfile`, `docker-compose.yml`, `docker-requirements.txt`, `.dockerignore`,
`.env.example`, `run_docker.bat`, `stop_docker.bat`, `run_pc_side.bat`, `open_security.bat`,
`tests/test_v215_security.py`. Changed: `tcg_bot.py` (three hooks in the request code, data-folder
setting, emergency-stop pause in the loop), `auto_buy.py` (hand-over), `commands_bot.py` (proxy, guard),
and one line each in `auto_buy_web.py`, `collection.py`, `deal_finder.py`, `ebay_watch.py`,
`link_watch.py`, `fast_lane.py` (data folder / container).

## Not tested yet

The container build and the Gluetun wiring were written against Gluetun's documentation but have not
been run: there was no Docker engine where this was built and the PC wasn't reachable. The Python side
(26 tests) is tested. Expect the first `run_docker.bat` to need a look at `docker compose logs`.
