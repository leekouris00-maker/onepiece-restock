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

## Publishing on the App Store for everyone (later)

TestFlight is enough for you (and up to 100 people you invite). A public App Store listing also needs App Review, screenshots, a privacy policy page, and the rights to show the card pictures: they're TCGplayer's photos of Bandai's card art. For a public release, switch the pictures to your own photos only (`tcgImage` in `src/data.js`).

## Files

- `app/` screens (expo-router): `(tabs)/index` collection, `(tabs)/market` sets, `(tabs)/search`, `(tabs)/account`, `set/[id]`, `card/[k]`, `item/[id]`, `addcard`
- `src/data.js` prices, account and database; `src/ui.jsx` shared pieces; `src/theme.js` colours and fonts
- `supabase/schema.sql` database tables, security rules and photo storage
- `supabase/delete-account.sql` lets people delete their own account in the app (Profile → Delete my account). Already inside schema.sql; if you set up the database before 22 Nov 2026, run this file once in the SQL Editor.
- `public/privacy.html` the privacy policy (linked from Profile; served at …/onepiece-restock/privacy.html)
