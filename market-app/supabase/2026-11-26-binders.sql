-- One Piece Market: binders (26 Nov 2026). A binder is a page-by-page view of cards: from a collection group,
-- from a whole set (missing cards shown faded), or cards you pick and arrange yourself.
-- Paste into Supabase > SQL Editor > New query, then Run. Safe to run again.
-- Until this is run, the app keeps binders on the device instead.
create table if not exists public.binders (
  id text primary key,
  user_id uuid not null default auth.uid() references auth.users on delete cascade,
  name text not null default 'My binder',
  color text not null default 'lime',
  grid text not null default '3x3' check (grid in ('2x2','3x3','4x3')),
  source jsonb not null default '{"kind":"pick"}'::jsonb,   -- {kind:'group',group} | {kind:'set',set,master} | {kind:'pick'}
  sort text not null default 'number' check (sort in ('number','price','added','custom')),
  slots jsonb not null default '[]'::jsonb,                -- custom order: ["o:<owned id>", "k:<card key>", null (empty pocket)]
  show_prices boolean not null default true,
  position integer not null default 0,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists binders_user on public.binders (user_id, position);
alter table public.binders enable row level security;
drop policy if exists "own binders" on public.binders;
create policy "own binders" on public.binders for all to authenticated
  using (user_id = auth.uid()) with check (user_id = auth.uid());
grant select, insert, update, delete on public.binders to authenticated;
revoke all on public.binders from anon;
grant all on public.binders to service_role;

-- Owner stats: also count visits to Binders (and the Market's Meta / Promos tabs)
create or replace function public.track(what text) returns void
language plpgsql security definer set search_path = '' as $$
declare uid uuid := auth.uid();
begin
  if uid is null then return; end if;
  if what not in ('open','search','card_add','scan_add','alert_set','import','export','trade','deck','sets','sales','watchlist','rewards','shop','share','meta','promos','binders') then return; end if;
  insert into public.usage (user_id, name, day) values (uid, what, public._mel_today())
  on conflict (user_id, name, day) do update set n = least(public.usage.n + 1, 500);
end $$;
revoke all on function public.track(text) from public, anon;
grant execute on function public.track(text) to authenticated;
