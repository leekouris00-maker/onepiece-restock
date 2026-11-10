#!/usr/bin/env python3
"""
File and process permission checks for the restock bot (v2.15)
==============================================================
With security on, the bot checks every file it is about to write, delete or rename, and every program it
is about to start, before the operating system is asked:

  * WRITING is only allowed inside the bot's data folder (and the system's temp folder). A write anywhere
    else - Windows, Program Files, your documents, the bot's own code - is refused and logged
    ("blocked_file"). Reading is not restricted (Python needs its own files).
  * STARTING PROGRAMS is refused inside the container ("blocked_process"). On the PC it stays allowed,
    because auto-buy opens Chrome and desk mode opens your browser.

In the Docker container the operating system enforces the same thing independently (read-only system,
non-root user, no extra privileges); this is the second lock, and the one that tells you about it.

Settings (config.json "security" > "files"): "enforce": true, "extra_write_dirs": ["D:/somewhere"].
The check is Python's audit hook. Once switched on it stays installed until the bot restarts; switching
security off makes it allow everything again.
"""
import os
import sys
import tempfile

STATE = {"on": False, "roots": [], "block_processes": False, "blocked": 0}
_installed = [False]
_report = [None]            # set by netguard: fn(kind, detail)
_WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND
_FILE_EVENTS = {"os.remove": 0, "os.rename": None, "os.rmdir": 0, "os.mkdir": 0, "os.chmod": 0, "os.truncate": 0,
                "shutil.rmtree": 0, "os.symlink": 1, "os.link": 1}
_PROC_EVENTS = ("subprocess.Popen", "os.system", "os.exec", "os.spawn", "os.posix_spawn", "os.startfile")


def _norm(p):
    try:
        return os.path.normcase(os.path.realpath(os.fspath(p)))
    except (TypeError, ValueError, OSError):
        return None


def inside(path, roots):
    """True if path is one of roots or under one."""
    p = _norm(path)
    if p is None:
        return True                      # not a path (a file descriptor): nothing to check
    for r in roots:
        if p == r or p.startswith(r.rstrip("\\/") + os.sep):
            return True
    return False


def is_write(mode, flags):
    if isinstance(mode, str) and any(c in mode for c in "wax+"):
        return True
    return isinstance(flags, int) and bool(flags & _WRITE_FLAGS)


def _refuse(kind, detail):
    STATE["blocked"] += 1
    fn = _report[0]
    if fn:
        was, STATE["on"] = STATE["on"], False          # reporting writes the log: don't check ourselves
        try:
            fn(kind, detail)
        except Exception:  # noqa: BLE001
            pass
        finally:
            STATE["on"] = was
    raise PermissionError(f"blocked by the bot's security settings ({kind}): {detail}")


def _hook(event, args):
    if not STATE["on"]:
        return
    if event == "open":
        path, mode, flags = (list(args) + [None, None, None])[:3]
        if isinstance(path, int) or not is_write(mode, flags):
            return
        if not inside(path, STATE["roots"]):
            _refuse("blocked_file", f"write to {path}")
    elif event in _FILE_EVENTS:
        idx = _FILE_EVENTS[event]
        paths = [a for a in args[:2] if isinstance(a, (str, bytes, os.PathLike))] if idx is None else \
            [args[idx]] if len(args) > idx and isinstance(args[idx], (str, bytes, os.PathLike)) else []
        for p in paths:
            if not inside(p, STATE["roots"]):
                _refuse("blocked_file", f"{event} {p}")
    elif STATE["block_processes"] and event.startswith(_PROC_EVENTS):
        _refuse("blocked_process", f"{event} {str(args[0])[:120] if args else ''}")


def enable(data_dir, extra=(), block_processes=False, report=None):
    roots = [_norm(data_dir), _norm(tempfile.gettempdir())] + [_norm(x) for x in extra or []]
    STATE["roots"] = [r for r in roots if r]
    STATE["block_processes"] = bool(block_processes)
    _report[0] = report
    if not _installed[0]:
        sys.addaudithook(_hook)
        _installed[0] = True
    STATE["on"] = True


def disable():
    STATE["on"] = False
