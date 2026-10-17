#!/usr/bin/env python3
"""Turn bench/results/results.json into bench/RESULTS.md.   python bench/report.py"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from bench import summarise, table  # noqa: E402

SCENARIOS = [
    ("cloud", "Cloud config (4 cards), calibrated network",
     "The cloud copy's own config.json and today's shop list (4 more sealed shops than on 13 Oct; see Calibration)."),
    ("cloud_slow", "Cloud config, network twice as slow",
     "Every request twice as slow: how the result holds up on a slower link."),
    ("pc", "PC config (5 cards), calibrated network", "Adds Sabo PRB02-014, searched by name, like the PC's want list."),
    ("pc_noskip", "PC config, v2 asks down shops every check",
     "`down_retry_minutes: 0`, so v2 also asks Mayhem and JToys every check: the speed-up without that feature."),
    ("sealed_only", "Booster boxes only (drop mode)", "`--sealed`, what drop mode runs every 60 s."),
    ("fast_network", "PC config, network twice as fast", ""),
    ("slow_network", "PC config, network twice as slow", ""),
    ("faults", "PC config with faults",
     "Gameology, Good Games TCG and Gumnut answer 503 to 15% of requests; TCGroup is 6.4 s slower than normal."),
    ("today", "Cloud config, the shop failures of 14 Oct",
     "Also failing: M-G and Friendly Collectibles (503), as in the cloud copy's scheduled run at 6:35 am on 14 Oct, which took 25 s."),
]


def main():
    path = os.path.join(HERE, "results", "results.json")
    with open(path, encoding="utf-8") as f:
        r = json.load(f)
    out = ["# Benchmark results: v1 vs v2", "",
           f"Run {r.get('when', '')} on commit fb445c5 (the next commit only changes new-listing bookkeeping, which no "
           "timed path uses). Both versions ran unmodified (`python tcg_bot.py`, a fresh process per check, "
           "exactly as the cloud copy runs) against the same local mock shops, alternating v1, v2, v1, v2. "
           "The mock shops are built from the bot's own saved data (recap.json, known_products.json) and speak real "
           "HTTPS with keep-alive and gzip. Mayhem answers 401 and JToys 403, as the real sites did on 13-14 Oct. "
           "Each scenario starts with 3 untimed runs per version so state files exist. "
           "p99 from 30 runs is close to the slowest run.", "",
           "Request, connection and byte counts are exact properties of the code. Times depend on the network model "
           "(per-request server time, connection set-up, bandwidth, random jitter), which is calibrated but still a model.",
           ""]
    for key, title, note in SCENARIOS:
        if key not in r:
            continue
        for v in r[key].values():                      # recompute from the raw runs with today's summarise()
            v["summary"] = summarise(v["runs"])
        res = {k: {"summary": v["summary"]} for k, v in r[key].items()}
        out += [table(res, title).replace("### ", "## ", 1)]
        s1, s2 = r[key]["v1"]["summary"], r[key]["v2"]["summary"]
        out += ["", f"{note} **{s1['p50'] / s2['p50']:.1f}x faster at p50**, {s1['requests_mean'] / max(1, s2['requests_mean']):.1f}x fewer "
                    f"requests, {s1['mb_mean'] / max(0.001, s2['mb_mean']):.1f}x less downloaded.".strip(), ""]
    if "calib_13oct" in r:
        c = summarise(r["calib_13oct"]["v1"]["runs"])
        out += ["## Calibration", "",
                f"With the shop list of 13 Oct (before the 4 extra sealed shops), v1 takes {c['p50']:.1f} s (p50) in the "
                "model; its real manual runs that day took 13 to 14 s in GitHub Actions' \"Check shops\" step.", ""]
    if "startup" in r:
        st = r["startup"]
        out += ["## Start-up (Python start + `import tcg_bot`)", "", "| | v1 | v2 |", "|---|---|---|",
                f"| p50 (ms) | {st['v1']['p50_ms']:.0f} | {st['v2']['p50_ms']:.0f} |",
                f"| p95 (ms) | {st['v1']['p95_ms']:.0f} | {st['v2']['p95_ms']:.0f} |", ""]
    if "delivery" in r:
        d = r["delivery"]
        out += ["## Alert delivery (fresh install, 14 finds under max)", "",
                "| Scenario | v1 delivered | v1 cut off (\"+N more\") | v2 delivered | v2 cut off |", "|---|---|---|---|---|"]
        names = {"normal": "Discord working", "429_first_post": "Discord rate-limits the first post",
                 "down_one_check": "Discord down for one check, back for the next"}
        for case, label in names.items():
            a, b = d.get(f"{case}/v1"), d.get(f"{case}/v2")
            if a and b:
                out.append(f"| {label} | {a['delivered']} | {a['summarised_not_sent']} | {b['delivered']} | {b['summarised_not_sent']} |")
        out.append("")
    if "commands" in r:
        c = r["commands"]
        out += ["## `/deals` reply time (time the bot needs before it can answer)", "",
                "| Version | People asking at once | p50 | p95 | Shop requests per burst |", "|---|---|---|---|---|"]

        def t(x):
            return f"{x * 1000:.1f} ms" if x < 0.1 else f"{x:.2f} s"
        label = {"v1": "v1 (always live)", "v2-fresh": "v2 `fresh:True` (shared live check)", "v2": "v2 default (last check)"}
        for k, v in c.items():
            out.append(f"| {label[v['mode']]} | {v['concurrency']} | {t(v['p50'])} | {t(v['p95'])} | {v['requests_per_round']:.0f} |")
        out += ["", "Discord allows 3 s for the first response, then 15 minutes for a follow-up; v1 and `fresh:True` "
                    "acknowledge first and follow up. The v2 default answers inside the 3 s.", ""]
    abl_path = os.path.join(HERE, "results", "ablation.json")
    if os.path.exists(abl_path):
        with open(abl_path, encoding="utf-8") as f:
            ab = json.load(f)
        for v in ab.values():
            v["summary"] = summarise(v["runs"])
        order = ["v1", "no_keepalive", "no_gzip", "v1_retries", "no_parallel", "no_skip", "v2"]
        step = {"no_keepalive": "everything else (page 2 of Pokebox, per-shop limit, robots.txt)",
                "no_gzip": "kept-alive connections", "v1_retries": "gzip",
                "no_parallel": "no retry waits on refused requests", "no_skip": "boxes and singles at once, parallel pages",
                "v2": "skipping down shops between 15-minute retries"}
        out += ["## Where the time went (cloud config, v2 with each speed-up removed in turn)", "",
                "| Variant | mean (s) | p50 (s) | requests | connections | MB |", "|---|---|---|---|---|---|"]
        for k in order:
            s = ab[k]["summary"]
            out.append(f"| {ab[k]['label']} | {s['mean']:.2f} | {s['p50']:.2f} | {s['requests_mean']:.0f} | "
                       f"{s['connections_mean']:.0f} | {s['mb_mean']:.2f} |")
        out += ["", "| Step from v1 to v2 | change in mean check time (s) |", "|---|---|"]
        for a, b in zip(order, order[1:]):
            out.append(f"| {step[b]} | {ab[b]['summary']['mean'] - ab[a]['summary']['mean']:+.2f} |")
        out += ["", "Variants remove v2's speed-ups cumulatively (see bench/ablate.py). Means are used because they add up; "
                    "a different removal order would split the total a little differently.", ""]
    with open(os.path.join(HERE, "RESULTS.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    print("\n".join(out))


if __name__ == "__main__":
    main()
