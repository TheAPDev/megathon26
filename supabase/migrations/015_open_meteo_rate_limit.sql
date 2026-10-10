-- Batched, resumable Open-Meteo loader (free tier: ~600 weighted calls/minute; one 2-year city request ~40).
-- Usage: select realdata.load_open_meteo('2024-10-01', '2026-09-30', 10);  -- repeat after a minute until 0
--        select realdata.load_nasa_power();  select realdata.load_worldbank();  (017)
create or replace function realdata.load_open_meteo(p_start date default '2024-10-01', p_end date default '2026-09-30', p_max_cities int default 8)
returns int language plpgsql set search_path = '' as $$
declare c record; j jsonb; n int := 0; k int; done int := 0;
begin
  for c in select ci.city, ci.lat, ci.lon from public.cities ci
           where (select count(*) from realdata.city_weather_daily w where w.city = ci.city) < (least(p_end, current_date - 6) - p_start + 1)
           order by ci.city loop
    exit when done >= p_max_cities;
    select content::jsonb into j from extensions.http_get(format(
      'https://archive-api.open-meteo.com/v1/archive?latitude=%s&longitude=%s&start_date=%s&end_date=%s&timezone=Asia%%2FKolkata'
      '&daily=temperature_2m_mean,temperature_2m_max,temperature_2m_min,apparent_temperature_max,relative_humidity_2m_mean,'
      'shortwave_radiation_sum,precipitation_sum,wind_speed_10m_max', c.lat, c.lon, p_start, least(p_end, current_date - 6)));
    if j ? 'error' then raise notice 'open-meteo: % (%), stopping', j->>'reason', c.city; exit; end if;
    insert into realdata.city_weather_daily
    select c.city, (d.v)::date,
           (j->'daily'->'temperature_2m_mean'->>(d.i - 1)::int)::numeric, (j->'daily'->'temperature_2m_max'->>(d.i - 1)::int)::numeric,
           (j->'daily'->'temperature_2m_min'->>(d.i - 1)::int)::numeric, (j->'daily'->'apparent_temperature_max'->>(d.i - 1)::int)::numeric,
           (j->'daily'->'relative_humidity_2m_mean'->>(d.i - 1)::int)::numeric, (j->'daily'->'shortwave_radiation_sum'->>(d.i - 1)::int)::numeric,
           (j->'daily'->'precipitation_sum'->>(d.i - 1)::int)::numeric, (j->'daily'->'wind_speed_10m_max'->>(d.i - 1)::int)::numeric
    from jsonb_array_elements_text(j->'daily'->'time') with ordinality d(v, i)
    on conflict (city, day) do nothing;
    get diagnostics k = row_count; n := n + k; done := done + 1;
    perform pg_sleep(2);
  end loop;
  update realdata.sources set rows_loaded = (select count(*) from realdata.city_weather_daily), fetched_at = now() where source_id = 'open_meteo_archive';
  return n;
end $$;
revoke all on function realdata.load_open_meteo(date, date, int) from public, anon, authenticated;
