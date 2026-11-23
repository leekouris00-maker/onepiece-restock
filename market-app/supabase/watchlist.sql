-- Watchlist + price alerts (added 23 Nov 2026). Paste into Supabase > SQL Editor > New query, then Run. Safe to run again.
-- Until this is run, the app keeps your watchlist on each device separately.
create table if not exists public.watchlist (
  user_id uuid not null default auth.uid() references auth.users on delete cascade,
  card text not null,        -- 't:<TCGplayer product id>' or 'u:<custom card id>'
  below numeric,             -- alert when the price drops to this A$ or lower
  above numeric,             -- alert when the price rises to this A$ or higher
  created_at timestamptz not null default now(),
  primary key (user_id, card)
);
alter table public.watchlist enable row level security;
drop policy if exists "own rows" on public.watchlist;
create policy "own rows" on public.watchlist for all to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid());
grant select, insert, update, delete on public.watchlist to authenticated;
grant all on public.watchlist to service_role;
