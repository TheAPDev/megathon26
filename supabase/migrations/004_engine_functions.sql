-- SQL port of the Python engine's modelled energy and Green Ghar Score (greenghar/engine/physics.py, score.py).
-- Same constants and formulas; parity is checked by scripts/check_sql_parity.py (Python vs SQL on sample homes).
-- The Python engine remains the source of truth for plans, scenarios and finance; SQL scoring lets analysts and
-- the in-database generator score 50k homes without leaving Postgres.

create type gg.energy_t as (
  monthly_import real[], monthly_demand real[], total_demand real, cooling real, plug real,
  water real, lpg_kwh real, pv_gen real
);

create or replace function gg.iseer(h public.homes) returns real language sql stable set search_path = '' as $$
  select (case when h.ac_star in (1,3,5)
            then (select value from public.appliances where appliance = 'ac' and variant = h.ac_tech || '_' || h.ac_star || 'star')
            else ((select value from public.appliances where appliance = 'ac' and variant = h.ac_tech || '_' || (h.ac_star - 1) || 'star')
                + (select value from public.appliances where appliance = 'ac' and variant = h.ac_tech || '_' || (h.ac_star + 1) || 'star')) / 2
          end) * greatest(0.6, 1 - 0.01 * h.ac_age_years)
$$;

-- truth multipliers: behaviour, humid, leak, income, wfh_plug, wfh_cool, tenant_cool; year_factor scales cooling
create or replace function gg.energy(h public.homes, truth real[] default null, year_factor real default 1)
returns gg.energy_t language plpgsql stable set search_path = '' as $$
declare
  c record; zone text; area real := coalesce(h.carpet_area_m2, 90);
  days int[] := array[31,28,31,30,31,30,31,31,30,31,30,31];
  pv_shape real[] := array[0.080,0.084,0.096,0.097,0.097,0.080,0.068,0.070,0.078,0.086,0.082,0.082];
  iseer real := 1; env real := 1; roof real; glass real; shade real; sp real; smart real;
  cap real := h.ac_tonnage * 3.517; fridge_annual real; fan_w real; light_w real; water_annual real := 0; zf real;
  ww real := 0; plug_annual real; lpg real := 0; cook_el real := 0; outage real; loss_rate real := 0; standby real := 0;
  t real; d int; cdd real; ac_h real; cool real; fans real; fridge real; light real; water real; plug real; cook real; loss real;
  dem real; gen real; daytime real; m int;
  b real := 1; hum real := 1; leak real := 1; inc real := 1; wplug real := 1; wcool real := 1; tcool real := 1;
  r gg.energy_t;
begin
  select * into c from public.cities where city = h.city;
  zone := c.nbc_zone;
  if truth is not null then
    b := truth[1]; hum := truth[2]; leak := truth[3]; inc := truth[4]; wplug := truth[5]; wcool := truth[6]; tcool := truth[7];
  end if;
  if h.n_ac > 0 then iseer := gg.iseer(h); end if;
  if h.floor_position = 'top' or h.dwelling_type <> 'apartment' then
    roof := 1.25;
    if h.cool_roof then roof := roof * (1 - 0.15); end if;
    if h.roof_insulation then roof := roof * (1 - 0.20); end if;
    env := env * roof;
  end if;
  env := env * case h.wall_type when 'solid_brick' then 1.05 when 'hollow_block' then 1.0 else 0.94 end;
  glass := 1 + 0.35 * greatest(0, h.window_to_wall - 0.15);
  if h.west_glass then glass := glass * 1.08; end if;
  shade := case h.shading when 'none' then 1 when 'partial' then 0.96 else 0.92 end;
  if h.solar_film then shade := shade * 0.95; end if;
  env := env * glass * shade;
  sp := greatest(0.5, 1 - 0.06 * (h.ac_setpoint_c - 24));
  smart := case when h.smart_plugs then 0.95 else 1 end;
  fridge_annual := (array[400,330,270,220,180])[h.fridge_star] * (1 + 0.02 * h.fridge_age_years);
  fan_w := h.n_fans * (h.bldc_fan_share * 30 + (1 - h.bldc_fan_share) * 75);
  light_w := h.light_points * (h.led_share * 9 + (1 - h.led_share) * 25);
  zf := case zone when 'cold' then 1.6 when 'composite' then 1.0 when 'temperate' then 0.6 when 'hot_dry' then 0.6 else 0.3 end;
  water_annual := case h.water_heating when 'electric_geyser' then 180 * h.occupants * zf
                                       when 'heat_pump' then 180 * h.occupants * zf * 0.35
                                       when 'solar' then 180 * h.occupants * zf * 0.30 else 0 end;
  for m in 1..12 loop ww := ww + greatest(0.5, 26 - c.temps[m]); end loop;
  plug_annual := 250 + 80 * h.occupants + 1.0 * area;
  if h.cooking = 'lpg' then lpg := coalesce(h.lpg_cylinders_per_year, 2 + 1.75 * h.occupants) * 14.2 * 13.6;
  elsif h.cooking = 'induction' then cook_el := (2 + 1.75 * h.occupants) * 14.2 * 13.6 * 0.40 / 0.84; end if;
  outage := h.outage_hours_month * 0.6;
  if h.backup = 'lead_acid' then loss_rate := 1/0.70 - 1; standby := 150;
  elsif h.backup = 'lithium' then loss_rate := 1/0.92 - 1; standby := 40; end if;
  daytime := 0.35 + case when h.wfh then 0.15 else 0 end;
  r.monthly_import := array[]::real[]; r.monthly_demand := array[]::real[];
  r.total_demand := 0; r.cooling := 0; r.plug := 0; r.water := 0; r.pv_gen := 0; r.lpg_kwh := lpg;
  for m in 1..12 loop
    t := c.temps[m]; d := days[m];
    cdd := greatest(0, t - 24) * d;
    ac_h := least(16 * d, 1.0 * cdd * env * sp);
    cool := h.n_ac * ac_h * cap * 0.5 / iseer * smart * hum * leak * wcool * tcool * year_factor;
    fans := fan_w * 0.6 * least(14, greatest(0, 3 + 0.8 * (t - 20))) * d / 1000
            + case when zone in ('hot_dry','composite') then h.n_coolers * 200 * least(12, greatest(0, t - 26)) * d / 1000 else 0 end;
    fridge := fridge_annual / 12 * (1 + 0.012 * (t - 25));
    light := light_w * 5 * d / 1000;
    water := water_annual * greatest(0.5, 26 - t) / ww;
    plug := plug_annual / 12 * inc * wplug;
    cook := cook_el / 12;
    loss := case when h.backup in ('lead_acid','lithium') then outage * loss_rate + standby / 12 else 0 end;
    dem := (cool + fans + fridge + light + water + plug + cook + loss) * b;
    gen := h.pv_kw * c.pv_yield_kwh_per_kwp * pv_shape[m];
    r.monthly_demand := r.monthly_demand || dem;
    r.monthly_import := r.monthly_import || greatest(0, dem - least(gen, dem * daytime));
    r.total_demand := r.total_demand + dem; r.cooling := r.cooling + cool; r.plug := r.plug + plug;
    r.water := r.water + water; r.pv_gen := r.pv_gen + gen;
  end loop;
  return r;
