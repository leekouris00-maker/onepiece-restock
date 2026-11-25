-- One Piece Market: Rewards points saved to accounts, simple usage counts, and an owner-only stats page (25 Nov 2026).
-- Paste this whole file into Supabase > SQL Editor > New query, then Run. Safe to run again.
--
-- What it adds:
--   points_ledger  every point earned or spent (append-only; the balance is the sum, never an editable number)
--   checkins       one row per person per Melbourne day (the database refuses a second one)
--   milestones     one-off rewards, once per person, ever
--   redemptions    points-shop swaps (test phase: recorded for the owner to review; nothing ships automatically)
--   usage          how many times each person did a few key things each day (opened the app, scanned, added a card…)
--   shop_items     the points shop's fixed prices
--   owners         who can see the stats page (the first person to press "Make me the owner" in the app)
-- People can read their own rows but can't write to any of these tables directly: every change goes through the
-- functions below, which check the rules (once a day, enough points, milestone actually done…).
-- Everything is linked to the account with "on delete cascade", so Delete my account removes it all.

-- ---------- tables ----------
create table if not exists public.points_ledger (
  id bigint generated always as identity primary key,
  user_id uuid not null references auth.users on delete cascade,
  delta integer not null,
  kind text not null check (kind in ('checkin','streak','milestone','redeem','refund','adjust')),
  label text not null,
  ref text,
  created_at timestamptz not null default now()
);
create index if not exists points_ledger_user on public.points_ledger (user_id, created_at desc);

create table if not exists public.checkins (
  user_id uuid not null references auth.users on delete cascade,
  day date not null,
  created_at timestamptz not null default now(),
  primary key (user_id, day)
);

create table if not exists public.milestones (
  user_id uuid not null references auth.users on delete cascade,
  id text not null,
  created_at timestamptz not null default now(),
  primary key (user_id, id)
);

create table if not exists public.redemptions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users on delete cascade,
  item text not null,
  label text not null,
  cost integer not null check (cost > 0),
  status text not null default 'requested' check (status in ('requested','sent','cancelled')),
  note text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists redemptions_user on public.redemptions (user_id, created_at desc);

create table if not exists public.usage (
  user_id uuid not null references auth.users on delete cascade,
  name text not null,
  day date not null,
  n integer not null default 1,
  primary key (user_id, name, day)
);
create index if not exists usage_day on public.usage (day);

create table if not exists public.shop_items (
  id text primary key,
  label text not null,
  cost integer not null check (cost > 0),
  aud numeric not null,
  sort integer not null default 0,
  active boolean not null default true
);

create table if not exists public.owners (
  user_id uuid primary key references auth.users on delete cascade,
  created_at timestamptz not null default now()
);

-- the shop's fixed prices (100 points = A$1, set November 2026). Change prices here, with 30 days' notice in the app.
insert into public.shop_items (id, label, cost, aud, sort) values
  ('c5', 'A$5 store credit', 500, 5, 1),
  ('pack', 'OP-18 booster pack', 900, 9, 2),
  ('c10', 'A$10 store credit', 1000, 10, 3),
  ('single20', 'Any single up to A$20', 2000, 20, 4),
  ('c25', 'A$25 store credit', 2500, 25, 5),
  ('single50', 'Any single up to A$50', 5000, 50, 6),
  ('box', 'OP-18 booster box', 28000, 280, 7)
on conflict (id) do nothing;

-- ---------- who can read what ----------
do $$
declare t text;
begin
  foreach t in array array['points_ledger','checkins','milestones','redemptions','usage'] loop
    execute format('alter table public.%I enable row level security', t);
    execute format('drop policy if exists "read own" on public.%I', t);
    execute format('create policy "read own" on public.%I for select to authenticated using (user_id = auth.uid())', t);
    execute format('revoke insert, update, delete on public.%I from anon, authenticated', t);
    execute format('grant select on public.%I to authenticated', t);
    execute format('grant all on public.%I to service_role', t);
  end loop;
end $$;
alter table public.shop_items enable row level security;
drop policy if exists "anyone reads" on public.shop_items;
create policy "anyone reads" on public.shop_items for select to anon, authenticated using (true);
revoke insert, update, delete on public.shop_items from anon, authenticated;
grant select on public.shop_items to anon, authenticated;
grant all on public.shop_items to service_role;
alter table public.owners enable row level security;   -- no policies: only the functions below read it
revoke all on public.owners from anon, authenticated;
grant all on public.owners to service_role;

-- ---------- helpers ----------
create or replace function public._mel_today() returns date
language sql stable set search_path = '' as $$ select (now() at time zone 'Australia/Melbourne')::date $$;

