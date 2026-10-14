# Benchmark results: v1 vs v2

Run 2026-10-14 07:25:46 +1100 on commit fb445c5 (the next commit only changes new-listing bookkeeping, which no timed path uses). Both versions ran unmodified (`python tcg_bot.py`, a fresh process per check, exactly as the cloud copy runs) against the same local mock shops, alternating v1, v2, v1, v2. The mock shops are built from the bot's own saved data (recap.json, known_products.json) and speak real HTTPS with keep-alive and gzip. Mayhem answers 401 and JToys 403, as the real sites did on 13-14 Oct. Each scenario starts with 3 untimed runs per version so state files exist. p99 from 30 runs is close to the slowest run.

Request, connection and byte counts are exact properties of the code. Times depend on the network model (per-request server time, connection set-up, bandwidth, random jitter), which is calibrated but still a model.

## Cloud config (4 cards), calibrated network

| metric | v1 | v2 |
|---|---|---|
| p50 latency (s) | 13.12 | 2.66 |
| p95 latency (s) | 13.43 | 3.19 |
| p99 latency (s) | 13.62 | 3.30 |
| mean ± sd (s) | 13.10 ± 0.21 | 2.71 ± 0.26 |
| CPU time (s) | 0.29 | 0.27 |
| peak memory, median run (MB) | 64.9 | 65.1 |
| HTTP requests / check | 63.0 | 54.0 |
| TCP+TLS connections / check | 63.0 | 28.0 |
| MB downloaded / check | 3.66 | 0.61 |
| checks per minute | 4.6 | 22.1 |
| error rate | 0% | 0% |

The cloud copy's own config.json and today's shop list (4 more sealed shops than on 13 Oct; see Calibration). **4.9x faster at p50**, 1.2x fewer requests, 6.0x less downloaded.

## Cloud config, network twice as slow

| metric | v1 | v2 |
|---|---|---|
| p50 latency (s) | 17.71 | 5.16 |
| p95 latency (s) | 18.71 | 8.07 |
| p99 latency (s) | 18.86 | 8.56 |
| mean ± sd (s) | 17.72 ± 0.58 | 5.60 ± 1.17 |
| CPU time (s) | 0.29 | 0.26 |
| peak memory, median run (MB) | 64.4 | 64.4 |
| HTTP requests / check | 63.0 | 54.0 |
| TCP+TLS connections / check | 63.0 | 28.0 |
| MB downloaded / check | 3.66 | 0.61 |
| checks per minute | 3.4 | 10.7 |
| error rate | 0% | 0% |

Every request twice as slow: how the result holds up on a slower link. **3.4x faster at p50**, 1.2x fewer requests, 6.0x less downloaded.

## PC config (5 cards), calibrated network

| metric | v1 | v2 |
|---|---|---|
| p50 latency (s) | 15.57 | 2.87 |
| p95 latency (s) | 15.91 | 3.21 |
| p99 latency (s) | 15.93 | 3.47 |
| mean ± sd (s) | 15.53 ± 0.26 | 2.88 ± 0.21 |
| CPU time (s) | 0.31 | 0.28 |
| peak memory, median run (MB) | 75.7 | 75.7 |
| HTTP requests / check | 69.0 | 58.0 |
| TCP+TLS connections / check | 69.0 | 28.0 |
| MB downloaded / check | 3.67 | 0.62 |
| checks per minute | 3.9 | 20.9 |
| error rate | 0% | 0% |

Adds Sabo PRB02-014, searched by name, like the PC's want list. **5.4x faster at p50**, 1.2x fewer requests, 5.9x less downloaded.

## PC config, v2 asks down shops every check

| metric | v1 | v2 |
|---|---|---|
| p50 latency (s) | 15.51 | 2.92 |
| p95 latency (s) | 15.79 | 3.06 |
| p99 latency (s) | 15.93 | 3.09 |
| mean ± sd (s) | 15.45 ± 0.26 | 2.90 ± 0.13 |
| CPU time (s) | 0.32 | 0.29 |
| peak memory, median run (MB) | 85.5 | 85.5 |
| HTTP requests / check | 69.0 | 61.0 |
| TCP+TLS connections / check | 69.0 | 31.0 |
| MB downloaded / check | 3.67 | 0.62 |
| checks per minute | 3.9 | 20.7 |
| error rate | 0% | 0% |

