-- Real-data state profile and synthetic-vs-real calibration report.

-- One row per state: Census 2011 housing/assets/income, NFHS-5 energy-relevant indicators, WRI generation fleet.
create or replace view realdata.state_profile with (security_invoker = true) as
with census as (
  select state, sum(population) population, sum(households) households,
         round(100.0 * sum(urban_households) / nullif(sum(households), 0), 1) urban_hh_pct,
         round(100.0 * sum(hh_electric_lighting) / nullif(sum(households), 0), 1) electric_lighting_pct_2011,
         round(100.0 * sum(hh_lpg_png) / nullif(sum(households), 0), 1) lpg_png_pct_2011,
         round(100.0 * sum(hh_owned) / nullif(sum(hh_owned + hh_rented), 0), 1) owned_pct_2011,
         round(100.0 * sum(hh_dilapidated) / nullif(sum(households), 0), 1) dilapidated_pct_2011,
         round(100.0 * sum(hh_computer) / nullif(sum(households), 0), 1) computer_pct_2011,
         round(100.0 * sum(hh_car) / nullif(sum(households), 0), 1) car_pct_2011,
         round(100.0 * sum(hh_television) / nullif(sum(households), 0), 1) tv_pct_2011,
         round((sum(hh_size_1) * 1 + sum(hh_size_2) * 2 + sum(hh_size_3) * 3 + sum(hh_size_4) * 4 + sum(hh_size_5) * 5
                + sum(hh_size_6_8) * 6.8 + sum(hh_size_9_plus) * 10)::numeric
               / nullif(sum(hh_size_1 + hh_size_2 + hh_size_3 + hh_size_4 + hh_size_5 + hh_size_6_8 + hh_size_9_plus), 0), 2) mean_hh_size_2011,
         round(100.0 * sum(pp_330k_545k + pp_gt_545k) / nullif(sum(pp_total), 0), 1) hh_above_330k_pct_2011,
         round(100.0 * sum(pp_gt_545k) / nullif(sum(pp_total), 0), 1) hh_above_545k_pct_2011
  from realdata.census2011_district group by state),
nfhs as (
  select state,
         max(nfhs5_total) filter (where indicator_no = 7) electricity_pct,
         max(nfhs5_urban) filter (where indicator_no = 7) electricity_urban_pct,
         max(nfhs5_total) filter (where indicator_no = 10) clean_cooking_pct,
         max(nfhs5_urban) filter (where indicator_no = 10) clean_cooking_urban_pct,
         max(nfhs4_total) filter (where indicator_no = 10) clean_cooking_pct_nfhs4,
         max(nfhs5_urban) filter (where indicator_no = 9) improved_sanitation_urban_pct,
         max(nfhs5_total) filter (where indicator_no = 12) health_insurance_pct,
         max(nfhs5_urban) filter (where indicator_no = 18) women_internet_urban_pct,
         max(nfhs5_urban) filter (where indicator_no = 19) men_internet_urban_pct
  from realdata.nfhs5_state group by state),
fleet as (
  select nearest_state state, round(sum(capacity_mw)) capacity_mw_near,
         round(100 * sum(capacity_mw) filter (where primary_fuel = 'Coal') / nullif(sum(capacity_mw), 0), 1) coal_capacity_pct_near,
         round(100 * sum(capacity_mw) filter (where primary_fuel in ('Solar', 'Wind', 'Hydro', 'Biomass')) / nullif(sum(capacity_mw), 0), 1) renewable_capacity_pct_near,
         count(*) plants_near
  from realdata.power_plant where nearest_city_km <= 400 group by nearest_state)
