create table public.office_workspaces (
  user_id uuid primary key default auth.uid() references auth.users(id) on delete cascade,
  revision integer not null default 0 check (revision >= 0),
  payload jsonb not null default '{}'::jsonb check (jsonb_typeof(payload) = 'object' and octet_length(payload::text) <= 262144)
);
alter table public.office_workspaces enable row level security;
revoke all on public.office_workspaces from anon, authenticated;
grant select, insert, update on public.office_workspaces to authenticated;
create policy "Read own workspace" on public.office_workspaces for select to authenticated using ((select auth.uid()) = user_id);
create policy "Create own workspace" on public.office_workspaces for insert to authenticated with check ((select auth.uid()) = user_id);
create policy "Update own workspace" on public.office_workspaces for update to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