-- days checked in a row, ending today (or yesterday if not checked in yet today);
-- one missed day per calendar month is covered (a "streak freeze") and doesn't add to the count
create or replace function public._streak(uid uuid, today date, out n integer, out freeze_left boolean)
language plpgsql stable set search_path = '' as $$
declare t date := today; frozen text[] := '{}'; m text;
begin
  n := 0;
  if not exists (select 1 from public.checkins c where c.user_id = uid and c.day = t) then t := t - 1; end if;
  loop
    if exists (select 1 from public.checkins c where c.user_id = uid and c.day = t) then
      n := n + 1; t := t - 1;
    else
      m := to_char(t, 'YYYY-MM');
      if not (m = any(frozen)) and exists (select 1 from public.checkins c where c.user_id = uid and c.day = t - 1) then
        frozen := frozen || m; t := t - 1;
      else
        exit;
      end if;
    end if;
  end loop;
  freeze_left := not (to_char(today, 'YYYY-MM') = any(frozen));
end $$;

create or replace function public._balance(uid uuid) returns integer
language sql stable set search_path = '' as $$ select coalesce(sum(delta), 0)::integer from public.points_ledger where user_id = uid $$;

create or replace function public._is_owner(uid uuid) returns boolean
language sql stable set search_path = '' as $$ select exists (select 1 from public.owners where user_id = uid) $$;

-- ---------- what the app calls ----------
-- everything the Rewards page needs in one go
create or replace function public.my_points() returns jsonb
language plpgsql security definer set search_path = '' as $$
declare uid uuid := auth.uid(); today date := public._mel_today(); s record;
begin
  if uid is null then raise exception 'Sign in first'; end if;
  s := public._streak(uid, today);
  return jsonb_build_object(
    'pts', public._balance(uid),
    'today', today,
    'streak', s.n,
    'freeze_left', s.freeze_left,
    'checked_in', exists (select 1 from public.checkins where user_id = uid and day = today),
    'days', coalesce((select jsonb_agg(day order by day) from public.checkins where user_id = uid and day > today - 45), '[]'::jsonb),
    'ms', coalesce((select jsonb_object_agg(id, created_at) from public.milestones where user_id = uid), '{}'::jsonb),
    'log', coalesce((select jsonb_agg(jsonb_build_object('at', created_at, 'delta', delta, 'why', label) order by created_at desc, id desc)
                     from (select * from public.points_ledger where user_id = uid order by created_at desc, id desc limit 25) l), '[]'::jsonb),
    'swaps', coalesce((select jsonb_agg(jsonb_build_object('id', id, 'label', label, 'cost', cost, 'status', status, 'at', created_at) order by created_at desc)
                       from (select * from public.redemptions where user_id = uid order by created_at desc limit 10) r), '[]'::jsonb)
  );
end $$;

-- the daily check-in: +10, and +50 on every 7th day in a row / +250 on day 30
create or replace function public.check_in() returns jsonb
language plpgsql security definer set search_path = '' as $$
declare uid uuid := auth.uid(); today date := public._mel_today(); s record; bonus integer := 0; added integer;
begin
  if uid is null then raise exception 'Sign in first'; end if;
  insert into public.checkins (user_id, day) values (uid, today) on conflict do nothing;
  get diagnostics added = row_count;
  if added = 0 then return public.my_points() || jsonb_build_object('already', true); end if;
  insert into public.points_ledger (user_id, delta, kind, label, ref) values (uid, 10, 'checkin', 'Daily check-in', today::text);
  insert into public.usage (user_id, name, day) values (uid, 'checkin', today) on conflict (user_id, name, day) do nothing;
  s := public._streak(uid, today);
  bonus := case when s.n = 30 then 250 when s.n > 0 and s.n % 7 = 0 then 50 else 0 end;
  if bonus > 0 then
    insert into public.points_ledger (user_id, delta, kind, label, ref) values (uid, bonus, 'streak', s.n || ' days in a row', today::text);
  end if;
  return public.my_points() || jsonb_build_object('bonus', bonus);
end $$;

