-- PENDING (needs owner confirmation because it drops/recreates policies): move RLS helper functions out of the
-- exposed `public` schema into `private`, so they are no longer callable via /rest/v1/rpc.
-- Run in the Supabase SQL editor or: supabase db push
create schema if not exists private;
grant usage on schema private to authenticated;

create or replace function private.my_customer_ids() returns setof text language sql stable security definer set search_path = '' as $$
  select customer_id from public.customers where auth_user_id = (select auth.uid())
$$;
create or replace function private.is_analyst() returns boolean language sql stable set search_path = '' as $$
  select coalesce((auth.jwt() -> 'app_metadata' ->> 'app_role') = 'analyst', false)
$$;
revoke all on function private.my_customer_ids() from public, anon;
grant execute on function private.my_customer_ids() to authenticated;
grant execute on function private.is_analyst() to authenticated;

drop policy "own customer" on public.customers;
drop policy "own homes" on public.homes;
drop policy "own scores" on public.home_scores;
drop policy "own events" on public.retrofit_events;
drop policy "own memory read" on public.memory;
drop policy "own memory write" on public.memory;
drop policy "analyst sales" on public.sales;
drop policy "analyst logs" on public.advisor_logs;

create policy "own customer" on public.customers for select to authenticated
  using (customer_id in (select private.my_customer_ids()) or (select private.is_analyst()));
create policy "own homes" on public.homes for select to authenticated
  using (customer_id in (select private.my_customer_ids()) or (select private.is_analyst()));
create policy "own scores" on public.home_scores for select to authenticated
  using (home_id in (select home_id from public.homes where customer_id in (select private.my_customer_ids())) or (select private.is_analyst()));
create policy "own events" on public.retrofit_events for select to authenticated
  using (home_id in (select home_id from public.homes where customer_id in (select private.my_customer_ids())) or (select private.is_analyst()));
create policy "own memory read" on public.memory for select to authenticated
  using (customer_id in (select private.my_customer_ids()));
create policy "own memory write" on public.memory for insert to authenticated
  with check (customer_id in (select private.my_customer_ids()));
create policy "analyst sales" on public.sales for select to authenticated using ((select private.is_analyst()));
create policy "analyst logs" on public.advisor_logs for select to authenticated using ((select private.is_analyst()));

drop function public.my_customer_ids();
drop function public.is_analyst();

