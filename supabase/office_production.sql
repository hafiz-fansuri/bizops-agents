create table public.office_agent_roles (
  id text primary key,
  instructions text not null
);
insert into public.office_agent_roles (id, instructions) values
  ('sales', 'Analyze the sales pipeline, qualify leads, prepare quotes and proposals, and summarize orders. Never claim a sale or discount was committed.'),
  ('inventory', 'Analyze stock, supplier and fulfillment records. Plan counts, reorder quantities and purchasing. Clearly flag absent quantities or lead times.'),
  ('finance', 'Explain provided revenue, costs, cash flow and expenses. Show material assumptions and distinguish estimates from recorded facts. Never move money.'),
  ('support', 'Analyze tickets and incident reports, triage issues and draft replies. Never claim a customer was contacted or a refund was made.'),
  ('marketing', 'Develop positioning, campaign plans, content and draft copy grounded in supplied business facts. Never publish or send anything.');
alter table public.office_agent_roles enable row level security;
revoke all on public.office_agent_roles from anon, authenticated;
grant select on public.office_agent_roles to service_role;

create table public.office_records (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
  category text not null check (category in ('sales','inventory','finance','support','marketing','operations')),
  title text not null check (char_length(title) between 1 and 120),
  body text not null check (char_length(body) between 1 and 4000),
  created_at timestamptz not null default now()
);
create index office_records_owner_date on public.office_records (user_id, created_at desc);
alter table public.office_records enable row level security;
revoke all on public.office_records from anon, authenticated;
grant select, delete on public.office_records to authenticated;
grant insert(category, title, body) on public.office_records to authenticated;
grant select on public.office_records to service_role;
create policy office_records_select on public.office_records for select to authenticated using (user_id = (select auth.uid()));
create policy office_records_insert on public.office_records for insert to authenticated with check (user_id = (select auth.uid()));
create policy office_records_delete on public.office_records for delete to authenticated using (user_id = (select auth.uid()));

create table public.office_runs (
  id uuid primary key,
  user_id uuid not null references auth.users(id) on delete cascade,
  request text not null check (char_length(request) between 1 and 4000),
  status text not null default 'routing' check (status in ('routing','working','complete','failed')),
  assignments jsonb not null default '[]',
  answer text,
  created_at timestamptz not null default now()
);
create index office_runs_owner_date on public.office_runs (user_id, created_at desc);
alter table public.office_runs enable row level security;
revoke all on public.office_runs from anon, authenticated;
grant select on public.office_runs to authenticated;
grant select, insert, update on public.office_runs to service_role;
create policy office_runs_select on public.office_runs for select to authenticated using (user_id = (select auth.uid()));

-- Serialize budget checks per user and admit each idempotency key at most once.
create function public.office_admit_run(owner_id uuid, run_id uuid, prompt text)
returns boolean language plpgsql set search_path = '' as $$
begin
  perform pg_advisory_xact_lock(hashtextextended(owner_id::text, 0));
  if exists (select 1 from public.office_runs where id = run_id) then return false; end if;
  if exists (
    select 1 from public.office_runs
    where user_id = owner_id and status in ('routing','working')
      and created_at > now() - interval '3 minutes'
  ) or (
    select count(*) from public.office_runs where user_id = owner_id and created_at > now() - interval '1 day'
  ) >= 30 then return false; end if;
  insert into public.office_runs (id, user_id, request) values (run_id, owner_id, prompt);
  return true;
end;
$$;
revoke all on function public.office_admit_run(uuid, uuid, text) from public, anon, authenticated;
grant execute on function public.office_admit_run(uuid, uuid, text) to service_role;