-- one-off milestones; the database checks they're really done
create or replace function public.claim_milestone(mid text) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare uid uuid := auth.uid(); pts integer; lbl text; ok boolean := false; items integer; added integer;
begin
  if uid is null then raise exception 'Sign in first'; end if;
  select x.p, x.l into pts, lbl from (values
    ('card1', 50, 'Add your first card'), ('card10', 100, '10 things in your collection'), ('card50', 200, '50 things in your collection'),
    ('scan', 50, 'Scan a card with the camera'), ('alert', 25, 'Set a price alert'), ('import', 100, 'Import your collection')
  ) as x(id, p, l) where x.id = mid;
  if pts is null then raise exception 'Unknown milestone'; end if;
  select count(*) into items from public.owned where user_id = uid and status = 'owned';
  ok := case mid
    when 'card1' then items >= 1
    when 'card10' then items >= 10
    when 'card50' then items >= 50
    when 'scan' then exists (select 1 from public.usage where user_id = uid and name = 'scan_add')
    when 'import' then exists (select 1 from public.usage where user_id = uid and name = 'import')
    when 'alert' then exists (select 1 from public.watchlist where user_id = uid and (below is not null or above is not null))
  end;
  if not ok then raise exception 'Not done yet'; end if;
  insert into public.milestones (user_id, id) values (uid, mid) on conflict do nothing;
  get diagnostics added = row_count;
  if added > 0 then
    insert into public.points_ledger (user_id, delta, kind, label, ref) values (uid, pts, 'milestone', lbl, mid);
  end if;
  return public.my_points() || jsonb_build_object('claimed', added > 0, 'points', pts);
end $$;

-- swap points for a shop item (one at a time per person, so two quick taps can't overspend)
create or replace function public.redeem(item_id text) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare uid uuid := auth.uid(); it record; rid uuid;
begin
  if uid is null then raise exception 'Sign in first'; end if;
  perform pg_advisory_xact_lock(hashtext('points:' || uid::text));
  select * into it from public.shop_items where id = item_id and active;
  if it.id is null then raise exception 'That reward isn''t available'; end if;
  if public._balance(uid) < it.cost then raise exception 'Not enough points'; end if;
  insert into public.redemptions (user_id, item, label, cost) values (uid, it.id, it.label, it.cost) returning id into rid;
  insert into public.points_ledger (user_id, delta, kind, label, ref) values (uid, -it.cost, 'redeem', 'Swapped for ' || it.label, rid::text);
  return public.my_points() || jsonb_build_object('redemption', rid);
end $$;

-- take back a swap that hasn't been sent yet (the app's Undo); points come back
create or replace function public.cancel_redemption(rid uuid) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare uid uuid := auth.uid(); r record;
begin
  if uid is null then raise exception 'Sign in first'; end if;
  perform pg_advisory_xact_lock(hashtext('points:' || uid::text));
  select * into r from public.redemptions where id = rid and user_id = uid for update;
  if r.id is null then raise exception 'Not found'; end if;
  if r.status <> 'requested' then raise exception 'This swap has already been %', r.status; end if;
  update public.redemptions set status = 'cancelled', updated_at = now() where id = rid;
  insert into public.points_ledger (user_id, delta, kind, label, ref) values (uid, r.cost, 'refund', 'Swap undone: ' || r.label, rid::text);
  return public.my_points();
end $$;

-- count one use of a feature today (only these names; capped at 500 a day each)
create or replace function public.track(what text) returns void
language plpgsql security definer set search_path = '' as $$
declare uid uuid := auth.uid();
begin
  if uid is null then return; end if;
  if what not in ('open','search','card_add','scan_add','alert_set','import','export','trade','deck','sets','sales','watchlist','rewards','shop','share') then return; end if;
  insert into public.usage (user_id, name, day) values (uid, what, public._mel_today())
  on conflict (user_id, name, day) do update set n = least(public.usage.n + 1, 500);
end $$;

-- ---------- owner ----------
create or replace function public.am_owner() returns jsonb
language sql security definer set search_path = '' as $$
  select jsonb_build_object('owner', public._is_owner(auth.uid()), 'claimable', not exists (select 1 from public.owners))
$$;

-- the first person to call this becomes the owner; after that it does nothing
create or replace function public.claim_owner() returns boolean
language plpgsql security definer set search_path = '' as $$
begin
  if auth.uid() is null then raise exception 'Sign in first'; end if;
  perform pg_advisory_xact_lock(hashtext('owners'));
  if not exists (select 1 from public.owners) then insert into public.owners (user_id) values (auth.uid()); end if;
  return public._is_owner(auth.uid());
end $$;

