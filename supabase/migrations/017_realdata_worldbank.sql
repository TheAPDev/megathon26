-- World Bank WDI: India national indicators relevant to household energy, finance and urbanisation (1960-latest).
insert into realdata.sources (source_id, title, publisher, url, licence, reference_period) values
 ('worldbank_wdi', 'World Development Indicators: India (electricity access/use, clean cooking, losses, renewables, urbanisation, income, lending rate, PM2.5)',
  'World Bank', 'https://api.worldbank.org/v2/country/IND/indicator', 'CC BY 4.0', '1960-latest')
on conflict (source_id) do nothing;

create table if not exists realdata.wb_indicator (
  indicator_id text not null, indicator text, year int not null, value numeric, primary key (indicator_id, year));
alter table realdata.wb_indicator enable row level security;

create or replace function realdata.load_worldbank() returns int language plpgsql set search_path = '' as $$
declare ind text; j jsonb; n int := 0; k int;
begin
  foreach ind in array array[
    'EG.ELC.ACCS.ZS', 'EG.ELC.ACCS.UR.ZS', 'EG.ELC.ACCS.RU.ZS', 'EG.USE.ELEC.KH.PC', 'EG.CFT.ACCS.ZS', 'EG.CFT.ACCS.UR.ZS',
    'EG.ELC.LOSS.ZS', 'EG.ELC.COAL.ZS', 'EG.ELC.RNEW.ZS', 'EG.FEC.RNEW.ZS', 'EG.EGY.PRIM.PP.KD', 'EG.USE.PCAP.KG.OE',
    'SP.POP.TOTL', 'SP.URB.TOTL.IN.ZS', 'SP.URB.GROW', 'EN.POP.SLUM.UR.ZS', 'NY.GDP.PCAP.CD', 'NY.GDP.PCAP.PP.CD',
    'FP.CPI.TOTL.ZG', 'FR.INR.LEND', 'EN.ATM.PM25.MC.M3', 'EN.GHG.CO2.PC.CE.AR5', 'EN.GHG.ALL.PC.CE.AR5', 'AG.LND.PRCP.MM']
  loop
    perform extensions.http_set_curlopt('CURLOPT_TIMEOUT_MS', '30000');
    begin
      select content::jsonb into j from extensions.http_get(
        format('https://api.worldbank.org/v2/country/IND/indicator/%s?format=json&per_page=100', ind));
    exception when others then raise notice 'world bank % failed: %', ind, sqlerrm; continue;
    end;
    if jsonb_typeof(j) <> 'array' or jsonb_array_length(j) < 2 or jsonb_typeof(j->1) <> 'array' then continue; end if;
    insert into realdata.wb_indicator
    select ind, e->'indicator'->>'value', (e->>'date')::int, (e->>'value')::numeric
    from jsonb_array_elements(j->1) e where e->>'value' is not null
    on conflict (indicator_id, year) do update set value = excluded.value, indicator = excluded.indicator;
    get diagnostics k = row_count; n := n + k;
  end loop;
  update realdata.sources set rows_loaded = (select count(*) from realdata.wb_indicator), fetched_at = now() where source_id = 'worldbank_wdi';
  return n;
end $$;
revoke all on function realdata.load_worldbank() from public, anon, authenticated;
grant select on all tables in schema realdata to service_role;
