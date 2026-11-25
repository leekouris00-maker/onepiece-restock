-- One Piece Market: count use of the new Ban & Meta and Promos pages on the owner stats page (26 Nov 2026).
-- Optional. Paste into Supabase > SQL Editor > New query, then Run. Safe to run again.
create or replace function public.track(what text) returns void
language plpgsql security definer set search_path = '' as $$
declare uid uuid := auth.uid();
begin
  if uid is null then return; end if;
  if what not in ('open','search','card_add','scan_add','alert_set','import','export','trade','deck','sets','sales','watchlist','rewards','shop','share','meta','promos') then return; end if;
  insert into public.usage (user_id, name, day) values (uid, what, public._mel_today())
  on conflict (user_id, name, day) do update set n = least(public.usage.n + 1, 500);
end $$;
revoke all on function public.track(text) from public, anon;
grant execute on function public.track(text) to authenticated;