end $$;

-- Calendar-ordered (Jan..Dec) last 12 readings from kwh_24m (month 0 = Oct 2024)
create or replace function gg.last12(k real[]) returns real[] language sql immutable set search_path = '' as $$
  select array_agg(k[13 + ((m + 2) % 12)] order by m) from generate_series(1, 12) m
$$;

create or replace function gg.score(h public.homes)
returns table (score smallint, raw_score real, band text, confidence text, annual_grid_kwh real, annual_estimated boolean,
               intensity_kwh_m2 real, s_energy_efficiency real, s_consumption_intensity real, s_envelope real, s_cooling_system real,
               s_windows_shading real, s_renewables real, s_smart_use real, weakest_component text, warnings jsonb)
language plpgsql stable set search_path = '' as $$
declare
  e gg.energy_t; e0 gg.energy_t; ews gg.energy_t; bench real; area real; area_est boolean := h.carpet_area_m2 is null;
  obs real[]; shape real[]; tot real := 0; med real; implied real[] := array[]::real[]; n_obs int := 0; obs_sum real := 0; shape_sum real := 0;
  annual real; est boolean; r real; ee real; it real; env real; cool real; win real; ren real; sm real; iseer real; m int;
  wall real; roofp real; swh real := 0; w jsonb := '[]'::jsonb; raw real; hx public.homes;
