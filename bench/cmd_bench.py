#!/usr/bin/env python3
"""
How long a /deals reply takes to build, for one version of the bot, with N people asking at once.
Run by bench.py in a bot folder (so `import tcg_bot` / `import commands_bot` get that version):

    python cmd_bench.py <bot dir> <mode: v1 | v2 | v2-fresh> <concurrency> <rounds>

Prints JSON: per-request latencies in seconds. Discord itself isn't involved - this is the time the
bot spends before it can answer (Discord gives 3 s for the first response, 15 min for a follow-up).
"""
import asyncio
import json
import os
import sys
import time


async def main():
    folder, mode, conc, rounds = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
    sys.path.insert(0, folder)
    os.chdir(folder)
    sys.argv = ["commands_bot.py"]
    import commands_bot as cb
    cfg = cb.cfg_now()
    lat = []

    async def one_v1():
        t0 = time.perf_counter()
        await asyncio.to_thread(cb.build_deals, cfg)
        lat.append(time.perf_counter() - t0)

    async def one_v2(fresh, uid):
        t0 = time.perf_counter()
        data, t, kind, note = await cb.get_data(cfg, fresh, uid)
        cb.build_deals(cfg, data, kind, t, note=note)
        lat.append(time.perf_counter() - t0)

    for r in range(rounds):
        if mode == "v1":
            await asyncio.gather(*(one_v1() for _ in range(conc)))
        else:
            # every round starts cold, as if asked minutes after the last one: no shared result, no
            # remembered responses, no warm connections (the robots.txt cache stays, as it would)
            cb.LIVE.result, cb.LIVE.t = None, 0.0
            cb._cooldown.clear()
            cb.tb.HTTP.memo.clear()
            cb.tb.HTTP.close_idle()
            await asyncio.gather(*(one_v2(mode == "v2-fresh", f"u{r}-{i}") for i in range(conc)))
    print(json.dumps({"mode": mode, "concurrency": conc, "latencies": lat}))


if __name__ == "__main__":
    asyncio.run(main())