`down_retry_minutes: 0`, so v2 also asks Mayhem and JToys every check: the speed-up without that feature. **5.3x faster at p50**, 1.1x fewer requests, 5.9x less downloaded.

## Booster boxes only (drop mode)

| metric | v1 | v2 |
|---|---|---|
| p50 latency (s) | 5.53 | 2.28 |
| p95 latency (s) | 5.76 | 3.01 |
| p99 latency (s) | 5.76 | 3.16 |
| mean ± sd (s) | 5.55 ± 0.13 | 2.38 ± 0.39 |
| CPU time (s) | 0.20 | 0.23 |
| peak memory, median run (MB) | 96.6 | 96.6 |
| HTTP requests / check | 21.0 | 20.0 |
| TCP+TLS connections / check | 21.0 | 19.0 |
| MB downloaded / check | 3.51 | 0.57 |
| checks per minute | 10.8 | 25.2 |
| error rate | 0% | 0% |

`--sealed`, what drop mode runs every 60 s. **2.4x faster at p50**, 1.1x fewer requests, 6.1x less downloaded.

## PC config, network twice as fast

| metric | v1 | v2 |
|---|---|---|
| p50 latency (s) | 12.39 | 1.62 |
| p95 latency (s) | 12.60 | 1.74 |
| p99 latency (s) | 12.61 | 1.80 |
| mean ± sd (s) | 12.38 ± 0.17 | 1.60 ± 0.10 |
| CPU time (s) | 0.31 | 0.27 |
| peak memory, median run (MB) | 106.2 | 106.2 |
| HTTP requests / check | 69.0 | 58.0 |
| TCP+TLS connections / check | 69.0 | 28.0 |
| MB downloaded / check | 3.67 | 0.62 |
| checks per minute | 4.8 | 37.4 |
| error rate | 0% | 0% |

**7.7x faster at p50**, 1.2x fewer requests, 5.9x less downloaded.

## PC config, network twice as slow

| metric | v1 | v2 |
|---|---|---|
| p50 latency (s) | 19.13 | 5.25 |
| p95 latency (s) | 19.60 | 6.27 |
| p99 latency (s) | 19.65 | 6.68 |
| mean ± sd (s) | 19.08 ± 0.45 | 5.36 ± 0.52 |
| CPU time (s) | 0.31 | 0.28 |
| peak memory, median run (MB) | 116.6 | 116.6 |
| HTTP requests / check | 69.0 | 58.0 |
| TCP+TLS connections / check | 69.0 | 28.0 |
| MB downloaded / check | 3.67 | 0.62 |
| checks per minute | 3.1 | 11.2 |
| error rate | 0% | 0% |

**3.6x faster at p50**, 1.2x fewer requests, 5.9x less downloaded.

## PC config with faults

| metric | v1 | v2 |
|---|---|---|
| p50 latency (s) | 19.14 | 7.83 |
| p95 latency (s) | 21.40 | 8.13 |
| p99 latency (s) | 21.63 | 8.14 |
| mean ± sd (s) | 19.40 ± 1.25 | 7.82 ± 0.23 |
| CPU time (s) | 0.32 | 0.27 |
| peak memory, median run (MB) | 126.5 | 126.5 |
| HTTP requests / check | 73.9 | 61.0 |
| TCP+TLS connections / check | 73.9 | 28.2 |
| MB downloaded / check | 3.61 | 0.62 |
| checks per minute | 3.1 | 7.7 |
| error rate | 0% | 0% |

Gameology, Good Games TCG and Gumnut answer 503 to 15% of requests; TCGroup is 6.4 s slower than normal. **2.4x faster at p50**, 1.2x fewer requests, 5.8x less downloaded.

## Cloud config, the shop failures of 14 Oct

