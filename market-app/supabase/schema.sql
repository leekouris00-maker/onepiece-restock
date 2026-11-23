-- One Piece Market: database setup for Supabase.
-- Paste this whole file into Supabase > SQL Editor > New query, then Run. Safe to run again.
-- Every row belongs to the signed-in user; nobody else can read or change it.

create table if not exists public.owned (
  id text primary key,
  user_id uuid not null default auth.uid() references auth.users on delete cascade,
  card text,                 -- 't:<TCGplayer product id>' or 'u:<custom card id>', null for other items
  name text not null,
  qty integer not null default 1 check (qty > 0),
  kind text,                 -- Card, Promo, DON!!, Sealed, Other
  cond text,                 -- Raw, Sealed, PSA 10, ...
  lang text default 'EN',
  grp text default 'Other',  -- your group: Binder, Sabo deck, ...
  paid numeric,              -- A$ each
  value numeric,             -- your own A$ value each (null = automatic)
  notes text,
  status text not null default 'owned' check (status in ('owned','sold')),
  sold_for numeric,          -- A$ each
  added date default current_date,
  num text,
  photo text,                -- storage path of your photo (items without a catalogue card)
  updated_at timestamptz not null default now()
);

create table if not exists public.sales (
  id text primary key,
  user_id uuid not null default auth.uid() references auth.users on delete cascade,
  card text not null,
  price numeric not null check (price > 0),
  cur text not null default 'AUD' check (cur in ('AUD','USD')),
  date date not null default current_date,
  grade text default 'Raw',
  link text,
  note text,
  created_at timestamptz not null default now()
);

create table if not exists public.cards (
  id text primary key,
  user_id uuid not null default auth.uid() references auth.users on delete cascade,
  lang text default 'JP',
  num text,
  name text not null,
  set_name text not null,
  rar text,
  note text,
  created_at timestamptz not null default now()
);

create table if not exists public.watch (
  user_id uuid not null default auth.uid() references auth.users on delete cascade,
  card text not null,
  q text not null,
  lang text,
  graded boolean,
  updated_at timestamptz not null default now(),
  primary key (user_id, card)
);

create table if not exists public.photos (
  user_id uuid not null default auth.uid() references auth.users on delete cascade,
  card text not null,
  path text not null,
  updated_at timestamptz not null default now(),
  primary key (user_id, card)
);

do $$
declare t text;
begin
  foreach t in array array['owned','sales','cards','watch','photos'] loop
    execute format('alter table public.%I enable row level security', t);
    execute format('drop policy if exists "own rows" on public.%I', t);
    execute format('create policy "own rows" on public.%I for all to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid())', t);
    -- signed-in users may use the table (the policy above still limits them to their own rows);
    -- needed when the project doesn't grant API access to new tables automatically
    execute format('grant select, insert, update, delete on public.%I to authenticated', t);
    execute format('grant all on public.%I to service_role', t);
  end loop;
end $$;

-- Private bucket for card photos; each user can only use their own folder (<user id>/...).
insert into storage.buckets (id, name, public) values ('photos', 'photos', false)
on conflict (id) do nothing;

drop policy if exists "own photos read" on storage.objects;
drop policy if exists "own photos write" on storage.objects;
drop policy if exists "own photos update" on storage.objects;
drop policy if exists "own photos delete" on storage.objects;
create policy "own photos read" on storage.objects for select to authenticated
  using (bucket_id = 'photos' and (storage.foldername(name))[1] = auth.uid()::text);
create policy "own photos write" on storage.objects for insert to authenticated
  with check (bucket_id = 'photos' and (storage.foldername(name))[1] = auth.uid()::text);
create policy "own photos update" on storage.objects for update to authenticated
  using (bucket_id = 'photos' and (storage.foldername(name))[1] = auth.uid()::text);
create policy "own photos delete" on storage.objects for delete to authenticated
  using (bucket_id = 'photos' and (storage.foldername(name))[1] = auth.uid()::text);

-- ---- Account deletion (Profile > Delete account) ----
create or replace function public.delete_my_account()
returns void
language plpgsql
security definer
set search_path = ''
as $$
declare uid uuid := auth.uid();
begin
  if uid is null then
    raise exception 'Not signed in';
  end if;
  delete from auth.users where id = uid;
end;
$$;

revoke all on function public.delete_my_account() from public, anon;
grant execute on function public.delete_my_account() to authenticated;

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
