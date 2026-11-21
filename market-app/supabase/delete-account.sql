-- One Piece Market: lets a signed-in person delete their own account from the app (Profile > Delete account).
-- Paste into Supabase > SQL Editor > New query, then Run. Safe to run again. (Also included in schema.sql.)
-- Their collection, sales, own cards, tracked searches and photo records go with the login
-- (every table is "on delete cascade"); the app removes their photo files first.
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
