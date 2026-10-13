# Changelog

## 2.0 - 14 Oct 2026

Everything v1 did still works the same way: same commands and flags, same `config.json`, same state
files (`seen.json`, `known_products.json`, `status.json`, `recap.json`), same Discord channels and
message style. Either version can pick up the other's state, so rolling back is just swapping files.

### Faster
- **HTTP client (stdlib only):** one kept-alive TLS connection per shop instead of a new handshake per
  request (urllib forces `Connection: close`), `Accept-Encoding: gzip`, at most 3 requests in flight per
  shop, `If-None-Match` / `If-Modified-Since` revalidation in `--loop` when shops send validators.
- **Retries that make sense:** only timeouts, 5xx, 408, 425 and 429 are retried, with jittered exponential
  backoff or the server's `Retry-After`; no sleep after the last attempt. v1 retried everything and slept
  1.5 s + 3 s per failing URL, so each 401 from Mayhem and 403 from JToys cost 4.5 s.
- **Shared requests:** identical requests within 15 s share one network call (also across concurrent
  Discord commands); a 401/403 from a shop isn't asked again for a minute.
- **More parallel:** boxes and singles are checked at the same time; the three search queries of a search
  shop run together; product pages behind a search are fetched together instead of one by one.
- **Down shops:** after 3 failed checks a shop is retried every 15 minutes (`down_retry_minutes`) instead of
  every check; drop mode always checks everything.

### More reliable
- **No lost alerts:** Discord posts use `?wait=true` (Discord confirms the message was saved), wait out 429s
  and retry 5xx. Finds that still don't get through aren't marked as seen, so the next check posts them.
  v1 marked them as seen first, so a failed post meant the alert was gone for good.
- **No cut-off alerts:** v1 sent at most 10 finds per channel ("+N more, see finds.log", and the cloud copy's
  finds.log is thrown away after each run). v2 sends them all, 10 per message within Discord's 6,000-character
  embed limit, up to 6 messages per channel per check.
- **PC → cloud hand-off gap closed:** while the PC copy is on, the cloud copy holds what it sees; once the PC
  checks in after that, it's dropped (the PC posted it). If the PC goes quiet first, the cloud copy posts it.
  v1 marked those finds as seen and never posted them.
- **Big shops read in full:** Shopify collections are read past the first 250 products (up to 4 pages).
  Products seen for the first time this way are remembered quietly, not announced as new.
- **Atomic state files** (temp file + rename), with retries for Windows file locks; a corrupt file is
  reported and started fresh instead of crashing.
- **config.json checks:** numbers typed as text are fixed, a broken card or shop is switched off with a
  warning (posted once to Discord) instead of crashing the loop, likely typos in setting names are pointed
  out, and a UTF-8 BOM (Notepad) is accepted.
- **Pre-order note fixed:** v1 tagged anything containing "pre" (e.g. "Premium Booster") as a pre-order.
- `finds.log` and the `.bat` logs roll over instead of growing forever.
- The cloud workflows retry their state commit when another push lands at the same time (one recap run
  failed this way on 13 Oct), and no longer commit per-run timestamps.

### New
- **One cart per shop:** singles found at the same Shopify shop get a combined cart link with the cheapest
  copy of each card and your wanted quantities (one order, one shipping fee).
- **Price history:** `price_history.json` (one price per listing per day) and `events.jsonl` (in/out of
  stock). Box alerts show the lowest price seen in 90 days.
- **Auto drop windows** for booster releases in the release list (`auto_drop_windows`).
- **Quiet hours** (`alerts.quiet_hours`) and **/mute**: no pings or phone pushes, except booster boxes in
  quiet hours.
- **Buttons:** a single find gets "⚡ Buy now" / "Open listing" link buttons (falls back to a plain message if
  the webhook doesn't take them).
- **Instant Discord commands** from `latest.json`, `fresh:True` for a live check (shared, 30 s cooldown each).
- **New commands:** `/history`, `/stats`, and admin-only `/want list|add|remove|enable`, `/boxmax`, `/mute`,
  `/unmute` (backups in `config.json.bak`, every change in `audit.log`).
- **robots.txt** is followed (RFC 9309: longest match, wildcards, 24 h cache kept in `status.json`).
- `--dry-run`, `--self-test`, `secrets.json`, webhook/token redaction in logs and status posts,
  per-check timing line and `/status` speed details.

### Trade-offs
- Start-up is about 10-15 ms slower (a bigger file to compile). Checks are seconds faster, so it's a net win
  even for one-shot cloud runs.
- The first check after an upgrade reads each shop's robots.txt once (about 15 small requests); after that
  it's cached for 24 hours.
- A down shop's recovery is noticed within 15 minutes rather than at the next check (set
  `"down_retry_minutes": 0` for v1 behaviour).
