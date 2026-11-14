#!/usr/bin/env python3
"""
The bot's updater (v2.21) - run by update_bot.bat, or:  py -3 updater.py
========================================================================
Downloads the newest copy of the bot's own files from its GitHub repo and puts them in this folder.

  * WHICH files comes from update_files.txt in the repo, so a new file in a later version is never
    missed (before v2.21 the list lived inside update_bot.bat, which never updated itself).
  * All or nothing: every file is downloaded and checked first (each .py must be real Python). If
    anything fails, nothing in the folder is changed.
  * Your settings and the bot's memory are never touched: no .json file can be updated, whatever the
    list says.
  * Files that change are copied to backup-before-update first. .bat files are saved with Windows line
    endings.
  * update_bot.bat can't be replaced while it's running, so its new copy is saved as update_bot.bat.new
    and update_bot.bat swaps it in as its very last step.

Exit code 0 = up to date; 1 = something went wrong and nothing was changed.
"""
import os
import re
import shutil
import sys
import urllib.parse
import urllib.request

BASE = "https://raw.githubusercontent.com/leekouris00-maker/onepiece-restock/master/"
HERE = os.path.dirname(os.path.abspath(__file__))
LIST_NAME = "update_files.txt"
BACKUP_DIR = "backup-before-update"
SELF_BAT = "update_bot.bat"
SAFE_NAME = re.compile(r"^[A-Za-z0-9._ -]{1,80}$")
ALLOWED_EXT = (".py", ".bat", ".txt", ".md", ".yml", ".vbs")
ALLOWED_NAMES = ("Dockerfile", ".dockerignore", ".env.example")
# running the whole time, so never replaced by an update (and your own files)
NEVER = ("run_forever.bat", "run_commands.bat", "start_bot_hidden.vbs", "config.json", "secrets.json", ".env")
# used only if update_files.txt can't be downloaded; kept the same as that file (a test checks)
BUILTIN = [
    "updater.py", "tcg_bot.py", "commands_bot.py", "settings_check.py", "rehearsal.py", "value.py", "tcgplayer.py", "deck_price.py",
    "link_watch.py", "ebay_watch.py", "pokemon_watch.py", "fast_lane.py", "misses.py", "onepiece_instore.py",
    "auto_buy.py", "auto_buy_web.py", "auto_buy_host.py", "collection.py", "deal_finder.py", "chain_shops.py",
    "restock_trend.py", "scorecard.py", "netguard.py", "captcha_watch.py", "fileguard.py", "security_log.py",
    "security_panel.py", "add_channels.py", "add_pokemon_channels.py", "Dockerfile", "docker-compose.yml",
    "docker-compose.novpn.yml", "docker-requirements.txt", ".dockerignore", ".env.example", "run_docker.bat",
    "stop_docker.bat", "run_pc_side.bat", "open_security.bat", "setup_autobuy.bat", "open_autobuy.bat",
    "add_channels.bat", "add_pokemon_channels.bat", "restart_bot.bat", "update_bot.bat", "update_files.txt",
    "HOW TO RUN.txt", "SECURITY.md",
]


def allowed(name):
    """Only the bot's own code and help files, in this folder: never a .json, never a path."""
    if not SAFE_NAME.match(name) or name.startswith("-") or ".." in name or name in NEVER:
        return False
    return name in ALLOWED_NAMES or name.lower().endswith(ALLOWED_EXT)


def parse_list(text):
    """update_files.txt -> file names, in order, without repeats. Lines starting with # are notes."""
    out = []
    for raw in str(text).splitlines():
        name = raw.split("#", 1)[0].strip()
        if name and allowed(name) and name not in out:
            out.append(name)
    return out


