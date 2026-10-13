#!/usr/bin/env python3
"""
Restock bot benchmark: runs two versions of tcg_bot.py, unmodified, against the same mock shops.

    python bench/bench.py compare --v1 OLD/tcg_bot.py --v2 tcg_bot.py --runs 30 --out results.json
    python bench/bench.py calibrate --bot OLD/tcg_bot.py --runs 5

Each timed run is a fresh `python tcg_bot.py` process (exactly how the cloud copy runs, and close to
one loop of the PC copy), so interpreter start-up is included. Runs alternate v1, v2, v1, v2... so
any drift on the machine hits both equally. Needs Linux/macOS and the `cryptography` package
(only to mint a throwaway TLS certificate for the mock shops).
"""
import argparse
import json
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import certs  # noqa: E402
import fixtures  # noqa: E402
from mockserver import MockInternet, Profile  # noqa: E402

CACHE = os.environ.get("BENCH_CACHE") or os.path.join(tempfile.gettempdir(), "restock-bench")
WEBHOOKS = {"DISCORD_WEBHOOK_BOXES": "https://discord.com/api/webhooks/1001/boxes-token",
            "DISCORD_WEBHOOK_SINGLES": "https://discord.com/api/webhooks/1002/singles-token",
            "DISCORD_WEBHOOK_SEALED": "https://discord.com/api/webhooks/1003/sealed-token",
            "DISCORD_PING": "<@&123456789012345678>"}


# ----------------------------------------------------------------------------- workloads
def cloud_config():
    """The repo's own config.json - what the cloud copy runs (4 cards on the want list)."""
    return json.load(open(os.path.join(REPO, "config.json"), encoding="utf-8"))


def pc_config():
    """The PC config's active part: the cloud list plus Sabo PRB02-014 searched by name."""
    cfg = cloud_config()
    cfg["singles"]["cards"].insert(1, {"name": "Sabo", "num": "PRB02-014", "qty": 4, "max": 5, "deck": "Sabo",
                                       "priority": True, "enabled": True, "search": "sabo premium booster"})
    return cfg


def pc_noskip_config():
    """PC workload with v2's 'retry a down shop every 15 minutes' switched off, so v2 also asks the
    refusing shops every check (v1 ignores the setting). Separates that feature from the rest."""
    cfg = pc_config()
    cfg["down_retry_minutes"] = 0
    return cfg


WORKLOADS = {"cloud": cloud_config, "pc": pc_config, "pc_noskip": pc_noskip_config}


# ----------------------------------------------------------------------------- harness
class Harness:
    def __init__(self, scenario="baseline", profile=None):
        self.hosts = fixtures.all_hosts()
        ca, cert, key = certs.make(os.path.join(CACHE, "tls"), self.hosts)
        self.ca = ca
        self.inet = MockInternet(fixtures.build(scenario), profile or Profile(), cert, key).start()

    def env(self, extra=None):
        env = dict(os.environ)
        env.update({"PYTHONPATH": os.path.join(HERE, "inject"), "BENCH_HOSTS": ",".join(self.hosts),
                    "BENCH_PORT": str(self.inet.port), "SSL_CERT_FILE": self.ca, "no_proxy": "*", "NO_PROXY": "*",
                    "TZ": "Australia/Melbourne", "PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8"})
        for k in ("DISCORD_WEBHOOK", "NTFY_TOPIC", "HEARTBEAT_TOPIC", "HEARTBEAT_ROLE", "DISCORD_BOT_TOKEN"):
            env.pop(k, None)
        env.update(extra or {})
        return env

    def stop(self):
        self.inet.stop()


