-- Real public datasets, parsed in-database from the raw CSVs fetched by 012_realdata_loader (realdata.fetch).
-- Every table keeps typed key columns plus the full source row in `attrs` (jsonb), so no source factor is lost.

create or replace function realdata.norm_state(s text) returns text language sql immutable set search_path = '' as $$
  select case
    when u in ('NCT OF DELHI', 'NCT DELHI', 'DELHI') then 'Delhi'
    when u in ('ORISSA', 'ODISHA') then 'Odisha'
    when u in ('PONDICHERRY', 'PUDUCHERRY') then 'Puducherry'
    when u like 'ANDAMAN%' then 'Andaman and Nicobar Islands'
    when u like 'DADRA%' or u like 'DAMAN%' then 'Dadra and Nagar Haveli and Daman and Diu'
    else replace(initcap(replace(u, '&', 'AND')), ' And ', ' and ') end
  from (select upper(trim(s)) as u) x
$$;

create or replace function realdata.num(t text) returns numeric language sql immutable set search_path = '' as $$
  select case when t ~ '^\s*-?[0-9]+(\.[0-9]+)?([eE][-+]?[0-9]+)?\s*$' then t::numeric end
$$;

-- 1. Census 2011 districts (640) -----------------------------------------------------------------------------
create table realdata.census2011_district as
select (j->>'District code')::int as district_code,
       case when upper(j->>'State name') = 'ANDHRA PRADESH' and upper(j->>'District name') in
            ('ADILABAD', 'NIZAMABAD', 'KARIMNAGAR', 'MEDAK', 'HYDERABAD', 'RANGAREDDY', 'MAHBUBNAGAR', 'NALGONDA', 'WARANGAL', 'KHAMMAM')
            then 'Telangana' else realdata.norm_state(j->>'State name') end as state,
       j->>'District name' as district,
       realdata.num(j->>'Population')::bigint as population,
       realdata.num(j->>'Households')::bigint as households,
       realdata.num(j->>'Urban_Households')::bigint as urban_households,
       realdata.num(j->>'Rural_Households')::bigint as rural_households,
       realdata.num(j->>'Housholds_with_Electric_Lighting')::bigint as hh_electric_lighting,
       realdata.num(j->>'LPG_or_PNG_Households')::bigint as hh_lpg_png,
       realdata.num(j->>'Ownership_Owned_Households')::bigint as hh_owned,
       realdata.num(j->>'Ownership_Rented_Households')::bigint as hh_rented,
       realdata.num(j->>'Condition_of_occupied_census_houses_Dilapidated_Households')::bigint as hh_dilapidated,
       realdata.num(j->>'Households_with_separate_kitchen_Cooking_inside_house')::bigint as hh_separate_kitchen,
       realdata.num(j->>'Households_with_Television')::bigint as hh_television,
       realdata.num(j->>'Households_with_Computer')::bigint as hh_computer,
       realdata.num(j->>'Households_with_Internet')::bigint as hh_internet,
       realdata.num(j->>'Households_with_Car_Jeep_Van')::bigint as hh_car,
       realdata.num(j->>'Households_with_Scooter_Motorcycle_Moped')::bigint as hh_two_wheeler,
       realdata.num(j->>'Household_size_1_person_Households')::bigint as hh_size_1,
       realdata.num(j->>'Household_size_2_persons_Households')::bigint as hh_size_2,
       realdata.num(j->>'Household_size_3_persons_Households')::bigint as hh_size_3,
       realdata.num(j->>'Household_size_4_persons_Households')::bigint as hh_size_4,
       realdata.num(j->>'Household_size_5_persons_Households')::bigint as hh_size_5,
       realdata.num(j->>'Household_size_6_8_persons_Households')::bigint as hh_size_6_8,
       realdata.num(j->>'Household_size_9_persons_and_above_Households')::bigint as hh_size_9_plus,
       realdata.num(j->>'Power_Parity_Less_than_Rs_45000')::bigint as pp_lt_45k,
       realdata.num(j->>'Power_Parity_Rs_45000_150000')::bigint as pp_45k_150k,
       realdata.num(j->>'Power_Parity_Rs_150000_330000')::bigint as pp_150k_330k,
       realdata.num(j->>'Power_Parity_Rs_330000_545000')::bigint as pp_330k_545k,
       realdata.num(j->>'Power_Parity_Above_Rs_545000')::bigint as pp_gt_545k,
       realdata.num(j->>'Total_Power_Parity')::bigint as pp_total,
       j - 'State name' - 'District name' as attrs