def fetch(name, timeout=30):
    req = urllib.request.Request(BASE + urllib.parse.quote(name), headers={"User-Agent": "onepiece-restock-updater"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def crlf(raw):
    return raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n").replace(b"\n", b"\r\n")


def prepare(name, raw):
    """The bytes to save for this file. Raises ValueError if it isn't what it should be."""
    if not raw.strip():
        raise ValueError("came back empty")
    if raw.lstrip()[:15].lower().startswith((b"<!doctype html", b"<html")):
        raise ValueError("got a web page instead of the file")
    if name.endswith(".py"):
        try:
            compile(raw.decode("utf-8"), name, "exec")
        except (SyntaxError, UnicodeError, ValueError) as e:
            raise ValueError(f"isn't valid Python ({type(e).__name__})") from None
    if name.lower().endswith(".bat"):
        raw = crlf(raw)
    return raw


def version_of(raw):
    m = re.search(rb'^VERSION = "([^"]+)"', raw or b"", re.M)
    return m.group(1).decode() if m else ""


def _read(path):
    try:
        with open(path, "rb") as f:
            return f.read()
    except OSError:
        return None


def _write(path, raw):
    tmp = path + ".download"
    with open(tmp, "wb") as f:
        f.write(raw)
    os.replace(tmp, path)


def update(here=HERE, fetcher=fetch, say=print, defer_bat=False):
    """Returns (ok, changed file names, new version). defer_bat: update_bot.bat is running us, so its new copy
    is saved as update_bot.bat.new for it to swap in as its last step."""
    try:
        names = parse_list(fetcher(LIST_NAME).decode("utf-8-sig"))
        if "tcg_bot.py" not in names:
            raise ValueError("the list has no tcg_bot.py")
    except Exception as e:  # noqa: BLE001
        say(f"  (couldn't read the file list from GitHub ({type(e).__name__}); using the list built into the updater)")
        names = [n for n in BUILTIN if allowed(n)]
    ready, problems = {}, []
    for name in names:
        try:
            ready[name] = prepare(name, fetcher(name))
        except Exception as e:  # noqa: BLE001
            problems.append(f"{name}: {e if isinstance(e, ValueError) else type(e).__name__}")
    if problems:
        say("  Couldn't get every file, so NOTHING was changed:")
        for p in problems[:12]:
            say(f"    {p}")
        say("  Check the internet connection and run update_bot.bat again.")
        return False, [], ""
    changed = []
    backup = os.path.join(here, BACKUP_DIR)
    for name, raw in ready.items():
        path = os.path.join(here, name)
        old = _read(path)
        if old == raw:
            continue
        try:
            if old is not None:
                os.makedirs(backup, exist_ok=True)
                shutil.copyfile(path, os.path.join(backup, name))
            if name == SELF_BAT and old is not None and defer_bat:
                _write(path + ".new", raw)
            else:
                _write(path, raw)
        except OSError as e:
            say(f"  ! couldn't save {name} ({type(e).__name__}); close anything that has it open and run this again")
            return False, changed, ""
        changed.append(name)
        say(f"  updated {name}")
    new_version = version_of(ready.get("tcg_bot.py"))
    if not changed:
        say(f"  Already up to date (v{new_version})." if new_version else "  Already up to date.")
    else:
        say(f"  {len(changed)} file(s) updated." + (f" The bot is now v{new_version}." if new_version else ""))
    return True, changed, new_version


def check_settings(here=HERE, say=print):
    """After an update: say so now if config.json or secrets.json has a typo, instead of the bot finding out."""
    try:
        sys.path.insert(0, here)
        import settings_check
    except Exception:  # noqa: BLE001
        return []
    bad = []
    for name in ("config.json", "secrets.json"):
        p = settings_check.problem(os.path.join(here, name))
        if p:
            bad.append(p["text"])
            say(f"\n  ! {p['text']}\n    Open {name} in Notepad, fix that line and save. The bot notices by itself.")
    return bad


def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass
    ok, _, version = update(defer_bat=True)
    if not ok:
        return 1
    check_settings()
    if version:
        print(f'\n  After the restart, Discord\'s #bot-status should say "Bot online (PC, v{version})".')
    return 0


if __name__ == "__main__":
    sys.exit(main())
