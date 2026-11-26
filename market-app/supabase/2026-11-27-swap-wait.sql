-- One Piece Market: swaps open once an account is 30 days old (27 Nov 2026). Earning points starts straight away.
-- The app's owner is exempt so swaps can still be tested. Paste into Supabase > SQL Editor, then Run. Safe to run again.
create or replace function public.redeem(item_id text) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare uid uuid := auth.uid(); it record; rid uuid; joined timestamptz;
begin
  if uid is null then raise exception 'Sign in first'; end if;
  select created_at into joined from auth.users where id = uid;
  if joined > now() - interval '30 days' and not public._is_owner(uid) then
    raise exception 'Swaps open 30 days after you join (on %)', to_char((joined + interval '30 days') at time zone 'Australia/Melbourne', 'FMDD Mon');
  end if;
  perform pg_advisory_xact_lock(hashtext('points:' || uid::text));
  select * into it from public.shop_items where id = item_id and active;
  if it.id is null then raise exception 'That reward isn’t available'; end if;
  if public._balance(uid) < it.cost then raise exception 'Not enough points'; end if;
  insert into public.redemptions (user_id, item, label, cost) values (uid, it.id, it.label, it.cost) returning id into rid;
  insert into public.points_ledger (user_id, delta, kind, label, ref) values (uid, -it.cost, 'redeem', 'Swapped for ' || it.label, rid::text);
  return public.my_points() || jsonb_build_object('redemption', rid);
end $$;
revoke all on function public.redeem(text) from public, anon;
grant execute on function public.redeem(text) to authenticated;
