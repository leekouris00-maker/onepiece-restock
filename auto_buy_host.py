#!/usr/bin/env python3
"""
The PC side of auto-buy when the bot runs in its container (v2.15)
==================================================================
The container does the checking and the alerts. It can't open your signed-in Chrome, and shouldn't:
shop sign-ins and saved payment details stay on the PC, outside the container and off the VPN.
This small program is the PC's half:

  * it watches the shared data folder for restocks the container says auto-buy may take
    (autobuy_offers.jsonl), checks each one (recent, https links, a shop your own config.json knows),
    and passes it to auto-buy exactly as the bot used to: your list, your limits and budgets still decide;
  * it runs the auto-buy page (open_autobuy.bat) and picks up /autobuy try requests.

Run it with run_pc_side.bat (which run_docker.bat starts for you). It uses the same data folder as the
container (BOT_DATA_DIR, "docker-data" next to the bot by default). The buyer's browser profile
(buyer_profile) and screenshots stay next to the code on the PC and are never shared with the container.
"""
import os
import sys
import time

CODE_DIR = os.path.dirname(os.path.abspath(__file__))
os.environ.setdefault("BOT_DATA_DIR", os.path.join(CODE_DIR, "docker-data"))
os.environ.pop("BOT_CONTAINER", None)
sys.path.insert(0, CODE_DIR)

import tcg_bot as tb  # noqa: E402
import auto_buy  # noqa: E402

POLL_SECONDS = 2


def known_hosts(cfg):
    return {h.lower() for h in tb.shop_names(cfg)}


def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass
    if not os.path.isdir(tb.HERE):
        sys.exit(f"The data folder {tb.HERE} doesn't exist yet. Run run_docker.bat first.")
    cfg = tb.load_config()
    print(f"Auto-buy (PC side) v{tb.VERSION}: watching {auto_buy.OFFERS_PATH}")
    auto_buy.start(tb)
    try:
        import auto_buy_web
        auto_buy_web.start(tb, auto_buy, cfg)
    except Exception as e:  # noqa: BLE001
        print(f"   ! auto-buy page skipped ({tb.redact(e)})")
    try:
        pos = os.path.getsize(auto_buy.OFFERS_PATH)        # only what arrives from now on
    except OSError:
        pos = 0
    last_cfg = time.time()
    while True:
        time.sleep(POLL_SECONDS)
        try:
            if time.time() - last_cfg > 60:
                cfg, last_cfg = tb.load_config(), time.time()
            finds, pos = auto_buy.read_offers(pos, known_hosts(cfg))
            if finds:
                taken = auto_buy.offer(tb, cfg, finds)
                print(f"[{time.strftime('%H:%M:%S')}] from the container: {len(finds)} find(s), auto-buy took {len(taken)}")
        except KeyboardInterrupt:
            raise
        except Exception as e:  # noqa: BLE001
            print(f"   ! {type(e).__name__}: {tb.redact(str(e))[:200]}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
