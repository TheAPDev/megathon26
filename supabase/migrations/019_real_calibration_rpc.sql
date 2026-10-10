-- Service-role RPC for the calibration report (synthetic population vs Census 2011 / NFHS-5, per state).
create or replace function public.real_synth_vs_real() returns jsonb language sql stable set search_path = '' as $$
  select coalesce(jsonb_agg(to_jsonb(v) order by v.homes desc), '[]') from realdata.synth_vs_real_state v
$$;
revoke all on function public.real_synth_vs_real() from public, anon, authenticated;
grant execute on function public.real_synth_vs_real() to service_role;
