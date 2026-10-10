-- Advisor fixes applied (non-destructive): pin search_path, revoke anon execute, index every foreign key.
alter function synth.norm() set search_path = '';
alter function synth.pick(text[], real[]) set search_path = '';
alter function synth.poisson(real) set search_path = '';
alter function synth.apply(public.homes, text) set search_path = '';
alter function synth.feasible(public.homes, text) set search_path = '';
alter function synth.generate(int, int, double precision) set search_path = '';
revoke execute on function public.my_customer_ids() from anon;
create index if not exists advisor_logs_customer_idx on public.advisor_logs (customer_id);
create index if not exists advisor_logs_home_idx on public.advisor_logs (home_id);
create index if not exists bill_uploads_home_idx on public.bill_uploads (home_id);
create index if not exists customers_city_idx on public.customers (city);
create index if not exists memory_home_idx on public.memory (home_id);
create index if not exists retrofit_events_retrofit_idx on public.retrofit_events (retrofit_id);
create index if not exists telegram_links_home_idx on public.telegram_links (home_id);
comment on table public.telegram_links is 'Service-role only: RLS enabled with no policies by design (no client access).';
comment on table public.bill_uploads is 'Service-role only: RLS enabled with no policies by design (no client access).';
