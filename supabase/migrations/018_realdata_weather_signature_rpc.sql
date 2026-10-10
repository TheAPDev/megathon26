-- Join the real weather to every home's metered months: per-home cooling sensitivity (kWh per real CDD24)
-- and weather-normalised base load, via ordinary least squares over the 24 billing months (Oct 2024 - Sep 2026).
create materialized view realdata.home_weather_signature as
with wm as materialized (select city, month, cdd24 from realdata.city_weather_monthly),
     nc as (select city, sum(cdd24) / 2 as normal_cdd24 from wm group by city)
select h.home_id, h.city, count(u.k) as months_used,
       round(regr_slope(u.k, w.cdd24)::numeric, 3) as kwh_per_cdd24,
       round(regr_intercept(u.k, w.cdd24)::numeric, 1) as base_kwh_per_month,
       round(regr_r2(u.k, w.cdd24)::numeric, 3) as r2,
       round(sum(u.k) filter (where u.i > 12)::numeric, 0) as actual_kwh_last12,
       round((regr_intercept(u.k, w.cdd24) * 12 + regr_slope(u.k, w.cdd24) * nc.normal_cdd24)::numeric, 0) as weather_normalised_kwh_year
from public.homes h
cross join lateral unnest(h.kwh_24m) with ordinality u(k, i)
join wm w on w.city = h.city and w.month = (date '2024-10-01' + make_interval(months => (u.i - 1)::int))::date
join nc on nc.city = h.city
where u.k is not null
group by h.home_id, h.city, nc.normal_cdd24
having count(u.k) >= 6;
create unique index on realdata.home_weather_signature (home_id);

-- Service-role RPCs used by the API (GG_REPO=supabase): real-data context for a state, city or home.
create or replace function public.real_state_profile(p_state text) returns jsonb language sql stable set search_path = '' as $$
  select to_jsonb(p) from realdata.state_profile p where p.state = p_state
$$;
create or replace function public.real_city_climate(p_city text) returns jsonb language sql stable set search_path = '' as $$
  select jsonb_build_object(
    'check', (select to_jsonb(c) from realdata.city_climate_check c where c.city = p_city),
    'monthly', (select coalesce(jsonb_agg(to_jsonb(m) - 'city' order by m.month), '[]') from realdata.city_weather_monthly m where m.city = p_city),
    'nasa_climatology', (select jsonb_object_agg(parameter, vals) from (select parameter, jsonb_object_agg(month, value order by month) vals
                          from realdata.city_climatology where city = p_city group by parameter) x))
$$;
create or replace function public.real_home_weather(p_home_id text) returns jsonb language sql stable set search_path = '' as $$
  select to_jsonb(s) from realdata.home_weather_signature s where s.home_id = p_home_id
$$;
create or replace function public.real_sources() returns jsonb language sql stable set search_path = '' as $$
  select coalesce(jsonb_agg(to_jsonb(s) order by s.source_id), '[]') from realdata.sources s
$$;
revoke all on function public.real_state_profile(text), public.real_city_climate(text), public.real_home_weather(text), public.real_sources()
  from public, anon, authenticated;
grant execute on function public.real_state_profile(text), public.real_city_climate(text), public.real_home_weather(text), public.real_sources()
  to service_role;
revoke all on realdata.home_weather_signature from anon, authenticated;
grant select on realdata.home_weather_signature to service_role;