create or replace function public.owner_stats() returns jsonb
language plpgsql security definer set search_path = '' as $$
declare today date := public._mel_today(); res jsonb;
begin
  if not public._is_owner(auth.uid()) then raise exception 'Only the owner can see this'; end if;
  with act as (
    select user_id, day from public.usage
    union select user_id, day from public.checkins
  ), u as (
    select id, (created_at at time zone 'Australia/Melbourne')::date as s,
           exists (select 1 from public.checkins c where c.user_id = users.id) as rewards
    from auth.users
  ), ret as (
    select
      count(*) filter (where s <= today - 1) as e1,
      count(*) filter (where s <= today - 1 and exists (select 1 from act where act.user_id = u.id and act.day = u.s + 1)) as r1,
      count(*) filter (where s <= today - 7) as e7,
      count(*) filter (where s <= today - 7 and exists (select 1 from act where act.user_id = u.id and act.day between u.s + 7 and u.s + 13)) as r7,
      count(*) filter (where s <= today - 30) as e30,
      count(*) filter (where s <= today - 30 and exists (select 1 from act where act.user_id = u.id and act.day between u.s + 30 and u.s + 59)) as r30,
      count(*) filter (where s <= today - 7 and rewards) as e7r,
      count(*) filter (where s <= today - 7 and rewards and exists (select 1 from act where act.user_id = u.id and act.day between u.s + 7 and u.s + 13)) as r7r,
      count(*) filter (where s <= today - 7 and not rewards) as e7n,
      count(*) filter (where s <= today - 7 and not rewards and exists (select 1 from act where act.user_id = u.id and act.day between u.s + 7 and u.s + 13)) as r7n
    from u
  )
  select jsonb_build_object(
    'today', today,
    'users', (select count(*) from auth.users),
    'new7', (select count(*) from u where s > today - 7),
    'active_today', (select count(distinct user_id) from act where day = today),
    'active7', (select count(distinct user_id) from act where day > today - 7),
    'active30', (select count(distinct user_id) from act where day > today - 30),
    'retention', (select jsonb_build_object('d1', jsonb_build_array(r1, e1), 'd7', jsonb_build_array(r7, e7), 'd30', jsonb_build_array(r30, e30),
                                             'd7_rewards', jsonb_build_array(r7r, e7r), 'd7_no_rewards', jsonb_build_array(r7n, e7n)) from ret),
    'checkins14', coalesce((select jsonb_agg(jsonb_build_object('day', d::date, 'n', (select count(*) from public.checkins c where c.day = d::date)) order by d)
                            from generate_series(today - 13, today, interval '1 day') d), '[]'::jsonb),
    'points', jsonb_build_object(
      'issued', (select coalesce(sum(delta), 0) from public.points_ledger where delta > 0 and kind <> 'refund'),
      'spent', (select coalesce(sum(cost), 0) from public.redemptions where status <> 'cancelled'),
      'outstanding', (select coalesce(sum(delta), 0) from public.points_ledger),
      'holders', (select count(distinct user_id) from public.points_ledger)),
    'swaps', coalesce((select jsonb_agg(jsonb_build_object('id', r.id, 'label', r.label, 'cost', r.cost, 'status', r.status, 'at', r.created_at, 'email', au.email) order by r.created_at desc)
                       from (select * from public.redemptions order by created_at desc limit 50) r join auth.users au on au.id = r.user_id), '[]'::jsonb),
    'features', coalesce((select jsonb_agg(jsonb_build_object('name', name, 'people', p, 'times', t) order by p desc, t desc)
                          from (select name, count(distinct user_id) p, sum(n) t from public.usage where day > today - 30 group by name) f), '[]'::jsonb),
    'milestones', coalesce((select jsonb_object_agg(id, n) from (select id, count(*) n from public.milestones group by id) m), '{}'::jsonb)
  ) into res;
  return res;
end $$;

-- owner marks a swap as sent, or cancels it (points go back)
create or replace function public.owner_set_swap(rid uuid, new_status text) returns void
language plpgsql security definer set search_path = '' as $$
declare r record;
begin
  if not public._is_owner(auth.uid()) then raise exception 'Only the owner can do this'; end if;
  if new_status not in ('sent','cancelled') then raise exception 'Bad status'; end if;
  select * into r from public.redemptions where id = rid for update;
  if r.id is null then raise exception 'Not found'; end if;
  if r.status <> 'requested' then raise exception 'Already %', r.status; end if;
  update public.redemptions set status = new_status, updated_at = now() where id = rid;
  if new_status = 'cancelled' then
    insert into public.points_ledger (user_id, delta, kind, label, ref) values (r.user_id, r.cost, 'refund', 'Swap cancelled: ' || r.label, rid::text);
  end if;
end $$;

-- only signed-in people can call these (the owner ones also check the owners list)
do $$
declare f text;
begin
  foreach f in array array['my_points()','check_in()','claim_milestone(text)','redeem(text)','cancel_redemption(uuid)','track(text)',
                           'am_owner()','claim_owner()','owner_stats()','owner_set_swap(uuid, text)'] loop
    execute format('revoke all on function public.%s from public, anon', f);
    execute format('grant execute on function public.%s to authenticated', f);
  end loop;
  foreach f in array array['_mel_today()','_streak(uuid, date)','_balance(uuid)','_is_owner(uuid)'] loop
    execute format('revoke all on function public.%s from public, anon, authenticated', f);
  end loop;
end $$;