begin
  e := gg.energy(h);
  hx := h; hx.pv_kw := 0;
  e0 := gg.energy(hx);
  select median_kwh_m2 into bench from public.benchmarks where zone = h.zone;
  bench := bench * case when h.dwelling_type <> 'apartment' then 1.1 else 1 end;
  area := coalesce(h.carpet_area_m2, case h.dwelling_type when 'apartment' then 85 when 'independent_house' then 140 else 110 end);
  -- consumption profile: drop reading errors (>4x or <1/4 of the median implied annual), annualise with seasonal shape
  for m in 1..12 loop tot := tot + e.monthly_import[m]; end loop;
  shape := array(select x / nullif(tot, 0) from unnest(e.monthly_import) x);
  obs := case when h.kwh_24m is null then null else gg.last12(h.kwh_24m) end;
  if obs is not null then
    implied := array(select obs[i] / shape[i] from generate_series(1,12) i where obs[i] is not null and shape[i] > 0 order by 1);
    if coalesce(array_length(implied, 1), 0) >= 4 then
      med := implied[array_length(implied, 1) / 2 + 1];
      for m in 1..12 loop
        if obs[m] is not null and shape[m] > 0 and (obs[m] / shape[m] > med * 4 or obs[m] / shape[m] < med / 4) then obs[m] := null; end if;
      end loop;
    end if;
    for m in 1..12 loop
      if obs[m] is not null then n_obs := n_obs + 1; obs_sum := obs_sum + obs[m]; shape_sum := shape_sum + shape[m]; end if;
    end loop;
  end if;
  if n_obs = 12 then annual := obs_sum; est := false;
  elsif n_obs >= 6 then annual := obs_sum / shape_sum; est := true;
  else annual := tot; est := true; end if;  -- Python uses the ML predictor here when loaded; SQL uses physics
  -- sub-scores (mirrors score.py)
  if h.bee_star_label is not null then ee := 20 * h.bee_star_label;
  else ee := greatest(0, least(100, 100 * (1.6 - (e0.total_demand + e0.lpg_kwh) / area / bench) / 1.1)); end if;
  r := (annual + e.lpg_kwh) / area / bench;
  it := greatest(0, least(100, 100 * (2.0 - r) / 1.5));
  wall := case h.wall_type when 'solid_brick' then 0 when 'hollow_block' then 50 else 100 end;
  if h.floor_position = 'top' or h.dwelling_type <> 'apartment' then
    roofp := case when h.roof_insulation then 55 else 0 end + case when h.cool_roof then 45 else 0 end;
    env := 0.55 * roofp + 0.45 * wall;
  else env := wall; end if;
  if h.n_ac = 0 then cool := 0.7 * 85 + 0.3 * 100 * h.bldc_fan_share;
  else
    iseer := gg.iseer(h);
    cool := 0.7 * greatest(0, least(100, 100 * (iseer - 2.6) / 3.2)) * (0.85 + 0.15 * greatest(0, least(100, (h.ac_setpoint_c - 20) / 4 * 100)) / 100)
            + 0.3 * 100 * h.bldc_fan_share;
  end if;
  win := greatest(0, least(100, 100 - 120 * greatest(0, h.window_to_wall - 0.15)))
         * case h.shading when 'none' then 0.7 when 'partial' then 0.85 else 1 end
         * case when h.west_glass and not h.solar_film and h.shading <> 'full' then 0.85 else 1 end
         * case when h.solar_film then 1.05 else 1 end;
  win := least(100, win);
  if h.water_heating = 'solar' then
    hx := h; hx.water_heating := 'electric_geyser';
    ews := gg.energy(hx);
    swh := ews.water - e.water;
  end if;
  ren := least(100, 200 * (e.pv_gen + swh) / nullif(e.total_demand + e.lpg_kwh + swh, 0));
  sm := 30 * h.smart_meter::int + 20 * h.tod_tariff::int + 25 * h.smart_plugs::int
        + case when h.n_ac = 0 or h.ac_setpoint_c >= 24 then 25 else 25 * greatest(0, least(1, (h.ac_setpoint_c - 18) / 6)) end;
  raw := 0.25 * ee + 0.20 * it + 0.15 * env + 0.15 * cool + 0.10 * win + 0.10 * coalesce(ren, 0) + 0.05 * sm;
  if h.bee_star_label >= 4 and r > 1.5 then w := w || to_jsonb('Data conflict: BEE label says ' || h.bee_star_label || ' star but metered use is ' || round(r::numeric, 1) || 'x the benchmark.'); end if;
  if h.bee_star_label <= 2 and r < 0.6 then w := w || to_jsonb('Data conflict: BEE label says ' || h.bee_star_label || ' star but metered use is only ' || round(r::numeric, 1) || 'x the benchmark.'); end if;
  score := round(raw)::smallint; raw_score := raw;
  band := case when raw >= 79.5 then 'Highly efficient' when raw >= 64.5 then 'Good' when raw >= 49.5 then 'Moderate' when raw >= 29.5 then 'Poor' else 'Very poor' end;
  confidence := case when h.data_source = 'smart_meter' and n_obs = 12 and not area_est and jsonb_array_length(w) = 0 then 'high'
                     when n_obs >= 6 and not (area_est and n_obs < 12) then 'medium' else 'low' end;
  annual_grid_kwh := annual; annual_estimated := est; intensity_kwh_m2 := (annual + e.lpg_kwh) / area;
  s_energy_efficiency := ee; s_consumption_intensity := it; s_envelope := env; s_cooling_system := cool;
  s_windows_shading := win; s_renewables := coalesce(ren, 0); s_smart_use := sm; warnings := w;
  select k into weakest_component from (values ('energy_efficiency', ee), ('consumption_intensity', it), ('envelope', env),
       ('cooling_system', cool), ('windows_shading', win), ('renewables', coalesce(ren,0)), ('smart_use', sm)) v(k, s) order by s limit 1;
  return next;
end $$;

create or replace function gg.rescore(p_limit int default 5000) returns int language plpgsql set search_path = '' as $$
declare n int;
begin
  insert into public.home_scores (home_id, score, raw_score, band, confidence, annual_grid_kwh, annual_estimated, intensity_kwh_m2,
        s_energy_efficiency, s_consumption_intensity, s_envelope, s_cooling_system, s_windows_shading, s_renewables, s_smart_use,
        weakest_component, warnings, engine, engine_version)
  select h.home_id, s.*, 'sql', 'gg.score v1'
  from (select * from public.homes h0 where not exists (select 1 from public.home_scores x where x.home_id = h0.home_id) limit p_limit) h
  cross join lateral gg.score(h) s
  on conflict (home_id) do nothing;
  get diagnostics n = row_count;
  return n;
end $$;
