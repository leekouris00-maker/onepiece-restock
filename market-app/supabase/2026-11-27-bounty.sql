-- One Piece Market: bounties (27 Nov 2026).
--   * Your bounty: every point you ever earn, plus set-completion bounty. It never goes down (spending doesn't lower it).
--   * Weekly bounties: 3 tasks each week (Monday, Melbourne time), +20 points each, +40 more for all three.
--   * Set completion: 25 / 50 / 75 / 100% of a set's card numbers adds bounty only (no spendable points).
--   * Evening streak reminder: opt-in, one phone notification on days your streak would break.
-- Paste into Supabase > SQL Editor > New query, then Run. Safe to run again. Needs 2026-11-25-rewards.sql first.

-- ---------- tables ----------
-- the points ledger learns a new kind: 'quest'
do $$
declare c text;
begin
  select conname into c from pg_constraint
   where conrelid = 'public.points_ledger'::regclass and contype = 'c' and pg_get_constraintdef(oid) like '%kind%';
  if c is not null then execute format('alter table public.points_ledger drop constraint %I', c); end if;
  alter table public.points_ledger add constraint points_ledger_kind_check
    check (kind in ('checkin','streak','milestone','quest','redeem','refund','adjust'));
end $$;

create table if not exists public.quest_claims (
  user_id uuid not null references auth.users on delete cascade,
  week date not null,                      -- the Monday the week starts on
  id text not null,
  created_at timestamptz not null default now(),
  primary key (user_id, week, id)
);

-- bounty that isn't spendable (set completion)
create table if not exists public.bounty_log (
  id bigint generated always as identity primary key,
  user_id uuid not null references auth.users on delete cascade,
  delta integer not null check (delta > 0),
  label text not null,
  ref text not null,
  created_at timestamptz not null default now(),
  unique (user_id, ref)
);

create table if not exists public.notify_prefs (
  user_id uuid primary key default auth.uid() references auth.users on delete cascade,
  streak boolean not null default false,
  updated_at timestamptz not null default now()
);

do $$
declare t text;
begin
  foreach t in array array['quest_claims','bounty_log'] loop
    execute format('alter table public.%I enable row level security', t);
    execute format('drop policy if exists "read own" on public.%I', t);
    execute format('create policy "read own" on public.%I for select to authenticated using (user_id = auth.uid())', t);
    execute format('revoke insert, update, delete on public.%I from anon, authenticated', t);
    execute format('grant select on public.%I to authenticated', t);
    execute format('grant all on public.%I to service_role', t);
  end loop;
end $$;
alter table public.notify_prefs enable row level security;
drop policy if exists "own row" on public.notify_prefs;
create policy "own row" on public.notify_prefs for all to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid());
grant select, insert, update, delete on public.notify_prefs to authenticated;
revoke all on public.notify_prefs from anon;
grant all on public.notify_prefs to service_role;

-- ---------- weekly bounties ----------
create or replace function public._week_start(d date) returns date
language sql immutable set search_path = '' as $$ select (d - ((extract(isodow from d)::int) - 1))::date $$;

-- the pool: id, label, points. The three for a week are picked the same way for everyone.
create or replace function public._quest_pool() returns table (id text, label text)
language sql immutable set search_path = '' as $$
  values ('movers', 'See this week’s top movers'),
         ('add3', 'Add 3 things to your collection'),
         ('alert', 'Set a price alert'),
         ('binder', 'Make or update a binder'),
         ('scan', 'Scan a card with the camera'),
         ('meta', 'Check the Ban & Meta Radar'),
         ('promos', 'Look at this week’s promos'),
         ('checkin5', 'Check in on 5 days this week'),
         ('search3', 'Look up 3 cards'),
         ('sets', 'Browse a set’s prices')
$$;

create or replace function public._week_quests(wk date) returns text[]
language sql immutable set search_path = '' as $$
  select array_agg(id order by md5(wk::text || id)) from (select id from public._quest_pool() order by md5(wk::text || id) limit 3) q
$$;

