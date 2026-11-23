# One Piece Market (iPhone app)

Your One Piece price tracker and collection as a real iPhone app, built with Expo (React Native).

- **Market:** every English set on TCGplayer, promos included, with TCGplayer's card pictures, prices, 7-day moves and a 35-day price line. Prices come from `market_catalog.json` in this repo, refreshed every morning by the "Market data prices" workflow.
- **My collection:** what you own, what it's worth, groups, sold items, your own photos.
- **eBay sold prices:** track a card and the "eBay sold prices" workflow fetches its sold prices (CompsAPI free plan, about 20 cards).
- **Search** across every set, plus your own Japanese and other cards.

Your data (collection, sales, tracked cards, photos) is stored in **Supabase**, a free online database, under your own account.

## 1. Set up the database (about 10 minutes, free)

1. Go to **supabase.com**, sign up, and click **New project**. Name it `onepiece-market`, pick the **Sydney** region, and set a database password (save it somewhere).
2. When it's ready, open **SQL Editor → New query**, paste everything from [`supabase/schema.sql`](supabase/schema.sql), and click **Run**. It should say "Success".
3. Open **Project Settings → API** (or **Data API**). Copy two things:
   - **Project URL** (looks like `https://abcd1234.supabase.co`)
   - the **anon / public** key
   These two are safe to share. Send them to Claude (or put them into `eas.json` under `EXPO_PUBLIC_SUPABASE_URL` and `EXPO_PUBLIC_SUPABASE_ANON_KEY`).
4. Optional, to sign up without a confirmation email: **Authentication → Sign In / Providers → Email**, turn off **Confirm email**.

**Never share the `service_role` key** in a chat. It's only for GitHub (step 4).

## 2. Move your data from the web page

