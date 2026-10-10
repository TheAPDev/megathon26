-- Real public data layer (schema `realdata`, service-role only). The database fetches the raw public files itself
-- (pgsql-http), keeps them in realdata._raw for provenance, and parses them with an RFC-4180 CSV splitter.
create extension if not exists http with schema extensions;
create schema if not exists realdata;
revoke all on schema realdata from public, anon, authenticated;
grant usage on schema realdata to service_role;

create table if not exists realdata.sources (
  source_id text primary key, title text not null, publisher text not null, url text not null, licence text,
  reference_period text, fetched_at timestamptz default now(), bytes int, rows_loaded int);
create table if not exists realdata._raw (source_id text primary key references realdata.sources, body text not null);
alter table realdata.sources enable row level security;
alter table realdata._raw enable row level security;

create or replace function realdata.csv_fields(line text) returns text[] language sql immutable set search_path = '' as $$
  select coalesce(array_agg(case when f ~ '^".*"$' then replace(substr(f, 2, length(f) - 2), '""', '"') else f end order by ord), '{}')
  from regexp_matches(rtrim(line, E'\r'), '(?:^|,)("(?:[^"]|"")*"|[^,]*)', 'g') with ordinality as m(a, ord), lateral (select a[1] as f) x
$$;

create or replace function realdata.rows(p_source text, p_filter text default null) returns setof jsonb language plpgsql stable set search_path = '' as $$
declare hdr text[]; n int;
begin
  select realdata.csv_fields(split_part(body, E'\n', 1)) into hdr from realdata._raw where source_id = p_source;
  n := array_length(hdr, 1);
  return query
    select jsonb_object(hdr, (f || array_fill(null::text, array[greatest(0, n - coalesce(array_length(f, 1), 0))]))[1:n])
    from realdata._raw r, lateral unnest(string_to_array(r.body, E'\n')) with ordinality as l(line, i),
         lateral (select realdata.csv_fields(l.line) as f) x
    where r.source_id = p_source and l.i > 1 and length(trim(l.line)) > 0 and (p_filter is null or l.line like p_filter);
end $$;

create or replace function realdata.fetch(p_source text, p_url text) returns int language plpgsql set search_path = '' as $$
declare b text;
begin
  select content into b from extensions.http_get(p_url);
  insert into realdata._raw values (p_source, b) on conflict (source_id) do update set body = excluded.body;
  update realdata.sources set bytes = length(b), fetched_at = now() where source_id = p_source;
  return length(b);
end $$;
revoke all on function realdata.fetch(text, text), realdata.rows(text, text), realdata.csv_fields(text) from public, anon, authenticated;

insert into realdata.sources (source_id, title, publisher, url, licence, reference_period) values
 ('census2011_districts', 'Census of India 2011: district households, amenities and assets (640 districts)', 'Office of the Registrar General & Census Commissioner, India (via Kaggle/GitHub mirror)', 'https://raw.githubusercontent.com/nishusharma1608/India-Census-2011-Analysis/master/india-districts-census-2011.csv', 'Government Open Data', '2011'),
 ('nfhs5_states', 'National Family Health Survey 5: state fact sheets (131 indicators, urban/rural/total)', 'IIPS / Ministry of Health & Family Welfare (CSV by pratapvardhan/NFHS-5)', 'https://raw.githubusercontent.com/pratapvardhan/NFHS-5/master/NFHS-5-States.csv', 'CC BY 4.0', '2019-21'),
 ('nfhs5_districts', 'National Family Health Survey 5: district fact sheets (phase 1, 340 districts)', 'IIPS / MoHFW (CSV by pratapvardhan/NFHS-5)', 'https://raw.githubusercontent.com/pratapvardhan/NFHS-5/master/NFHS-5-Districts.csv', 'CC BY 4.0', '2019-20'),
 ('owid_energy', 'Our World in Data energy dataset (India series: generation mix, demand, carbon intensity)', 'Our World in Data (Energy Institute, Ember, EIA)', 'https://raw.githubusercontent.com/owid/energy-data/master/owid-energy-data.csv', 'CC BY 4.0', '1900-2025'),
 ('owid_co2', 'Our World in Data CO2 and GHG dataset (India series)', 'Our World in Data (Global Carbon Project)', 'https://raw.githubusercontent.com/owid/co2-data/master/owid-co2-data.csv', 'CC BY 4.0', '1850-2024'),
 ('wri_gppd', 'Global Power Plant Database (India plants with capacity, fuel, location, generation)', 'World Resources Institute', 'https://raw.githubusercontent.com/wri/global-power-plant-database/master/output_database/global_power_plant_database.csv', 'CC BY 4.0', '2013-2019 (v1.3)')
on conflict (source_id) do nothing;

-- Run once after applying (network fetch from the database):
--   select source_id, realdata.fetch(source_id, url) from realdata.sources where source_id in
--     ('census2011_districts','nfhs5_states','nfhs5_districts','owid_energy','owid_co2','wri_gppd');
