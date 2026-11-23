-- One Piece Market: eBay deal alerts (24 Nov 2026). Supabase > SQL Editor > New query > paste > Run. Safe to run again.
alter table public.watchlist add column if not exists deal_below numeric;   -- A$: tell me when listed at or below this

create table if not exists public.deals (
  user_id uuid not null references auth.users on delete cascade,
  item_id text not null,               -- eBay listing id
  card text not null,
  title text,
  price numeric,                       -- A$, including postage
  url text,
  image text,
  found_at timestamptz not null default now(),
  primary key (user_id, item_id)
);
alter table public.deals enable row level security;
drop policy if exists "own rows" on public.deals;
create policy "own rows" on public.deals for select to authenticated using (user_id = auth.uid());
drop policy if exists "own rows delete" on public.deals;
create policy "own rows delete" on public.deals for delete to authenticated using (user_id = auth.uid());
grant select, delete on public.deals to authenticated;
grant all on public.deals to service_role;