1. Install the app (step 3), open the **Account** tab and **Create account** with your email.
2. Open the `my-data.sql` file Claude gave you (it's not in this public repo). Replace `YOUR-EMAIL` with the email you signed up with.
3. Paste it into **SQL Editor** and **Run**. Your 46 items, logged sale, Nike DON!! card and 2 tracked cards appear in the app (pull down to refresh). Photos from the web page don't carry over: re-add them in the app.

## 3. Put it on your iPhone

You need:
- An **Apple Developer Program** membership (about A$149 a year, at developer.apple.com/programs; approval can take a day or two).
- A free **Expo** account at expo.dev.
- **Node.js** on your PC (nodejs.org, the LTS version).

Then, in a terminal on your PC:

```
git clone https://github.com/leekouris00-maker/onepiece-restock
cd onepiece-restock/market-app
npm install
npx eas-cli login
npx eas-cli build --platform ios --profile production
```

The build runs in Expo's cloud (no Mac needed). The first time, it asks you to sign in to your Apple account and sets up the certificates for you. When it finishes:

```
npx eas-cli submit --platform ios --latest
```

That uploads it to App Store Connect. Install the **TestFlight** app on your iPhone; the build appears there within about 15–30 minutes and installs like any other app.

**Try it for free first (no Apple membership):** install **Expo Go** from the App Store, then on your PC run `npx expo start` in `market-app` and scan the QR code with your iPhone camera (phone and PC on the same Wi-Fi).

## 4. eBay prices for cards tracked in the app (optional)

In GitHub: **Settings → Secrets and variables → Actions → New repository secret**:
- `COMPSAPI_KEY`: your CompsAPI key
- `SUPABASE_URL`: your Project URL
- `SUPABASE_SERVICE_KEY`: the **service_role** key from Supabase (keep this one secret)

The "eBay sold prices" workflow then reads the cards you track in the app each morning.

## 5. Watchlist and price alerts (one-time database step)
Supabase → SQL Editor → New query → paste `supabase/watchlist.sql` → Run. Until then the watchlist is kept on each device separately.

## What's in the app (23 Nov 2026)
- **Scanner:** versions side by side with their label (Release Event, Alternate Art…); **Stack** mode keeps scanning and collects cards in a tray, then adds them all with one condition / language / group; light button where the phone allows it; a tick you can feel when a card is read.
- **Collection:** swipe a row left for −1 / +1 / Sold; hold a row for the full menu; select several to move, set the price paid, mark sold or remove; everything has Undo. Sort by profit / loss. On a computer it's a table: click a quantity or price to change it.
- **Prices:** every card page says where its price comes from and how fresh it is, with a confidence badge for eBay prices; other versions of the same number; what to offer (70/80/90%); what you'd take home after eBay fees and postage; a price alert.
- **Search:** forgiving ("op17 84", "chopper re", one typo is fine) with recent searches.
- **Your data:** import a CSV (Collectr, TCGplayer or any spreadsheet) with a preview; export to CSV.
- **Speed:** works without signal (saved prices and collection; the app itself is kept on the phone), loading placeholders, pull down to refresh, keyboard shortcuts on a computer (/ search, N add, S scan, Esc back).

## 6. Database update of 24 Nov (one-time)
Supabase → SQL Editor → New query → paste `supabase/2026-11-24.sql` → Run. Switches on: tester feedback (read it in Table Editor → feedback), shared links, exact sale dates for the sales report, and phone notifications.

## Added 24 Nov 2026
- **Feedback button** (round button bottom-left; hide it in Profile) and a **3-screen intro** for new users.
- **Set progress:** each set page shows "84 of 120", a Missing filter and the cost to finish; Profile → Tools → Set progress lists every set you've started. "Count every version" = master set.
- **Trade calculator** (Profile → Tools, Collection ⋯, Market): your cards vs theirs, value theirs at 100/90/80/70%, then optionally do the trade in your collection (with Undo).
- **Card page tools:** Buying (offer prices), Selling (take-home), Grading (worth grading?), Open or keep (booster boxes), Price alert.
- **Open or keep sealed:** expected value of a booster box's cards vs the sealed price, with editable hits-per-box (community estimates).
- **Sales report:** sold items by Australian financial year or calendar year, profit, CSV export.
- **Share a group:** read-only link (Collection ⋯ → Share a group) showing cards and today's prices, never what you paid.
- **Phone notifications** for price alerts (Profile → Phone notifications; iPhone: home-screen app only). Sent each morning by `push_alerts.py` (workflow "Price alert notifications"); its key is made on the first run and kept in the database.

## 7. eBay deal alerts (one-time setup)
1. Supabase → SQL Editor → paste `supabase/2026-11-24b.sql` → Run.
2. Make a free eBay developer account (developer.ebay.com), create a **Production** keyset, and add its App ID and Cert ID to GitHub → Settings → Secrets → Actions as `EBAY_CLIENT_ID` and `EBAY_CLIENT_SECRET`. Optional: an eBay Partner Network campaign id as `EBAY_CAMPAIGN_ID` for affiliate links.
3. On any card: Price alert → "Deal alert" price. The "eBay deal alerts" workflow checks every 2 hours.

## Added 24 Nov 2026 (night)
- **Deck price** (Market, Profile → Tools): paste a decklist → whole-deck cost, what you own, cost to finish, copy a shopping list.
- **Long price history:** card charts 1M / 3M / 6M / 1Y / All, back to Feb 2024 once the "Long price history" workflow has been run with backfill; 90-day high/low signals on card pages and "Price signals" on Home.
- **eBay deal alerts:** see step 7; deals show on Home, in Profile → Tools → eBay deals, and as notifications.

## Publishing on the App Store for everyone (later)

TestFlight is enough for you (and up to 100 people you invite). A public App Store listing also needs App Review, screenshots, a privacy policy page, and the rights to show the card pictures: they're TCGplayer's photos of Bandai's card art. For a public release, switch the pictures to your own photos only (`tcgImage` in `src/data.js`).

## Files

- `app/` screens (expo-router): `(tabs)/index` collection, `(tabs)/market` sets, `(tabs)/search`, `(tabs)/account`, `set/[id]`, `card/[k]`, `item/[id]`, `addcard`
- `src/data.js` prices, account and database; `src/ui.jsx` shared pieces; `src/theme.js` colours and fonts
- `supabase/schema.sql` database tables, security rules and photo storage
- `supabase/delete-account.sql` lets people delete their own account in the app (Profile → Delete my account). Already inside schema.sql; if you set up the database before 22 Nov 2026, run this file once in the SQL Editor.
- `public/privacy.html` the privacy policy (linked from Profile; served at …/onepiece-restock/privacy.html)
