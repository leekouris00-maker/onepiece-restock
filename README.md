# One Piece TCG restock bot

Watches Australian shops for English One Piece booster boxes, other sealed products and the singles on
your want list, and posts anything buyable at or under your max price to Discord (plus your phone via
ntfy), each with a one-tap "add to cart → checkout" link. You still press pay yourself: the bot never
logs in or buys anything.

| File | What it is |
|---|---|
| `tcg_bot.py` | The restock bot. Python 3.8+, no installs. |
| `commands_bot.py` | Discord slash commands (`/deals`, `/boxes`, `/want` ...). Needs `pip install discord.py`. |
| `config.json` | What to watch: shops, your want list, max prices. |
| `secrets.json` | Optional, never committed: webhooks and bot token (same keys as `"alerts"`). |
| `run_forever.bat`, `run_commands.bat`, `start_bot_hidden.vbs` | Keep both running on the PC, hidden, restarting on crashes. |
| `.github/workflows/` | `ci.yml` runs the tests; `main.yml` / `recap.yml` are the cloud copy (see note below). |
| `tests/`, `bench/` | Automated tests and the benchmark used to measure v2 against v1. |

## Running it

```
python tcg_bot.py                 check once, show only new finds
python tcg_bot.py --loop 5        keep checking every 5 minutes (faster in drop windows)
python tcg_bot.py --dry-run       check and print, but post nothing and save nothing
python tcg_bot.py --self-test     check config, files and one shop, then stop
python tcg_bot.py --test-discord  post a test message
python tcg_bot.py --recap         post the daily recap
```

## What v2 changed (14 Oct 2026)

Checks are about **5x faster** in the benchmark (13.1 s → 2.7 s for the cloud config, 15.6 s → 2.9 s for the PC
config, same shops and data), download about **6x less**, and open **56% fewer connections**; `/deals` answers
from the last check in under a millisecond of work.
Details and numbers: [`bench/RESULTS.md`](bench/RESULTS.md) and [`CHANGELOG.md`](CHANGELOG.md).

* **Speed:** connections are kept open and reused, replies are gzip-compressed, identical requests within
  a check are shared, boxes and singles are checked at the same time, product pages are fetched in
  parallel (at most 4 at once per shop), and a shop that refuses the bot (401/403) isn't asked again in the
  same check. v1 also slept 4.5 s after every refused request; v2 doesn't retry those at all.
* **No lost alerts:** posts wait out Discord's rate limits and confirm delivery; anything that still
  fails is posted at the next check instead of being marked as seen. More than 10 finds go out over
  several messages (v1 cut them off at 10).
* **Nothing missed in big shops:** collections with more than 250 products are read page by page (pages it had
  last time are asked for together).
* **One cart per shop** for singles, so several cards from the same shop are one order and one shipping fee.
* **Price history:** box alerts show the lowest price seen; `/history` and `/stats` in Discord.
* **Instant commands:** `/deals`, `/boxes` and `/sealed` answer from the last check; `fresh:True` checks live.
* **Admin commands:** `/want add|remove|enable|list`, `/boxmax`, `/mute`, `/unmute` (Manage Server only,
  every change is backed up and written to `audit.log`).
* **Polite and compliant:** follows each shop's robots.txt, and a shop that's been down 3 checks in a row
  is retried every 15 minutes instead of every check.
* **Safer files:** state files are written atomically (a crash can't leave half a file), finds.log rolls over,
  and a typo in one card's settings switches off that card with a warning instead of stopping the bot.

### New optional settings (config.json)

| Setting | Default | What it does |
|---|---|---|
| `"singles_every_minutes": 15` | off (every check) | In `--loop`, check singles less often than boxes. |
| `"auto_drop_windows": true` | on | Drop mode for booster releases in the release list (eve 6pm-midnight, release day 8am-2pm). Your own `drop_windows` win where they overlap. |
| `"alerts": {"quiet_hours": "23:00-07:00"}` | off | No @ping or phone push in those hours, except booster boxes. Finds still post. |
| `"alerts": {"admin_user_ids": ["123..."]}` | Manage Server | Extra people allowed to use the admin commands. |
| `"down_retry_minutes": 15` | 15 | How often to retry a shop that's down (0 = every check, like v1). |
| `"respect_robots": true` | on | Follow each shop's robots.txt. |
| `"history": true` | on | Keep `price_history.json` / `events.jsonl`. |
| `"user_agent": "..."` | Chrome on Windows | The browser name the bot uses. |

## Updating the PC copy from v1 to v2

1. Copy `tcg_bot.py`, `commands_bot.py`, `run_forever.bat` and `run_commands.bat` into
   `D:\TCG\Discord Bot\Discord` (keep a copy of the old ones to roll back). Your `config.json` and state
   files stay as they are.
2. Run `python tcg_bot.py --self-test`, then `python tcg_bot.py --dry-run`.
3. Restart the bot (sign out and in, or end the two `python` processes; the `.bat` files restart them).

Rolling back is the same in reverse: put the old files back. v2 reads and writes the same `seen.json`,
`known_products.json` and `status.json` formats, so either version can pick up where the other left off.

## The cloud copy (GitHub Actions)

In its first 9 hours (13-14 Oct 2026) the 5-minute schedule in `main.yml` fired **once** (6:35 am on 14 Oct),
instead of about 100 times, and the 8:27 am daily recap that morning didn't run at all; every other run was a manual
"Run workflow". GitHub says scheduled runs can be delayed or dropped at busy times, and its
terms ask that GitHub-hosted runners not be used for activity unrelated to building, testing or deploying
the project. A small always-on machine (a spare PC or a Raspberry Pi running `tcg_bot.py --loop 5` with
`HEARTBEAT_ROLE=listen`) is a better home for a backup copy.

## Tests and benchmarks

```
python -m unittest discover -s tests          # 69 tests; the network ones need: pip install cryptography (and discord.py for the commands)
python bench/bench.py suite --v1 bench/baseline/tcg_bot_v1.py --v2 tcg_bot.py
```

The tests and benchmarks only talk to local mock shops built from the bot's own saved data. They never
contact a real shop, Discord or ntfy.
