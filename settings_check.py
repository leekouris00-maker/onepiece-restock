#!/usr/bin/env python3
"""
Plain-English messages for a settings file that won't load (v2.21)
==================================================================
config.json and secrets.json are edited by hand, and one missing comma stops the whole file from loading.
Before v2.21 a broken secrets.json was ignored without a word, so webhooks and the bot token kept there
simply stopped working; and the channel scripts showed a Python traceback.

  problem(path)        None if the file is fine or isn't there, else a dict: file, line, column, what,
                       hint, shown (the line, with its value hidden), text (all of it in one message).
  explain(path, err)   the same from an error you already caught.

Nothing here ever shows a value from secrets.json, and values in config.json that look like a webhook,
token, topic, key or password are hidden too. No dependencies, so the small set-up scripts can use it.
"""
import json
import os
import re

SENSITIVE_KEY = re.compile(r"webhook|token|topic|secret|password|passwd|key|auth|cookie|proxy|endpoint", re.I)
_HOOK = re.compile(r"(discord(?:app)?\.com/api/webhooks/)\S+", re.I)
_TOKEN = re.compile(r"\b[MN][\w-]{23,25}\.[\w-]{6}\.[\w-]{27,40}\b")
_KEY = re.compile(r'^\s*"([^"\\]{1,60})"\s*:')


def _mask(line, hide_all):
    """The line as it's safe to show: the setting's name, and its value only when it can't be a secret."""
    line = line.rstrip("\r\n")
    m = _KEY.match(line)
    if m:
        if hide_all or SENSITIVE_KEY.search(m.group(1)):
            tail = "," if line.rstrip().endswith(",") else ""
            return f'"{m.group(1)}": "***"{tail}'
    elif hide_all:
        return ""                         # can't tell the name from the value: show nothing from a secrets file
    line = _TOKEN.sub("***", _HOOK.sub(r"\1***", line.strip()))
    return line if len(line) <= 120 else line[:117] + "..."


def _hint(msg, lines, line, col):
    """What probably went wrong, in words. line/col are 1-based, as Python reports them."""
    here = lines[line - 1] if 0 < line <= len(lines) else ""
    before = here[:max(0, col - 1)]
    prev = line - 1
    while prev > 0 and not lines[prev - 1].strip():
        prev -= 1
    prev_text = lines[prev - 1].rstrip() if prev > 0 else ""
    if "Expecting ',' delimiter" in msg:
        if not before.strip() and prev:
            return f"Line {prev} is probably missing a comma at its end."
        return f"There's probably a comma or a quote mark missing on line {line}."
    if "Illegal trailing comma" in msg:                   # Python 3.13+ points at the comma itself
        return f"Line {line} ends with a comma but it's the last entry: remove that comma."
    if "Expecting property name" in msg:
        if prev and prev_text.endswith(",") and here.strip()[:1] in ("}", "]"):
            return f"Line {prev} ends with a comma but it's the last entry: remove that comma."
        return f"Each setting's name needs double quotes, like \"name\": ... (line {line})."
    if "Expecting ':' delimiter" in msg:
        return f"Line {line} needs a colon between the setting's name and its value."
    if "Unterminated string" in msg or "Invalid control character" in msg:
        return f"A quote mark (\") is missing on line {line}."
    if "Expecting value" in msg:
        if not "".join(lines).strip():
            return "The file is empty."
        return (f"Line {line} is missing its value, or uses something JSON doesn't allow "
                f"(single quotes, True/False with a capital, a comma with nothing after it).")
    if "Extra data" in msg:
        return f"There's something after the end of the settings (line {line}), often an extra }} or a second {{."
    if "Invalid \\escape" in msg or "Invalid \\\\escape" in msg:
        return f"A backslash on line {line} needs doubling: write \\\\ instead of \\ (or use / in folder paths)."
    return ""


def explain(path, err):
    """A caught error from reading `path` -> {"file", "line", "column", "what", "hint", "shown", "text"}."""
    name = os.path.basename(str(path))
    hide_all = name.lower().startswith("secrets")
    if not isinstance(err, json.JSONDecodeError):
        what = f"couldn't be opened ({type(err).__name__})" if isinstance(err, OSError) else "isn't saved as plain text"
        return {"file": name, "line": None, "column": None, "what": what, "hint": "", "shown": "",
                "text": f"{name} {what}."}
    lines = (err.doc or "").splitlines()
    line, col = int(err.lineno or 1), int(err.colno or 1)
    hint = _hint(err.msg, lines, line, col)
    show_no = line
    if hint.startswith("Line ") and "comma" in hint:          # the line to fix is the one before
        show_no = int(re.match(r"Line (\d+)", hint).group(1))
    shown = _mask(lines[show_no - 1], hide_all) if 0 < show_no <= len(lines) else ""
    text = f"{name} has a typo on line {line}."
    if hint:
        text += " " + hint
    if shown:
        text += f" Line {show_no} reads: {shown}"
    return {"file": name, "line": line, "column": col, "what": err.msg, "hint": hint, "shown": shown, "text": text}


def problem(path):
    """None if the settings file loads (or doesn't exist), else what's wrong with it (see explain)."""
    try:
        with open(path, encoding="utf-8-sig") as f:
            raw = f.read()
    except FileNotFoundError:
        return None
    except (OSError, UnicodeError) as e:
        return explain(path, e)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        return explain(path, e)
    if not isinstance(data, dict):
        name = os.path.basename(str(path))
        return {"file": name, "line": 1, "column": 1, "what": "not an object", "hint": "", "shown": "",
                "text": f"{name} should start with {{ and end with }}."}
    return None


if __name__ == "__main__":
    import sys
    here = os.path.dirname(os.path.abspath(__file__))
    bad = [p for p in (problem(os.path.join(here, n)) for n in sys.argv[1:] or ("config.json", "secrets.json")) if p]
    for p in bad:
        print(p["text"])
    if not bad:
        print("Settings files load fine.")
    sys.exit(1 if bad else 0)