-- is a quest done this week (Melbourne Monday 00:00 onwards)?
create or replace function public._quest_done(uid uuid, qid text, wk date) returns boolean
language plpgsql stable set search_path = '' as $$
declare since timestamptz := (wk::timestamp at time zone 'Australia/Melbourne');
begin
  return case qid
    when 'movers'   then exists (select 1 from public.usage where user_id = uid and name = 'movers' and day >= wk)
    when 'add3'     then (select count(*) from public.owned where user_id = uid and added >= wk) >= 3
    when 'alert'    then exists (select 1 from public.usage where user_id = uid and name = 'alert_set' and day >= wk)
    when 'binder'   then exists (select 1 from public.binders where user_id = uid and updated_at >= since)
    when 'scan'     then exists (select 1 from public.usage where user_id = uid and name = 'scan_add' and day >= wk)
    when 'meta'     then exists (select 1 from public.usage where user_id = uid and name = 'meta' and day >= wk)
    when 'promos'   then exists (select 1 from public.usage where user_id = uid and name = 'promos' and day >= wk)
    when 'checkin5' then (select count(*) from public.checkins where user_id = uid and day >= wk) >= 5
    when 'search3'  then coalesce((select sum(n) from public.usage where user_id = uid and name = 'search' and day >= wk), 0) >= 3
    when 'sets'     then exists (select 1 from public.usage where user_id = uid and name = 'sets' and day >= wk)
    else false end;
end $$;

-- lifetime bounty, in points (the app shows it in berries)
create or replace function public._bounty(uid uuid) returns integer
language sql stable set search_path = '' as $$
  select (coalesce((select sum(delta) from public.points_ledger where user_id = uid and kind in ('checkin','streak','milestone','quest')), 0)
        + coalesce((select sum(delta) from public.bounty_log where user_id = uid), 0))::integer
$$;

-- ---------- what the app calls ----------
create or replace function public.my_points() returns jsonb
language plpgsql security definer set search_path = '' as $$
declare uid uuid := auth.uid(); today date := public._mel_today(); s record; wk date; qs text[];
begin
  if uid is null then raise exception 'Sign in first'; end if;
  s := public._streak(uid, today);
  wk := public._week_start(today);
  qs := public._week_quests(wk);
  return jsonb_build_object(
    'pts', public._balance(uid),
    'bounty', public._bounty(uid),
    'today', today,
    'streak', s.n,
    'freeze_left', s.freeze_left,
    'checked_in', exists (select 1 from public.checkins where user_id = uid and day = today),
    'days', coalesce((select jsonb_agg(day order by day) from public.checkins where user_id = uid and day > today - 45), '[]'::jsonb),
    'ms', coalesce((select jsonb_object_agg(id, created_at) from public.milestones where user_id = uid), '{}'::jsonb),
    'log', coalesce((select jsonb_agg(jsonb_build_object('at', created_at, 'delta', delta, 'why', label) order by created_at desc, id desc)
                     from (select * from public.points_ledger where user_id = uid order by created_at desc, id desc limit 25) l), '[]'::jsonb),
    'swaps', coalesce((select jsonb_agg(jsonb_build_object('id', id, 'label', label, 'cost', cost, 'status', status, 'at', created_at) order by created_at desc)
                       from (select * from public.redemptions where user_id = uid order by created_at desc limit 10) r), '[]'::jsonb),
    'week', wk,
    'quests', (select jsonb_agg(jsonb_build_object('id', q, 'label', p.label,
                                                   'done', public._quest_done(uid, q, wk),
                                                   'claimed', exists (select 1 from public.quest_claims c where c.user_id = uid and c.week = wk and c.id = q))
                                order by array_position(qs, q))
               from unnest(qs) q join public._quest_pool() p on p.id = q),
    'sets', coalesce((select jsonb_agg(ref) from public.bounty_log where user_id = uid and ref like 'set:%'), '[]'::jsonb),
    'remind', coalesce((select streak from public.notify_prefs where user_id = uid), false)
  );
end $$;

