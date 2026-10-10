-- Lender portfolio served from Postgres (mirrors greenghar/engine/portfolio.py). Called by the API in
-- GG_REPO=supabase mode via /rest/v1/rpc/<name> with the service-role key; not executable by anon/authenticated.

create or replace view public.portfolio_frame with (security_invoker = true) as
select s.home_id, c.customer_id, h.city, h.state, h.zone, h.dwelling_type, h.floor_position, h.tenure, h.roof_access, h.pv_kw,
       h.lat, h.lon, s.score, s.band, s.confidence, s.weakest_component, s.warnings, s.improvement_potential_pct,
       s.package_saving_inr, s.package_co2_saving_kg, s.baseline_co2_kg, s.score_after_package, s.package_retrofits,
       c.has_home_loan, c.loan_outstanding_inr, c.property_value_inr, c.credit_band, c.consent_marketing, c.preferred_language,
       case when c.has_home_loan then least(1, greatest(0, c.loan_outstanding_inr / nullif(c.property_value_inr, 0))) else 0 end as attribution,
       case when h.dwelling_type = 'apartment'
            then upper(left(h.city, 3)) || '-' || round(h.lat * 100)::int || '-' || round(h.lon * 100)::int end as society_id
from public.home_scores s join public.homes h using (home_id) join public.customers c on c.customer_id = h.customer_id;

create or replace function public.portfolio_summary(p_city text default null, p_state text default null) returns jsonb
language sql stable set search_path = '' as $$
  with d as (select * from public.portfolio_frame where has_home_loan and (p_city is null or city = p_city) and (p_state is null or state = p_state))
  select jsonb_build_object(
    'homes_with_loans', (select count(*) from d),
    'mean_score', (select round(avg(score)::numeric, 1) from d),
    'median_score', (select percentile_cont(0.5) within group (order by score) from d),
    'band_counts', (select jsonb_build_object('Highly efficient', count(*) filter (where band = 'Highly efficient'), 'Good', count(*) filter (where band = 'Good'),
                       'Moderate', count(*) filter (where band = 'Moderate'), 'Poor', count(*) filter (where band = 'Poor'), 'Very poor', count(*) filter (where band = 'Very poor')) from d),
    'poor_or_very_poor_share', (select round(avg((band in ('Poor', 'Very poor'))::int)::numeric, 4) from d),
    'score_histogram', jsonb_build_object('bin_edges', (select jsonb_agg(e) from generate_series(0, 100, 5) e),
                       'counts', (select jsonb_agg(coalesce(n, 0) order by b) from generate_series(0, 19) b
                                  left join (select least(score / 5, 19) bb, count(*) n from d group by 1) x on x.bb = b)),
    'financed_emissions_t_co2', (select round((sum(baseline_co2_kg * attribution) / 1000)::numeric, 1) from d),
    'financed_emissions_reduction_potential_t_co2', (select round((sum(package_co2_saving_kg * attribution) / 1000)::numeric, 1) from d),
    'loan_book_outstanding_cr', (select round((sum(loan_outstanding_inr) / 1e7)::numeric, 1) from d),
    'low_confidence_share', (select round(avg((confidence = 'low')::int)::numeric, 4) from d),
    'method', 'Financed emissions = home CO2 x outstanding / property value (PCAF-style attribution); CEA grid factor')
$$;

create or replace function public.portfolio_poor_homes(p_limit int default 50, p_city text default null, p_state text default null) returns jsonb
language sql stable set search_path = '' as $$
  select coalesce(jsonb_agg(x order by (x->>'score')::int), '[]') from (
    select jsonb_build_object('home_id', home_id, 'customer_id', customer_id, 'city', city, 'score', score, 'band', band,
           'key_issue', replace(weakest_component, '_', ' '), 'confidence', confidence, 'warnings', warnings) x
    from public.portfolio_frame where has_home_loan and band in ('Poor', 'Very poor')
      and (p_city is null or city = p_city) and (p_state is null or state = p_state)
    order by score limit p_limit) t
$$;

