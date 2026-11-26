-- One Piece Market: Restocks (27 Nov 2026). One live feed of retail restocks across Australia from three sources:
--   sighting = a user saw stock in a shop (photo required, account 7+ days old), others confirm "still there" / "gone";
--   shop     = a local store's own post (shop accounts come later);
--   bot      = the restock watcher (written with the service key, only shops that let it in).
-- Confirmed sightings (2+ "still there") add bounty to the poster: bounty only, no spendable points.
-- 3 reports hide a post. The owner can hide posts and ban posters. Alert choices are saved per person.
-- Paste into Supabase > SQL Editor > New query, then Run. Safe to run again. Needs the bounty update first.

-- ---------- tables ----------
create table if not exists public.restock_posts (
  id uuid primary key default gen_random_uuid(),
  source text not null check (source in ('sighting','shop','bot')),
  user_id uuid references auth.users on delete cascade,
  k text,
  title text not null check (length(title) between 3 and 120),
  kind text not null default 'other' check (kind in ('box','pack','case','deck','promo','other')),
  price numeric check (price is null or (price > 0 and price < 100000)),
  store text not null check (length(store) between 2 and 80),
  chain text,
  suburb text check (suburb is null or length(suburb) <= 60),
  state text not null check (state in ('VIC','NSW','QLD','WA','SA','TAS','ACT','NT','ONLINE')),
  url text check (url is null or url ~ '^https://'),
  photo text,
  note text check (note is null or length(note) <= 200),
  ext_id text unique,
  created_at timestamptz not null default now(),
  expires_at timestamptz not null default now() + interval '12 hours',
  gone_at timestamptz,
  hidden boolean not null default false
);
create index if not exists restock_posts_live on public.restock_posts (created_at desc) where not hidden and gone_at is null;

create table if not exists public.restock_votes (
  post_id uuid not null references public.restock_posts on delete cascade,
  user_id uuid not null references auth.users on delete cascade,
  still boolean not null,
  created_at timestamptz not null default now(),
  primary key (post_id, user_id)
);
create table if not exists public.restock_reports (
  post_id uuid not null references public.restock_posts on delete cascade,
  user_id uuid not null references auth.users on delete cascade,
  reason text,
  created_at timestamptz not null default now(),
  primary key (post_id, user_id)
);
create table if not exists public.restock_bans (
  user_id uuid primary key references auth.users on delete cascade,
  created_at timestamptz not null default now()
);
create table if not exists public.restock_alerts (
  user_id uuid primary key default auth.uid() references auth.users on delete cascade,
  enabled boolean not null default true,
  kinds text[] not null default '{box}',
  max_price numeric,
  states text[] not null default '{}',
  sources text[] not null default '{sighting,shop,bot}',
  updated_at timestamptz not null default now()
);
create table if not exists public.restock_sent (
  post_id uuid not null references public.restock_posts on delete cascade,
  user_id uuid not null references auth.users on delete cascade,
  created_at timestamptz not null default now(),
  primary key (post_id, user_id)
);

-- the feed is read through restock_feed(); people never write these tables directly
do $$
declare t text;
begin
  foreach t in array array['restock_posts','restock_votes','restock_reports','restock_bans','restock_sent'] loop
    execute format('alter table public.%I enable row level security', t);
    execute format('revoke all on public.%I from anon, authenticated', t);
    execute format('grant all on public.%I to service_role', t);
  end loop;
end $$;
alter table public.restock_alerts enable row level security;
drop policy if exists "own row" on public.restock_alerts;
create policy "own row" on public.restock_alerts for all to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid());
grant select, insert, update, delete on public.restock_alerts to authenticated;
revoke all on public.restock_alerts from anon;
grant all on public.restock_alerts to service_role;

