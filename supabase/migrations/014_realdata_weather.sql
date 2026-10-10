-- Real weather and solar resource for every engine city, pulled by the database itself:
--   * Open-Meteo historical archive (ERA5 reanalysis): daily weather for the exact 24-month billing window
--     of the dataset (Oct 2024 - Sep 2026) -> real cooling degree-days and heatwave days per city-month.
--   * NASA POWER climatology (2001-2020 averages): monthly irradiance, temperature, humidity, wind, CDD.
insert into realdata.sources (source_id, title, publisher, url, licence, reference_period) values
 ('open_meteo_archive', 'Open-Meteo historical weather API (ERA5 / ERA5-Land reanalysis), daily, 43 cities', 'Open-Meteo / ECMWF Copernicus',
  'https://archive-api.open-meteo.com/v1/archive', 'CC BY 4.0', '2024-10-01 to 2026-09-30'),
 ('nasa_power', 'NASA POWER monthly climatology (solar resource and meteorology), 43 cities', 'NASA Langley Research Center POWER project',
  'https://power.larc.nasa.gov/api/temporal/climatology/point', 'Public domain (NASA)', '2001-2020 climatology')
on conflict (source_id) do nothing;

create table if not exists realdata.city_weather_daily (
  city text not null references public.cities(city), day date not null,
  t_mean_c numeric, t_max_c numeric, t_min_c numeric, apparent_t_max_c numeric, rh_mean_pct numeric,
  shortwave_mj_m2 numeric, precipitation_mm numeric, wind_max_kmh numeric,
  primary key (city, day));

create table if not exists realdata.city_climatology (
  city text not null references public.cities(city), parameter text not null, month int not null check (month between 1 and 13),
  value numeric, unit text, primary key (city, parameter, month));
alter table realdata.city_weather_daily enable row level security;
alter table realdata.city_climatology enable row level security;

create or replace function realdata.load_open_meteo(p_start date default '2024-10-01', p_end date default '2026-09-30')
returns int language plpgsql set search_path = '' as $$
declare c record; j jsonb; n int := 0; k int;
begin
  for c in select city, lat, lon from public.cities order by city loop
    select content::jsonb into j from extensions.http_get(format(
      'https://archive-api.open-meteo.com/v1/archive?latitude=%s&longitude=%s&start_date=%s&end_date=%s&timezone=Asia%%2FKolkata'
      '&daily=temperature_2m_mean,temperature_2m_max,temperature_2m_min,apparent_temperature_max,relative_humidity_2m_mean,'
      'shortwave_radiation_sum,precipitation_sum,wind_speed_10m_max', c.lat, c.lon, p_start, least(p_end, current_date - 6)));
    insert into realdata.city_weather_daily
    select c.city, (d.v)::date,
           (j->'daily'->'temperature_2m_mean'->>(d.i - 1)::int)::numeric, (j->'daily'->'temperature_2m_max'->>(d.i - 1)::int)::numeric,
           (j->'daily'->'temperature_2m_min'->>(d.i - 1)::int)::numeric, (j->'daily'->'apparent_temperature_max'->>(d.i - 1)::int)::numeric,
           (j->'daily'->'relative_humidity_2m_mean'->>(d.i - 1)::int)::numeric, (j->'daily'->'shortwave_radiation_sum'->>(d.i - 1)::int)::numeric,
           (j->'daily'->'precipitation_sum'->>(d.i - 1)::int)::numeric, (j->'daily'->'wind_speed_10m_max'->>(d.i - 1)::int)::numeric
    from jsonb_array_elements_text(j->'daily'->'time') with ordinality d(v, i)
    on conflict (city, day) do update set t_mean_c = excluded.t_mean_c, t_max_c = excluded.t_max_c, t_min_c = excluded.t_min_c,
      apparent_t_max_c = excluded.apparent_t_max_c, rh_mean_pct = excluded.rh_mean_pct, shortwave_mj_m2 = excluded.shortwave_mj_m2,
      precipitation_mm = excluded.precipitation_mm, wind_max_kmh = excluded.wind_max_kmh;
    get diagnostics k = row_count; n := n + k;
  end loop;
  update realdata.sources set rows_loaded = (select count(*) from realdata.city_weather_daily), fetched_at = now() where source_id = 'open_meteo_archive';
  return n;
end $$;

create or replace function realdata.load_nasa_power() returns int language plpgsql set search_path = '' as $$
declare c record; j jsonb; n int := 0; k int;
begin
  for c in select city, lat, lon from public.cities order by city loop
    select content::jsonb into j from extensions.http_get(format(
      'https://power.larc.nasa.gov/api/temporal/climatology/point?community=RE&format=JSON&longitude=%s&latitude=%s&parameters='
      'ALLSKY_SFC_SW_DWN,CLRSKY_SFC_SW_DWN,ALLSKY_KT,T2M,T2M_MAX,T2M_MIN,RH2M,WS2M,PRECTOTCORR,CDD18_3', c.lon, c.lat));
    insert into realdata.city_climatology
    select c.city, p.key, array_position(array['JAN','FEB','MAR','APR','MAY','JUN','JUL','AUG','SEP','OCT','NOV','DEC','ANN'], m.key),
           nullif(m.value::numeric, -999), j->'parameters'->p.key->>'units'
    from jsonb_each(j->'properties'->'parameter') p, jsonb_each_text(p.value) m
    on conflict (city, parameter, month) do update set value = excluded.value, unit = excluded.unit;
    get diagnostics k = row_count; n := n + k;
  end loop;
  update realdata.sources set rows_loaded = (select count(*) from realdata.city_climatology), fetched_at = now() where source_id = 'nasa_power';
  return n;
end $$;
revoke all on function realdata.load_open_meteo(date, date), realdata.load_nasa_power() from public, anon, authenticated;

-- Monthly real-weather aggregates the engine can use: CDD (base 24 C, as in the engine), heatwave days
-- (IMD plains criterion: Tmax >= 40 C), humid-heat days and solar resource.
create or replace view realdata.city_weather_monthly with (security_invoker = true) as
select city, date_trunc('month', day)::date as month, count(*) as days,
       round(avg(t_mean_c), 2) as t_mean_c, max(t_max_c) as t_max_c, min(t_min_c) as t_min_c,
       round(sum(greatest(t_mean_c - 24, 0)), 1) as cdd24, round(sum(greatest(t_mean_c - 18, 0)), 1) as cdd18,
       count(*) filter (where t_max_c >= 40) as heatwave_days, count(*) filter (where apparent_t_max_c >= 41) as humid_heat_days,
       round(avg(rh_mean_pct), 1) as rh_mean_pct, round(sum(shortwave_mj_m2) / 3.6, 1) as ghi_kwh_m2, round(sum(precipitation_mm), 1) as rain_mm
from realdata.city_weather_daily group by city, date_trunc('month', day);