def make_dir(bot_path, cfg, label):
    d = tempfile.mkdtemp(prefix=f"bench-{label}-", dir=CACHE)
    shutil.copy(bot_path, os.path.join(d, "tcg_bot.py"))
    with open(os.path.join(d, "config.json"), "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=1)
    return d


def run(h, d, args=(), extra_env=None, timeout=300):
    """One bot process. Returns wall/cpu/memory plus what the mock servers saw."""
    h.inet.stats.reset()
    out = open(os.path.join(d, "bench_stdout.log"), "ab")
    t0 = time.perf_counter()
    p = subprocess.Popen([sys.executable, "-u", "tcg_bot.py", *args], cwd=d, env=h.env(extra_env),
                         stdout=out, stderr=subprocess.STDOUT)
    _, status, ru = os.wait4(p.pid, 0)
    wall = time.perf_counter() - t0
    p.returncode = os.waitstatus_to_exitcode(status)
    out.close()
    s = h.inet.stats.snapshot()
    return {"wall": wall, "cpu": ru.ru_utime + ru.ru_stime, "maxrss_mb": ru.ru_maxrss / 1024, "exit": p.returncode,
            "requests": s["requests"], "connections": s["connections"], "bytes": s["bytes_out"],
            "statuses": s["statuses"], "discord_posts": s["discord_posts"]}


def pct(xs, p):
    xs = sorted(xs)
    if not xs:
        return float("nan")
    k = (len(xs) - 1) * p / 100
    f, c = int(k), min(int(k) + 1, len(xs) - 1)
    return xs[f] + (xs[c] - xs[f]) * (k - f)


def summarise(rows):
    walls = [r["wall"] for r in rows]
    ok = [r for r in rows if r["exit"] == 0]
    return {"n": len(rows), "p50": pct(walls, 50), "p95": pct(walls, 95), "p99": pct(walls, 99),
            "mean": statistics.fmean(walls), "stdev": statistics.pstdev(walls) if len(walls) > 1 else 0.0,
            "min": min(walls), "max": max(walls),
            "cpu_mean": statistics.fmean(r["cpu"] for r in rows),
            "maxrss_mb": max(r["maxrss_mb"] for r in rows),
            "rss_p50": pct([r["maxrss_mb"] for r in rows], 50),
            "requests_mean": statistics.fmean(r["requests"] for r in rows),
            "connections_mean": statistics.fmean(r["connections"] for r in rows),
            "mb_mean": statistics.fmean(r["bytes"] for r in rows) / 1e6,
            "error_rate": 1 - len(ok) / len(rows),
            "throughput_checks_per_min": 60 / statistics.fmean(walls)}


def warm(h, d, args=(), extra_env=None, n=3):
    """Untimed runs so state files exist and 'shop down' notices have already gone out."""
    for _ in range(n):
        run(h, d, args, extra_env)


def compare(versions, workload, runs, args=(), profile=None, scenario="baseline", extra_env=None, warmups=3):
    h = Harness(scenario, profile)
    try:
        cfg = WORKLOADS[workload]()
        dirs = {name: make_dir(path, cfg, f"{name}-{workload}") for name, path in versions.items()}
        env = dict(WEBHOOKS, **(extra_env or {}))
        for name, d in dirs.items():
            warm(h, d, args, env, warmups)
        rows = {name: [] for name in versions}
        for i in range(runs):
            for name, d in dirs.items():
                rows[name].append(run(h, d, args, env))
        return {name: {"summary": summarise(r), "runs": r, "dir": dirs[name]} for name, r in rows.items()}
    finally:
        h.stop()


def table(results, title):
    keys = list(results)
    lines = [f"### {title}", "", "| metric | " + " | ".join(keys) + " |", "|---|" + "---|" * len(keys)]
    rows = [("p50 latency (s)", "p50", "{:.2f}"), ("p95 latency (s)", "p95", "{:.2f}"), ("p99 latency (s)", "p99", "{:.2f}"),
            ("mean ± sd (s)", None, None), ("CPU time (s)", "cpu_mean", "{:.2f}"), ("peak memory, median run (MB)", "rss_p50", "{:.1f}"),
            ("HTTP requests / check", "requests_mean", "{:.1f}"), ("TCP+TLS connections / check", "connections_mean", "{:.1f}"),
            ("MB downloaded / check", "mb_mean", "{:.2f}"), ("checks per minute", "throughput_checks_per_min", "{:.1f}"),
            ("error rate", "error_rate", "{:.0%}")]
    for label, key, fmt in rows:
        if key is None:
            vals = [f"{results[k]['summary']['mean']:.2f} ± {results[k]['summary']['stdev']:.2f}" for k in keys]
        else:
            vals = [fmt.format(results[k]["summary"][key]) for k in keys]
        lines.append(f"| {label} | " + " | ".join(vals) + " |")
    return "\n".join(lines)


def startup_time(bot_path, n=15):
    """Interpreter start + `import tcg_bot` (what every cloud run and every restart pays)."""
    d = make_dir(bot_path, cloud_config(), "startup")
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    times = []
    for _ in range(n):
        t0 = time.perf_counter()
        subprocess.run([sys.executable, "-c", "import tcg_bot"], cwd=d, env=env, check=True)
        times.append(time.perf_counter() - t0)
    return {"p50_ms": pct(times, 50) * 1000, "p95_ms": pct(times, 95) * 1000}


def command_latency(v1_files, v2_files, concs=(1, 5, 10), rounds=3, profile=None):
    """Time to build a /deals reply with 1, 5, 10 people asking at once."""
    h = Harness("baseline", profile)
    out = {}
    try:
        dirs = {}
        for name, files in (("v1", v1_files), ("v2", v2_files)):
            d = tempfile.mkdtemp(prefix=f"bench-cmd-{name}-", dir=CACHE)
            for target, src in files.items():
                shutil.copy(src, os.path.join(d, target))
            with open(os.path.join(d, "config.json"), "w", encoding="utf-8") as f:
                json.dump(cloud_config(), f, indent=1)
            dirs[name] = d
        run(h, dirs["v2"])          # the restock bot's last check, which /deals answers from
        for mode in ("v1", "v2-fresh", "v2"):
            d = dirs["v1" if mode == "v1" else "v2"]
            for c in concs:
                h.inet.stats.reset()
                t0 = time.perf_counter()
                p = subprocess.run([sys.executable, os.path.join(HERE, "cmd_bench.py"), d, mode, str(c), str(rounds)],
                                   cwd=d, env=h.env(), capture_output=True, text=True, timeout=900)
                wall = time.perf_counter() - t0
                if p.returncode:
                    raise RuntimeError(p.stderr[-2000:])
                lat = json.loads(p.stdout.strip().splitlines()[-1])["latencies"]
                s = h.inet.stats.snapshot()
                out[f"{mode}@{c}"] = {"mode": mode, "concurrency": c, "p50": pct(lat, 50), "p95": pct(lat, 95),
                                      "max": max(lat), "requests_per_round": s["requests"] / rounds, "wall": wall}
    finally:
        h.stop()
    return out


def delivery(versions, profile=None):
    """Alerts that reach Discord on a fresh install, when Discord rate-limits the first post (429),
    and when Discord is down for one check then back."""
    out = {}
    for case in ("normal", "429_first_post", "down_one_check"):
        h = Harness("baseline", profile)
        try:
            for name, path in versions.items():
                d = make_dir(path, cloud_config(), f"deliv-{name}")
                h.inet.stats.reset()
                h.inet.profile.discord_429 = 1 if case == "429_first_post" else 0
                h.inet.discord_fail = 10 ** 6 if case == "down_one_check" else 0
                run(h, d, (), WEBHOOKS)
                h.inet.discord_fail = 0
                h.inet.profile.discord_429 = 0
                if case == "down_one_check":
                    run(h, d, (), WEBHOOKS)       # Discord is back for the next check
                titles = [e.get("title", "") for p in h.inet.stats.discord for e in p.get("embeds", [])]
                finds = [t for t in titles if t and not t.startswith("🧺")]
                cut = sum(int(x) for p in h.inet.stats.discord for x in __import__("re").findall(r"\+(\d+) more", p.get("content") or ""))
                out[f"{case}/{name}"] = {"delivered": len(finds), "summarised_not_sent": cut}
        finally:
            h.stop()
    return out


def suite(v1, v2, out_dir, runs=30):
    """Everything in the report, in one go."""
    os.makedirs(out_dir, exist_ok=True)
    cal = 1.6     # calibrated: v1 at this latency takes 13-14 s per check, like its real GitHub Actions runs
    res = {"calibration_scale": cal, "when": time.strftime("%Y-%m-%d %H:%M:%S %z")}
    ver = {"v1": v1, "v2": v2}
    steps = [
        ("cloud", lambda: compare(ver, "cloud", runs, profile=Profile(scale=cal))),
        ("pc", lambda: compare(ver, "pc", max(10, runs * 2 // 3), profile=Profile(scale=cal))),
        ("pc_noskip", lambda: compare(ver, "pc_noskip", max(10, runs // 2), profile=Profile(scale=cal))),
        ("sealed_only", lambda: compare(ver, "pc", max(10, runs // 2), args=("--sealed",), profile=Profile(scale=cal))),
        ("fast_network", lambda: compare(ver, "pc", 10, profile=Profile(scale=cal / 2))),
        ("slow_network", lambda: compare(ver, "pc", 10, profile=Profile(scale=cal * 2))),
    ]
    flaky = Profile(scale=cal)
    flaky.flaky_hosts = {"www.gameology.com.au": 0.15, "tcg.goodgames.com.au": 0.15, "www.gumnut.com.au": 0.15}
    flaky.slow_hosts = {"www.tcgroupau.com.au": 4.0}
    steps.append(("faults", lambda: compare(ver, "pc", 12, profile=flaky)))
    for name, fn in steps:
        print(f"... {name}", flush=True)
        r = fn()
        res[name] = {k: {"summary": v["summary"], "runs": v["runs"]} for k, v in r.items()}
        with open(os.path.join(out_dir, "results.json"), "w") as f:
            json.dump(res, f, indent=1)
    print("... startup", flush=True)
    res["startup"] = {"v1": startup_time(v1), "v2": startup_time(v2)}
    print("... delivery", flush=True)
    res["delivery"] = delivery(ver, Profile(scale=0.05, jitter=0))
    print("... commands", flush=True)
    v1_dir, v2_dir = os.path.dirname(os.path.abspath(v1)), os.path.dirname(os.path.abspath(v2))
    cmd_v1 = os.environ.get("V1_COMMANDS") or os.path.join(v1_dir, "commands_bot_v1.py")
    res["commands"] = command_latency({"tcg_bot.py": v1, "commands_bot.py": cmd_v1},
                                      {"tcg_bot.py": v2, "commands_bot.py": os.path.join(v2_dir, "commands_bot.py")},
                                      profile=Profile(scale=cal))
    with open(os.path.join(out_dir, "results.json"), "w") as f:
        json.dump(res, f, indent=1)
    return res


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("suite")
    s.add_argument("--v1", required=True)
    s.add_argument("--v2", required=True)
    s.add_argument("--runs", type=int, default=30)
    s.add_argument("--out", default=os.path.join(HERE, "results"))
    c = sub.add_parser("calibrate")
    c.add_argument("--bot", required=True)
    c.add_argument("--runs", type=int, default=5)
    c.add_argument("--workload", default="cloud")
    c.add_argument("--scale", type=float, default=1.0)
    m = sub.add_parser("compare")
    m.add_argument("--v1", required=True)
    m.add_argument("--v2", required=True)
    m.add_argument("--runs", type=int, default=20)
    m.add_argument("--workload", default="cloud")
    m.add_argument("--scale", type=float, default=1.0)
    m.add_argument("--args", default="")
    m.add_argument("--out")
    e = sub.add_parser("extra", help="add one more scenario to an existing results.json")
    e.add_argument("--name", required=True)
    e.add_argument("--v1", required=True)
    e.add_argument("--v2", required=True)
    e.add_argument("--workload", default="cloud")
    e.add_argument("--scale", type=float, default=1.6)
    e.add_argument("--runs", type=int, default=15)
    e.add_argument("--out", default=os.path.join(HERE, "results"))
    a = ap.parse_args()
    os.makedirs(CACHE, exist_ok=True)
    if a.cmd == "suite":
        suite(a.v1, a.v2, a.out, a.runs)
        return
    if a.cmd == "extra":
        path = os.path.join(a.out, "results.json")
        with open(path) as f:
            res = json.load(f)
        r = compare({"v1": a.v1, "v2": a.v2}, a.workload, a.runs, profile=Profile(scale=a.scale))
        res[a.name] = {k: {"summary": v["summary"], "runs": v["runs"]} for k, v in r.items()}
        with open(path, "w") as f:
            json.dump(res, f, indent=1)
        print(table(r, a.name))
        return
    if a.cmd == "calibrate":
        res = compare({"bot": a.bot}, a.workload, a.runs, profile=Profile(scale=a.scale))
        print(json.dumps(res["bot"]["summary"], indent=1))
        for r in res["bot"]["runs"]:
            print(round(r["wall"], 2), r["requests"], r["connections"], r["statuses"])
    else:
        res = compare({"v1": a.v1, "v2": a.v2}, a.workload, a.runs, args=a.args.split(), profile=Profile(scale=a.scale))
        print(table(res, f"{a.workload} workload, {a.runs} runs each"))
        if a.out:
            json.dump({k: {"summary": v["summary"], "runs": v["runs"]} for k, v in res.items()}, open(a.out, "w"), indent=1)


if __name__ == "__main__":
    main()