-- shelf photos: anyone can see them (they're shown in the public feed); you can only add to your own folder
insert into storage.buckets (id, name, public) values ('sightings', 'sightings', true) on conflict (id) do update set public = true;
drop policy if exists "sightings read" on storage.objects;
drop policy if exists "sightings write" on storage.objects;
drop policy if exists "sightings delete" on storage.objects;
create policy "sightings read" on storage.objects for select to anon, authenticated using (bucket_id = 'sightings');
create policy "sightings write" on storage.objects for insert to authenticated
  with check (bucket_id = 'sightings' and (storage.foldername(name))[1] = auth.uid()::text);
create policy "sightings delete" on storage.objects for delete to authenticated
  using (bucket_id = 'sightings' and (storage.foldername(name))[1] = auth.uid()::text);

-- ---------- reading ----------
create or replace function public.restock_feed(st text default null, lim integer default 60) returns jsonb
language sql stable security definer set search_path = '' as $$
  select coalesce(jsonb_agg(x order by x->>'created_at' desc), '[]'::jsonb) from (
    select jsonb_build_object(
      'id', p.id, 'source', p.source, 'k', p.k, 'title', p.title, 'kind', p.kind, 'price', p.price,
      'store', p.store, 'chain', p.chain, 'suburb', p.suburb, 'state', p.state, 'url', p.url, 'photo', p.photo, 'note', p.note,
      'created_at', p.created_at, 'expires_at', p.expires_at,
      'still', (select count(*) from public.restock_votes v where v.post_id = p.id and v.still),
      'gone', (select count(*) from public.restock_votes v where v.post_id = p.id and not v.still),
      'mine', p.user_id is not null and p.user_id = auth.uid(),
      'my_vote', (select v.still from public.restock_votes v where v.post_id = p.id and v.user_id = auth.uid()),
      'poster_bounty', case when p.user_id is null then null else public._bounty(p.user_id) end
    ) x
    from public.restock_posts p
    where not p.hidden and p.gone_at is null and p.expires_at > now()
      and (st is null or p.state = st or p.state = 'ONLINE')
    order by p.created_at desc
    limit least(greatest(coalesce(lim, 60), 1), 200)
  ) q
$$;

-- this week's spotters: confirmed sightings per person (no names, just rank and state)
create or replace function public.restock_top_spotters() returns jsonb
language sql stable security definer set search_path = '' as $$
  select coalesce(jsonb_agg(jsonb_build_object('n', n, 'state', st, 'bounty', public._bounty(uid), 'me', uid = auth.uid()) order by n desc), '[]'::jsonb)
  from (
    select p.user_id uid, count(*) n, mode() within group (order by p.state) st
    from public.restock_posts p
    where p.source = 'sighting' and p.created_at > now() - interval '7 days' and not p.hidden
      and (select count(*) from public.restock_votes v where v.post_id = p.id and v.still) >= 2
    group by p.user_id order by count(*) desc limit 10
  ) t
$$;

-- ---------- posting and voting ----------
-- blank text becomes null
create or replace function public._nz(t text) returns text
language sql immutable set search_path = '' as $$ select case when length(btrim(t)) > 0 then btrim(t) end $$;

create or replace function public.post_sighting(k text, title text, kind text, price numeric, store text, chain text,
                                                suburb text, state text, url text, photo text, note text) returns uuid
language plpgsql security definer set search_path = '' as $$
declare uid uuid := auth.uid(); joined timestamptz; pid uuid;
begin
  if uid is null then raise exception 'Sign in first'; end if;
  if exists (select 1 from public.restock_bans b where b.user_id = uid) then raise exception 'You can’t post restocks'; end if;
  select created_at into joined from auth.users where id = uid;
  if joined > now() - interval '7 days' and not public._is_owner(uid) then
    raise exception 'New accounts can post restocks after 7 days (on %)', to_char((joined + interval '7 days') at time zone 'Australia/Melbourne', 'FMDD Mon');
  end if;
  if photo is null or photo not like uid::text || '/%' then raise exception 'Add a photo of the shelf'; end if;
  if (select count(*) from public.restock_posts p where p.user_id = uid and p.created_at > now() - interval '24 hours') >= 10 then
    raise exception 'That’s 10 restocks today. Try again tomorrow';
  end if;
  if exists (select 1 from public.restock_posts p where p.user_id = uid and lower(p.title) = lower(post_sighting.title)
             and lower(p.store) = lower(post_sighting.store) and p.created_at > now() - interval '6 hours') then
    raise exception 'You already posted that one';
  end if;
  insert into public.restock_posts (source, user_id, k, title, kind, price, store, chain, suburb, state, url, photo, note)
  values ('sighting', uid, public._nz(post_sighting.k), btrim(post_sighting.title), coalesce(post_sighting.kind, 'other'), post_sighting.price,
          btrim(post_sighting.store), public._nz(post_sighting.chain), public._nz(post_sighting.suburb), post_sighting.state,
          public._nz(post_sighting.url), post_sighting.photo, public._nz(post_sighting.note))
  returning id into pid;
  return pid;
end $$;

-- "still there" (true) or "gone" (false). 2 still = confirmed (poster gets ฿10M bounty, post stays up longer);
-- 2 more gone than still = taken down as gone.
create or replace function public.vote_restock(pid uuid, still boolean) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare uid uuid := auth.uid(); p record; ys integer; ns integer;
begin
  if uid is null then raise exception 'Sign in first'; end if;
  select * into p from public.restock_posts where id = pid;
  if p.id is null or p.hidden then raise exception 'That post is gone'; end if;
  if p.user_id = uid then raise exception 'You can’t vote on your own post'; end if;
  insert into public.restock_votes (post_id, user_id, still) values (pid, uid, vote_restock.still)
  on conflict (post_id, user_id) do update set still = excluded.still, created_at = now();
  select count(*) filter (where v.still), count(*) filter (where not v.still) into ys, ns from public.restock_votes v where v.post_id = pid;
  if vote_restock.still then
    update public.restock_posts set expires_at = least(greatest(expires_at, now() + interval '6 hours'), created_at + interval '48 hours') where id = pid;
  end if;
  if ys >= 2 and p.source = 'sighting' and p.user_id is not null then
    insert into public.bounty_log (user_id, delta, label, ref) values (p.user_id, 10, 'Restock confirmed: ' || p.title, 'sighting:' || pid)
    on conflict (user_id, ref) do nothing;
  end if;
  if ns >= ys + 2 then update public.restock_posts set gone_at = now() where id = pid and gone_at is null; end if;
  return jsonb_build_object('still', ys, 'gone', ns);
end $$;

create or replace function public.report_restock(pid uuid, reason text) returns void
language plpgsql security definer set search_path = '' as $$
declare uid uuid := auth.uid();
begin
  if uid is null then raise exception 'Sign in first'; end if;
  insert into public.restock_reports (post_id, user_id, reason) values (pid, uid, left(reason, 200)) on conflict do nothing;
  if (select count(*) from public.restock_reports r where r.post_id = pid) >= 3 then
    update public.restock_posts set hidden = true where id = pid;
  end if;
end $$;

-- your own post: mark it gone (sold out) or delete it
create or replace function public.close_restock(pid uuid, remove boolean) returns void
language plpgsql security definer set search_path = '' as $$
declare uid uuid := auth.uid();
begin
  if uid is null then raise exception 'Sign in first'; end if;
  if remove then delete from public.restock_posts where id = pid and (user_id = uid or public._is_owner(uid));
  else update public.restock_posts set gone_at = now() where id = pid and (user_id = uid or public._is_owner(uid)); end if;
end $$;

-- owner: hide/show a post, ban/unban whoever posted it (a ban hides all their posts)
create or replace function public.owner_restock(pid uuid, action text) returns void
language plpgsql security definer set search_path = '' as $$
declare uid uuid := auth.uid(); poster uuid;
begin
  if not public._is_owner(uid) then raise exception 'Owner only'; end if;
  select user_id into poster from public.restock_posts where id = pid;
  if action = 'hide' then update public.restock_posts set hidden = true where id = pid;
  elsif action = 'show' then update public.restock_posts set hidden = false where id = pid;
  elsif action = 'ban' and poster is not null then
    insert into public.restock_bans (user_id) values (poster) on conflict do nothing;
    update public.restock_posts set hidden = true where user_id = poster;
  else raise exception 'Unknown action'; end if;
end $$;

-- for the alert job (service key only): who wants this post and hasn't had it yet. Marks them as sent.
create or replace function public.restock_targets(pid uuid) returns table (user_id uuid)
language plpgsql security definer set search_path = '' as $$
declare p record;
begin
  select * into p from public.restock_posts where id = pid;
  if p.id is null or p.hidden or p.gone_at is not null then return; end if;
  return query
  with want as (
    select a.user_id from public.restock_alerts a
    where a.enabled and p.kind = any(a.kinds) and p.source = any(a.sources)
      and (a.max_price is null or p.price is null or p.price <= a.max_price)
      and (cardinality(a.states) = 0 or p.state = any(a.states) or p.state = 'ONLINE')
      and a.user_id is distinct from p.user_id
      and exists (select 1 from public.push_subs s where s.user_id = a.user_id)
  ), ins as (
    insert into public.restock_sent (post_id, user_id) select pid, w.user_id from want w on conflict do nothing returning restock_sent.user_id
  )
  select ins.user_id from ins;
end $$;

-- the restock watcher (bot on the PC) posts its finds with its own key, not the database's master key.
-- The key's fingerprint is saved once in app_keys as 'bot_feed_sha' (set up when the bot is switched on).
create or replace function public.bot_post_restock(token text, rows jsonb) returns integer
language plpgsql security definer set search_path = '' as $$
declare want text := (select value from public.app_keys where name = 'bot_feed_sha'); r jsonb; n integer := 0; added integer;
begin
  if want is null or token is null or encode(sha256(convert_to(token, 'UTF8')), 'hex') <> want then raise exception 'Not allowed'; end if;
  if jsonb_typeof(rows) <> 'array' or jsonb_array_length(rows) > 50 then raise exception 'Send up to 50 at a time'; end if;
  for r in select * from jsonb_array_elements(rows) loop
    insert into public.restock_posts (source, k, title, kind, price, store, suburb, state, url, ext_id, expires_at)
    values ('bot', public._nz(r->>'k'), left(r->>'title', 120), coalesce(r->>'kind', 'other'), public._nz(r->>'price')::numeric,
            left(r->>'store', 80), public._nz(r->>'suburb'), coalesce(r->>'state', 'ONLINE'), r->>'url', r->>'ext_id', now() + interval '12 hours')
    on conflict (ext_id) do nothing;
    get diagnostics added = row_count;
    n := n + added;
  end loop;
  return n;
end $$;

create or replace function public.track(what text) returns void
language plpgsql security definer set search_path = '' as $$
declare uid uuid := auth.uid();
begin
  if uid is null then return; end if;
  if what not in ('open','search','card_add','scan_add','alert_set','import','export','trade','deck','sets','sales','watchlist','rewards','shop','share','meta','promos','binders','movers','poster','restocks') then return; end if;
  insert into public.usage (user_id, name, day) values (uid, what, public._mel_today())
  on conflict (user_id, name, day) do update set n = least(public.usage.n + 1, 500);
end $$;

do $$
declare f text;
begin
  foreach f in array array['restock_feed(text, integer)','restock_top_spotters()'] loop
    execute format('revoke all on function public.%s from public', f);
    execute format('grant execute on function public.%s to anon, authenticated', f);
  end loop;
  foreach f in array array['post_sighting(text, text, text, numeric, text, text, text, text, text, text, text)','vote_restock(uuid, boolean)',
                           'report_restock(uuid, text)','close_restock(uuid, boolean)','owner_restock(uuid, text)','track(text)'] loop
    execute format('revoke all on function public.%s from public, anon', f);
    execute format('grant execute on function public.%s to authenticated', f);
  end loop;
  revoke all on function public.bot_post_restock(text, jsonb) from public;
  grant execute on function public.bot_post_restock(text, jsonb) to anon, authenticated;
  revoke all on function public.restock_targets(uuid) from public, anon, authenticated;
  grant execute on function public.restock_targets(uuid) to service_role;
end $$;