create or replace function public.claim_quest(qid text) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare uid uuid := auth.uid(); wk date := public._week_start(public._mel_today()); lbl text; added integer;
begin
  if uid is null then raise exception 'Sign in first'; end if;
  if not (qid = any(public._week_quests(wk))) then raise exception 'Not one of this week’s bounties'; end if;
  if not public._quest_done(uid, qid, wk) then raise exception 'Not done yet'; end if;
  perform pg_advisory_xact_lock(hashtext('quest:' || uid::text));
  insert into public.quest_claims (user_id, week, id) values (uid, wk, qid) on conflict do nothing;
  get diagnostics added = row_count;
  if added = 1 then
    select label into lbl from public._quest_pool() where id = qid;
    insert into public.points_ledger (user_id, delta, kind, label, ref) values (uid, 20, 'quest', 'Weekly bounty: ' || lbl, wk || ':' || qid);
    if (select count(*) from public.quest_claims where user_id = uid and week = wk) = 3 then
      insert into public.points_ledger (user_id, delta, kind, label, ref) values (uid, 40, 'quest', 'All 3 weekly bounties done', wk || ':all');
    end if;
  end if;
  return public.my_points() || jsonb_build_object('claimed', added = 1);
end $$;

-- set completion: bounty only. The app sends the set's code (e.g. OP05) and how many card numbers it has;
-- the database counts the different card numbers you own from it.
create or replace function public.claim_set(code text, size integer, pct integer) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare uid uuid := auth.uid(); have integer; need integer; amt integer;
begin
  if uid is null then raise exception 'Sign in first'; end if;
  if code !~ '^[A-Z]{2,4}[0-9]{2}$' then raise exception 'Bad set'; end if;
  if size is null or size < 10 or size > 400 then raise exception 'Bad set size'; end if;
  amt := case pct when 25 then 25 when 50 then 50 when 75 then 100 when 100 then 250 else null end;
  if amt is null then raise exception 'Bad step'; end if;
  select count(distinct upper(num)) into have from public.owned
   where user_id = uid and status = 'owned' and upper(num) like code || '-%';
  need := ceil(size * pct / 100.0);
  if have < need then raise exception 'Not there yet (% of %)', have, need; end if;
  insert into public.bounty_log (user_id, delta, label, ref)
  values (uid, amt, code || ' ' || pct || '% complete', 'set:' || code || ':' || pct)
  on conflict (user_id, ref) do nothing;
  return public.my_points();
end $$;

create or replace function public.set_streak_reminder(onoff boolean) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare uid uuid := auth.uid();
begin
  if uid is null then raise exception 'Sign in first'; end if;
  insert into public.notify_prefs (user_id, streak, updated_at) values (uid, onoff, now())
  on conflict (user_id) do update set streak = excluded.streak, updated_at = now();
  return jsonb_build_object('remind', onoff);
end $$;

-- for the evening job (service key only): people who asked for a reminder, checked in yesterday, not yet today
create or replace function public.streak_reminders() returns table (user_id uuid, streak integer)
language plpgsql stable security definer set search_path = '' as $$
declare today date := public._mel_today(); r record; s record;
begin
  for r in select p.user_id from public.notify_prefs p
            where p.streak
              and exists (select 1 from public.checkins c where c.user_id = p.user_id and c.day = today - 1)
              and not exists (select 1 from public.checkins c where c.user_id = p.user_id and c.day = today)
              and exists (select 1 from public.push_subs ps where ps.user_id = p.user_id) loop
    s := public._streak(r.user_id, today);
    if s.n >= 2 then user_id := r.user_id; streak := s.n; return next; end if;
  end loop;
end $$;

create or replace function public.track(what text) returns void
language plpgsql security definer set search_path = '' as $$
declare uid uuid := auth.uid();
begin
  if uid is null then return; end if;
  if what not in ('open','search','card_add','scan_add','alert_set','import','export','trade','deck','sets','sales','watchlist','rewards','shop','share','meta','promos','binders','movers','poster') then return; end if;
  insert into public.usage (user_id, name, day) values (uid, what, public._mel_today())
  on conflict (user_id, name, day) do update set n = least(public.usage.n + 1, 500);
end $$;

do $$
declare f text;
begin
  foreach f in array array['my_points()','claim_quest(text)','claim_set(text, integer, integer)','set_streak_reminder(boolean)','track(text)'] loop
    execute format('revoke all on function public.%s from public, anon', f);
    execute format('grant execute on function public.%s to authenticated', f);
  end loop;
  foreach f in array array['_week_start(date)','_quest_pool()','_week_quests(date)','_quest_done(uuid, text, date)','_bounty(uuid)','streak_reminders()'] loop
    execute format('revoke all on function public.%s from public, anon, authenticated', f);
  end loop;
  grant execute on function public.streak_reminders() to service_role;
end $$;