from realdata.rows('census2011_districts') j;
alter table realdata.census2011_district add primary key (district_code);

-- 2. NFHS-5 state fact sheets (37 states/UTs incl. India x 132 indicators) -----------------------------------
create table realdata.nfhs5_state as
select case when j->>'state' = 'India' then 'India' else realdata.norm_state(j->>'state') end as state,
       nullif(substring(j->>'indicator' from '^([0-9]+)\.'), '')::int as indicator_no,
       regexp_replace(j->>'indicator', '^[0-9]+\.\s*', '') as indicator,
       realdata.num(j->>'nfhs5_urban') as nfhs5_urban, realdata.num(j->>'nfhs5_rural') as nfhs5_rural,
       realdata.num(j->>'nfhs5_total') as nfhs5_total, realdata.num(j->>'nfhs4_total') as nfhs4_total
from realdata.rows('nfhs5_states') j;
create index on realdata.nfhs5_state (indicator_no, state);

-- 3. NFHS-5 districts (phase 1: 340 districts x 104 indicators) --------------------------------------------------
create table realdata.nfhs5_district as
select realdata.norm_state(j->>'State') as state, j->>'District' as district,
       nullif(substring(j->>'Indicator' from '^([0-9]+)\.'), '')::int as indicator_no,
       regexp_replace(j->>'Indicator', '^[0-9]+\.\s*', '') as indicator,
       realdata.num(j->>'NFHS-5') as nfhs5, realdata.num(j->>'NFHS-4') as nfhs4, nullif(j->>'NFHS-5-note', '') as nfhs5_note
from realdata.rows('nfhs5_districts') j;
create index on realdata.nfhs5_district (indicator_no, state, district);

-- 4. OWID energy: India yearly series --------------------------------------------------------------------------
create table realdata.owid_energy_india as
select (j->>'year')::int as year,
       realdata.num(j->>'population')::bigint as population,
       realdata.num(j->>'electricity_generation') as electricity_generation_twh,
       realdata.num(j->>'electricity_demand') as electricity_demand_twh,
       realdata.num(j->>'per_capita_electricity') as per_capita_electricity_kwh,
       realdata.num(j->>'carbon_intensity_elec') as carbon_intensity_g_per_kwh,
       realdata.num(j->>'coal_share_elec') as coal_share_elec_pct, realdata.num(j->>'gas_share_elec') as gas_share_elec_pct,
       realdata.num(j->>'hydro_share_elec') as hydro_share_elec_pct, realdata.num(j->>'nuclear_share_elec') as nuclear_share_elec_pct,
       realdata.num(j->>'solar_share_elec') as solar_share_elec_pct, realdata.num(j->>'wind_share_elec') as wind_share_elec_pct,
       realdata.num(j->>'renewables_share_elec') as renewables_share_elec_pct, realdata.num(j->>'low_carbon_share_elec') as low_carbon_share_elec_pct,
       realdata.num(j->>'solar_electricity') as solar_electricity_twh, realdata.num(j->>'wind_electricity') as wind_electricity_twh,
       realdata.num(j->>'coal_electricity') as coal_electricity_twh,
       realdata.num(j->>'energy_per_capita') as primary_energy_per_capita_kwh,
       realdata.num(j->>'greenhouse_gas_emissions') as power_sector_ghg_mt,
       (select jsonb_object_agg(k, v) from jsonb_each_text(j) e(k, v) where v <> '' and k not in ('country', 'iso_code')) as attrs
