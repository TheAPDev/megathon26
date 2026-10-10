-- Row-level security. The FastAPI backend uses the service-role key (bypasses RLS) server-side only.
-- Clients using Supabase Auth see reference data and only their own customer, homes, scores and memory.
-- Analysts are users whose JWT app_metadata carries {"app_role": "analyst"}.

create or replace function public.is_analyst() returns boolean language sql stable set search_path = '' as $$
  select coalesce((auth.jwt() -> 'app_metadata' ->> 'app_role') = 'analyst', false)
$$;

create or replace function public.my_customer_ids() returns setof text language sql stable security definer set search_path = '' as $$
  select customer_id from public.customers where auth_user_id = (select auth.uid())
$$;
revoke all on function public.my_customer_ids() from public;
grant execute on function public.my_customer_ids() to authenticated;

do $$
declare t text;
begin
  foreach t in array array['cities','tariff_states','tariff_slabs','emission_factors','subsidy_rules','finance_products',
                           'appliances','retrofit_catalogue','zone_suitability','benchmarks','customers','homes','retrofit_events',
                           'sales','memory','home_scores','advisor_logs','telegram_links','bill_uploads','model_registry']
  loop
    execute format('alter table public.%I enable row level security', t);
  end loop;
  -- reference data: readable by everyone, writable by nobody through the API
  foreach t in array array['cities','tariff_states','tariff_slabs','emission_factors','subsidy_rules','finance_products',
                           'appliances','retrofit_catalogue','zone_suitability','benchmarks','model_registry']
  loop
    execute format('create policy "public read" on public.%I for select to anon, authenticated using (true)', t);
  end loop;
end $$;

create policy "own customer" on public.customers for select to authenticated
  using (customer_id in (select public.my_customer_ids()) or (select public.is_analyst()));
create policy "own homes" on public.homes for select to authenticated
  using (customer_id in (select public.my_customer_ids()) or (select public.is_analyst()));
create policy "own scores" on public.home_scores for select to authenticated
  using (home_id in (select home_id from public.homes where customer_id in (select public.my_customer_ids())) or (select public.is_analyst()));
create policy "own events" on public.retrofit_events for select to authenticated
  using (home_id in (select home_id from public.homes where customer_id in (select public.my_customer_ids())) or (select public.is_analyst()));
create policy "own memory read" on public.memory for select to authenticated
  using (customer_id in (select public.my_customer_ids()));
create policy "own memory write" on public.memory for insert to authenticated
  with check (customer_id in (select public.my_customer_ids()));
create policy "analyst sales" on public.sales for select to authenticated using ((select public.is_analyst()));
create policy "analyst logs" on public.advisor_logs for select to authenticated using ((select public.is_analyst()));
-- telegram_links and bill_uploads: service role only (no policies => no client access)

-- Engine/generator schemas are not exposed to API roles
revoke all on schema synth from anon, authenticated;
revoke all on schema gg from anon, authenticated;