select coalesce(c.state, n.state) state, c.population, c.households, c.urban_hh_pct, c.electric_lighting_pct_2011, c.lpg_png_pct_2011,
       c.owned_pct_2011, c.dilapidated_pct_2011, c.computer_pct_2011, c.car_pct_2011, c.tv_pct_2011, c.mean_hh_size_2011,
       c.hh_above_330k_pct_2011, c.hh_above_545k_pct_2011,
       n.electricity_pct, n.electricity_urban_pct, n.clean_cooking_pct, n.clean_cooking_urban_pct, n.clean_cooking_pct_nfhs4,
       n.improved_sanitation_urban_pct, n.health_insurance_pct, n.women_internet_urban_pct, n.men_internet_urban_pct,
       f.capacity_mw_near, f.coal_capacity_pct_near, f.renewable_capacity_pct_near, f.plants_near
from census c full join nfhs n on n.state = c.state left join fleet f on f.state = coalesce(c.state, n.state)
where coalesce(c.state, n.state) <> 'India';

-- Synthetic population vs real statistics, per engine state. The synthetic homes are urban, bank-customer
-- homes, so the right real comparator is the urban NFHS column where one exists; gaps are reported, not hidden.
create or replace view realdata.synth_vs_real_state with (security_invoker = true) as
with s as (
  select h.state, count(*) homes,
         round(100.0 * avg((h.cooking in ('lpg', 'png', 'induction'))::int), 1) synth_clean_cooking_pct,
         round(100.0 * avg((h.tenure = 'owner')::int), 1) synth_owned_pct,
         round(avg(h.occupants)::numeric, 2) synth_mean_occupants,
         round(100.0 * avg((h.income_band in ('upper_middle', 'high'))::int), 1) synth_upper_income_pct,
         round(avg((select sum(x) from unnest(h.kwh_24m[13:24]) x))::numeric, 0) synth_mean_annual_kwh
  from public.homes h group by h.state)
select s.state, s.homes,
       s.synth_clean_cooking_pct, p.clean_cooking_urban_pct real_clean_cooking_urban_pct,
       s.synth_owned_pct, p.owned_pct_2011 real_owned_pct_2011,
       s.synth_mean_occupants, p.mean_hh_size_2011 real_mean_hh_size_2011,
       s.synth_upper_income_pct, p.hh_above_330k_pct_2011 real_hh_above_330k_pct_2011,
       s.synth_mean_annual_kwh,
       round(s.synth_clean_cooking_pct - p.clean_cooking_urban_pct, 1) gap_clean_cooking_pp,
       round(s.synth_owned_pct - p.owned_pct_2011, 1) gap_owned_pp,
       round(s.synth_mean_occupants - p.mean_hh_size_2011, 2) gap_hh_size
from s left join realdata.state_profile p on p.state = s.state;

-- Engine reference climate vs real 2024-26 weather (Open-Meteo) and NASA climatology, per city.
create or replace view realdata.city_climate_check with (security_invoker = true) as
with w as (select city, round(sum(cdd24) / nullif(count(distinct month), 0) * 12, 0) real_cdd24_per_year,
                  sum(heatwave_days) / 2 real_heatwave_days_per_year, round(sum(ghi_kwh_m2) / 2, 0) real_ghi_kwh_m2_year
           from realdata.city_weather_monthly where month >= '2024-10-01' and month < '2026-10-01' group by city),
     n as (select city, max(value) filter (where parameter = 'ALLSKY_SFC_SW_DWN' and month = 13) * 365 nasa_ghi_kwh_m2_year,
                  max(value) filter (where parameter = 'T2M' and month = 13) nasa_t2m_annual_c
           from realdata.city_climatology group by city)
select c.city, c.state, c.nbc_zone, c.pv_yield_kwh_per_kwp engine_pv_yield,
       w.real_cdd24_per_year, w.real_heatwave_days_per_year, w.real_ghi_kwh_m2_year, round(n.nasa_ghi_kwh_m2_year, 0) nasa_ghi_kwh_m2_year,
       n.nasa_t2m_annual_c, round(n.nasa_ghi_kwh_m2_year * 0.77, 0) nasa_implied_pv_yield_kwh_per_kwp
from public.cities c left join w using (city) left join n using (city);

grant select on all tables in schema realdata to service_role;