| metric | v1 | v2 |
|---|---|---|
| p50 latency (s) | 24.56 | 2.45 |
| p95 latency (s) | 25.22 | 2.97 |
| p99 latency (s) | 25.36 | 3.22 |
| mean ± sd (s) | 24.64 ± 0.36 | 2.50 ± 0.29 |
| CPU time (s) | 0.29 | 0.24 |
| peak memory, median run (MB) | 63.8 | 63.8 |
| HTTP requests / check | 67.0 | 50.0 |
| TCP+TLS connections / check | 67.0 | 24.0 |
| MB downloaded / check | 3.64 | 0.61 |
| checks per minute | 2.4 | 24.0 |
| error rate | 0% | 0% |

Also failing: M-G and Friendly Collectibles (503), as in the cloud copy's scheduled run at 6:35 am on 14 Oct, which took 25 s. **10.0x faster at p50**, 1.3x fewer requests, 6.0x less downloaded.

## Calibration

With the shop list of 13 Oct (before the 4 extra sealed shops), v1 takes 12.7 s (p50) in the model; its real manual runs that day took 13 to 14 s in GitHub Actions' "Check shops" step.

## Start-up (Python start + `import tcg_bot`)

| | v1 | v2 |
|---|---|---|
| p50 (ms) | 84 | 100 |
| p95 (ms) | 97 | 118 |

## Alert delivery (fresh install, 14 finds under max)

| Scenario | v1 delivered | v1 cut off ("+N more") | v2 delivered | v2 cut off |
|---|---|---|---|---|
| Discord working | 11 | 3 | 14 | 0 |
| Discord rate-limits the first post | 10 | 3 | 14 | 0 |
| Discord down for one check, back for the next | 0 | 0 | 14 | 0 |

## `/deals` reply time (time the bot needs before it can answer)

| Version | People asking at once | p50 | p95 | Shop requests per burst |
|---|---|---|---|---|
| v1 (always live) | 1 | 13.02 s | 13.09 s | 62 |
| v1 (always live) | 5 | 12.92 s | 13.19 s | 312 |
| v1 (always live) | 10 | 13.32 s | 26.20 s | 622 |
| v2 `fresh:True` (shared live check) | 1 | 2.43 s | 2.51 s | 56 |
| v2 `fresh:True` (shared live check) | 5 | 2.48 s | 2.92 s | 57 |
| v2 `fresh:True` (shared live check) | 10 | 3.30 s | 3.62 s | 57 |
| v2 default (last check) | 1 | 0.5 ms | 0.7 ms | 0 |
| v2 default (last check) | 5 | 0.4 ms | 0.6 ms | 0 |
| v2 default (last check) | 10 | 0.4 ms | 0.6 ms | 0 |

Discord allows 3 s for the first response, then 15 minutes for a follow-up; v1 and `fresh:True` acknowledge first and follow up. The v2 default answers inside the 3 s.

## Where the time went (cloud config, v2 with each speed-up removed in turn)

| Variant | mean (s) | p50 (s) | requests | connections | MB |
|---|---|---|---|---|---|
| v1 | 12.99 | 12.99 | 63 | 63 | 3.66 |
| new connection per request | 13.11 | 13.08 | 64 | 64 | 3.89 |
| no gzip | 12.84 | 12.82 | 64 | 23 | 3.89 |
| v1 retries (4.5 s per refused request) | 12.96 | 13.00 | 64 | 23 | 0.61 |
| no extra parallelism | 7.15 | 6.85 | 58 | 25 | 0.61 |
| asks down shops every check | 2.66 | 2.61 | 57 | 31 | 0.61 |
| v2 as shipped | 2.75 | 2.59 | 54 | 28 | 0.61 |

| Step from v1 to v2 | change in mean check time (s) |
|---|---|
| everything else (page 2 of Pokebox, per-shop limit, robots.txt) | +0.12 |
| kept-alive connections | -0.27 |
| gzip | +0.12 |
| no retry waits on refused requests | -5.81 |
| boxes and singles at once, parallel pages | -4.49 |
| skipping down shops between 15-minute retries | +0.08 |

Variants remove v2's speed-ups cumulatively (see bench/ablate.py). Means are used because they add up; a different removal order would split the total a little differently.
