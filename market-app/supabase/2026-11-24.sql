-- One Piece Market: database update of 24 Nov 2026 (feedback, shared binders, sold dates, phone notifications).
-- Supabase > SQL Editor > New query > paste this whole file > Run. Safe to run again.
-- The app works before this is run; these features switch on once it has been.

-- 1. Feedback from testers. Anyone can send (signed in or not); only you read it (Table Editor > feedback).
create table if not exists public.feedback (
  id uuid primary key default gen_random_uuid(),
  user_id uuid default auth.uid() references auth.users on delete set null,
  email text,
  page text,
  note text not null,
  device text,
  photo text,                -- storage path in the photos bucket, if they attached a picture
  created_at timestamptz not null default now()
);
alter table public.feedback enable row level security;
drop policy if exists "anyone can send" on public.feedback;
create policy "anyone can send" on public.feedback for insert to anon, authenticated with check (user_id is null or user_id = auth.uid());
grant insert on public.feedback to anon, authenticated;
grant all on public.feedback to service_role;

-- 2. When something was sold (for the yearly sales report)
alter table public.owned add column if not exists sold_at date;

-- 3. Shared binders: a read-only link to one group of your collection (no prices paid, no notes)
create table if not exists public.shares (
  id text primary key,
  user_id uuid not null default auth.uid() references auth.users on delete cascade,
  grp text not null,
  title text,
  created_at timestamptz not null default now()
);
alter table public.shares enable row level security;
drop policy if exists "own rows" on public.shares;
create policy "own rows" on public.shares for all to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid());
grant select, insert, update, delete on public.shares to authenticated;
grant all on public.shares to service_role;

create or replace function public.get_share(sid text)
returns table (grp text, title text, card text, name text, qty integer, kind text, cond text, lang text, num text)
language sql security definer set search_path = '' stable as $$
  select s.grp, s.title, o.card, o.name, o.qty, o.kind, o.cond, o.lang, o.num
  from public.shares s join public.owned o on o.user_id = s.user_id and coalesce(o.grp, 'Other') = s.grp and o.status = 'owned'
  where s.id = sid
$$;
revoke all on function public.get_share(text) from public;
grant execute on function public.get_share(text) to anon, authenticated;

-- 4. Phone notifications for price alerts
create table if not exists public.push_subs (
  endpoint text primary key,
  user_id uuid not null default auth.uid() references auth.users on delete cascade,
  sub jsonb not null,
  device text,
  created_at timestamptz not null default now()
);
alter table public.push_subs enable row level security;
drop policy if exists "own rows" on public.push_subs;
create policy "own rows" on public.push_subs for all to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid());
grant select, insert, update, delete on public.push_subs to authenticated;
grant all on public.push_subs to service_role;

-- the notification sender's private key lives here; only the server (service_role) can read it
create table if not exists public.app_keys (name text primary key, value text not null);
alter table public.app_keys enable row level security;
revoke all on public.app_keys from anon, authenticated;
grant all on public.app_keys to service_role;

-- remember which alerts were already sent so each one arrives once
alter table public.watchlist add column if not exists notified text;      -- 'below' / 'above' when last sent
alter table public.watchlist add column if not exists notified_at timestamptz;