from realdata.rows('owid_energy', 'India,%') j;
alter table realdata.owid_energy_india add primary key (year);

-- 5. OWID CO2/GHG: India yearly series -------------------------------------------------------------------------
create table realdata.owid_co2_india as
select (j->>'year')::int as year,
       realdata.num(j->>'co2') as co2_mt, realdata.num(j->>'co2_per_capita') as co2_per_capita_t,
       realdata.num(j->>'coal_co2') as coal_co2_mt, realdata.num(j->>'oil_co2') as oil_co2_mt, realdata.num(j->>'gas_co2') as gas_co2_mt,
       realdata.num(j->>'total_ghg') as total_ghg_mt, realdata.num(j->>'ghg_per_capita') as ghg_per_capita_t,
       realdata.num(j->>'share_global_co2') as share_global_co2_pct,
       realdata.num(j->>'temperature_change_from_ghg') as temperature_change_from_ghg_c,
       (select jsonb_object_agg(k, v) from jsonb_each_text(j) e(k, v) where v <> '' and k not in ('country', 'iso_code')) as attrs
from realdata.rows('owid_co2', 'India,%') j;
alter table realdata.owid_co2_india add primary key (year);

-- 6. WRI Global Power Plant Database: India (1,589 plants) -----------------------------------------------------
create table realdata.power_plant as
select j->>'gppd_idnr' as plant_id, j->>'name' as name, realdata.num(j->>'capacity_mw') as capacity_mw,
       realdata.num(j->>'latitude') as lat, realdata.num(j->>'longitude') as lon, j->>'primary_fuel' as primary_fuel,
       nullif(j->>'other_fuel1', '') as other_fuel, floor(realdata.num(j->>'commissioning_year'))::int as commissioning_year,
       nullif(j->>'owner', '') as owner, nullif(j->>'source', '') as data_source,
       realdata.num(j->>'generation_gwh_2017') as generation_gwh_2017, realdata.num(j->>'generation_gwh_2018') as generation_gwh_2018,
       realdata.num(j->>'generation_gwh_2019') as generation_gwh_2019,
       realdata.num(j->>'estimated_generation_gwh_2017') as estimated_generation_gwh_2017,
       null::text as nearest_city, null::text as nearest_state, null::numeric as nearest_city_km
from realdata.rows('wri_gppd', 'IND,%') j;
alter table realdata.power_plant add primary key (plant_id);
update realdata.power_plant p set (nearest_city, nearest_state, nearest_city_km) =
  (select c.city, c.state, round((6371 * 2 * asin(sqrt(power(sin(radians(c.lat - p.lat) / 2), 2)
          + cos(radians(p.lat)) * cos(radians(c.lat)) * power(sin(radians(c.lon - p.lon) / 2), 2))))::numeric, 1)
   from public.cities c order by 3 limit 1)
where p.lat is not null;

update realdata.sources s set rows_loaded = x.n from (values
  ('census2011_districts', (select count(*) from realdata.census2011_district)),
  ('nfhs5_states', (select count(*) from realdata.nfhs5_state)),
  ('nfhs5_districts', (select count(*) from realdata.nfhs5_district)),
  ('owid_energy', (select count(*) from realdata.owid_energy_india)),
  ('owid_co2', (select count(*) from realdata.owid_co2_india)),
  ('wri_gppd', (select count(*) from realdata.power_plant))) x(id, n) where s.source_id = x.id;

alter table realdata.census2011_district enable row level security;
alter table realdata.nfhs5_state enable row level security;
alter table realdata.nfhs5_district enable row level security;
alter table realdata.owid_energy_india enable row level security;
alter table realdata.owid_co2_india enable row level security;
alter table realdata.power_plant enable row level security;
grant select on all tables in schema realdata to service_role;