create or replace function public.portfolio_ranking(p_limit int default 50, p_city text default null, p_state text default null) returns jsonb
language sql stable set search_path = '' as $$
  select coalesce(jsonb_agg(x order by o), '[]') from (
    select row_number() over (order by improvement_potential_pct desc, package_co2_saving_kg desc) o,
           jsonb_build_object('home_id', home_id, 'customer_id', customer_id, 'city', city, 'score', score,
             'improvement_potential_pct', improvement_potential_pct, 'score_after_package', score_after_package,
             'package_saving_inr_year', package_saving_inr, 'co2_saving_t_year', round((package_co2_saving_kg / 1000)::numeric, 2),
             'financed_co2_reduction_t_year', round((package_co2_saving_kg * attribution / 1000)::numeric, 3), 'package', package_retrofits) x
    from public.portfolio_frame where has_home_loan and (p_city is null or city = p_city) and (p_state is null or state = p_state)
    order by improvement_potential_pct desc, package_co2_saving_kg desc limit p_limit) t
$$;

create or replace function public.portfolio_city_map() returns jsonb language sql stable set search_path = '' as $$
  select coalesce(jsonb_agg(x order by (x->>'financed_emissions_t')::numeric desc), '[]') from (
    select jsonb_build_object('city', d.city, 'state', c.state, 'lat', c.lat, 'lon', c.lon, 'zone', c.nbc_zone, 'homes', count(*),
           'mean_score', round(avg(d.score)::numeric, 1), 'poor_share', round(avg((d.band in ('Poor', 'Very poor'))::int)::numeric, 3),
           'financed_emissions_t', round((sum(d.baseline_co2_kg * d.attribution) / 1000)::numeric, 1),
           'reduction_potential_t', round((sum(d.package_co2_saving_kg * d.attribution) / 1000)::numeric, 1)) x
    from public.portfolio_frame d join public.cities c on c.city = d.city where d.has_home_loan group by d.city, c.state, c.lat, c.lon, c.nbc_zone) t
$$;

create or replace function public.portfolio_targets(p_limit int default 100, p_city text default null) returns jsonb
language sql stable set search_path = '' as $$
  select coalesce(jsonb_agg(x order by (x->>'package_saving_inr_year')::numeric desc), '[]') from (
    select jsonb_build_object('customer_id', customer_id, 'home_id', home_id, 'city', city, 'score', score,
           'offer', case when roof_access and pv_kw = 0 then 'Rooftop solar loan + efficiency top-up' else 'Efficiency top-up' end,
           'package_saving_inr_year', package_saving_inr, 'improvement_potential_pct', improvement_potential_pct,
           'credit_band', credit_band, 'language', preferred_language) x
    from public.portfolio_frame
    where has_home_loan and consent_marketing and tenure = 'owner' and credit_band in ('A', 'B') and improvement_potential_pct >= 40
      and (p_city is null or city = p_city)
    order by package_saving_inr desc limit p_limit) t
$$;

create or replace function public.portfolio_rwa_leads(p_min_homes int default 4, p_limit int default 50) returns jsonb
language sql stable set search_path = '' as $$
  select coalesce(jsonb_agg(x order by o), '[]') from (
    select row_number() over (order by count(*) desc, avg(score)) o,
           jsonb_build_object('society_id', society_id, 'city', city, 'customers', count(*), 'without_private_roof', count(*) filter (where not roof_access),
             'mean_score', round(avg(score)::numeric, 1), 'suggested_common_solar_kw', least(500, greatest(5, floor(count(*) * 1.5)))::int,
             'rwa_subsidy_inr', (least(500, greatest(5, floor(count(*) * 1.5))) * 18000)::int) x
    from public.portfolio_frame where dwelling_type = 'apartment' and society_id is not null
    group by society_id, city having count(*) >= p_min_homes order by count(*) desc, avg(score) limit p_limit) t
$$;

revoke all on function public.portfolio_summary(text, text), public.portfolio_poor_homes(int, text, text), public.portfolio_ranking(int, text, text),
  public.portfolio_city_map(), public.portfolio_targets(int, text), public.portfolio_rwa_leads(int, int) from public, anon, authenticated;
grant execute on function public.portfolio_summary(text, text), public.portfolio_poor_homes(int, text, text), public.portfolio_ranking(int, text, text),
  public.portfolio_city_map(), public.portfolio_targets(int, text), public.portfolio_rwa_leads(int, int) to service_role;
revoke all on public.portfolio_frame from anon;
