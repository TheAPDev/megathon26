-- SQL port of the full-package scenario (greenghar/engine/plan.run_scenario over every feasible retrofit) so the
-- in-database population gets improvement potential, package savings and CO2 without leaving Postgres.
-- Mirrors: retrofits.feasibility (hard rules + zone table), already_done, apply, solar.recommend_kw,
-- consumption.profile (metered/annualised), tariff.annual_bill (slabs, free units, Delhi rule, net metering).
-- Parity with Python is tested in tests/test_sql_parity.py.

create or replace function gg.zone_suit(h public.homes, rid text) returns text language sql stable set search_path = '' as $$
  select suitability from public.zone_suitability where retrofit_id = rid and zone = h.zone
$$;

create or replace function gg.roof_area(h public.homes) returns real language sql immutable set search_path = '' as $$
  select coalesce(h.roof_area_m2, case when h.dwelling_type <> 'apartment' then coalesce(h.carpet_area_m2, 90) * 0.9 else 0 end)
$$;

create or replace function gg.max_pv_kw(h public.homes) returns real language sql immutable set search_path = '' as $$
  select case when not h.roof_access then 0
              else greatest(0, least(gg.roof_area(h) / 10, greatest(h.sanctioned_load_kw * 1.5, 3), 10)) end
$$;

create or replace function gg.already_done(h public.homes, rid text) returns boolean language sql stable set search_path = '' as $$
  select case rid
    when 'cool_roof' then h.cool_roof
    when 'roof_insulation' then h.roof_insulation
    when 'external_shading' then h.shading = 'full'
    when 'solar_film' then h.solar_film
    when 'ac_setpoint' then h.n_ac > 0 and h.ac_setpoint_c >= 24
    when 'smart_plug_tod' then h.smart_plugs
    when 'ac_5star_inverter' then h.n_ac > 0 and h.ac_tech = 'inverter' and h.ac_star = 5 and h.ac_age_years < 3
    when 'bldc_fans' then h.bldc_fan_share >= 0.99
    when 'led_lighting' then h.led_share >= 0.99
    when 'fridge_5star' then h.fridge_star = 5 and h.fridge_age_years < 5
    when 'solar_water_heater' then h.water_heating = 'solar'
    when 'heat_pump_geyser' then h.water_heating = 'heat_pump'
    when 'induction_cooking' then h.cooking = 'induction'
    when 'lithium_battery' then h.backup = 'lithium'
    when 'rooftop_solar' then h.pv_kw > 0 and h.pv_kw >= gg.max_pv_kw(h) * 0.8
    else false end
$$;

-- Suitability: 'Infeasible' | 'Low' | 'Medium' | 'High' (mirrors retrofits.feasibility)
create or replace function gg.feasibility(h public.homes, rid text) returns text language plpgsql stable set search_path = '' as $$
declare exposed boolean := h.floor_position = 'top' or h.dwelling_type <> 'apartment'; zs text := gg.zone_suit(h, rid);
begin
  if rid in ('cool_roof', 'roof_insulation') then
    if not exposed then return 'Infeasible'; end if;
    if h.tenure = 'tenant' and rid = 'roof_insulation' then return 'Low'; end if;
  end if;
  if rid in ('external_shading', 'solar_film') and h.window_to_wall <= 0.12 and not h.west_glass then return 'Low'; end if;
  if rid in ('ac_setpoint', 'ac_5star_inverter', 'smart_plug_tod') and h.n_ac = 0 then return 'Infeasible'; end if;
  if rid = 'ac_5star_inverter' and h.ac_tech = 'inverter' and h.ac_star >= 4 and h.ac_age_years < 4 then return 'Low'; end if;
  if rid = 'bldc_fans' and h.n_fans = 0 then return 'Infeasible'; end if;
  if rid = 'fridge_5star' and h.fridge_star >= 4 and h.fridge_age_years < 6 then return 'Low'; end if;
  if rid in ('solar_water_heater', 'heat_pump_geyser') and h.water_heating <> 'electric_geyser' then return 'Infeasible'; end if;
  if rid = 'solar_water_heater' and not h.roof_access then return 'Infeasible'; end if;
  if rid = 'induction_cooking' and h.cooking <> 'lpg' then return 'Infeasible'; end if;
  if rid = 'lithium_battery' and h.backup <> 'lead_acid' then return 'Infeasible'; end if;
  if rid = 'rooftop_solar' then
    if h.tenure = 'tenant' or not h.roof_access or gg.max_pv_kw(h) < 1 then return 'Infeasible'; end if;
  end if;
  if h.tenure = 'tenant' and rid in ('external_shading', 'solar_water_heater', 'heat_pump_geyser') then
    return case when zs = 'High' then 'Medium' else zs end;
  end if;
  return zs;
end $$;

create or replace function gg.recommend_kw(h public.homes) returns real language plpgsql stable set search_path = '' as $$
declare x public.homes := h; rid text; s text; load real; kw real; cap real := gg.max_pv_kw(h);
begin
  foreach rid in array array['cool_roof','roof_insulation','ac_setpoint','ac_5star_inverter','bldc_fans','led_lighting'] loop
    s := gg.feasibility(x, rid);
    if s in ('High', 'Medium') and not gg.already_done(x, rid) then x := gg.apply(x, rid, null); end if;
  end loop;
  x.pv_kw := 0;
  load := (gg.energy(x)).total_demand;
  kw := load / (select pv_yield_kwh_per_kwp from public.cities where city = h.city);
  if cap > 0 then kw := least(kw, cap); end if;
  kw := round(greatest(1, kw) * 2) / 2;
  if cap > 0 then kw := least(kw, cap); end if;
  return kw;
end $$;

create or replace function gg.apply(h public.homes, rid text, pv_kw real default null) returns public.homes language plpgsql stable set search_path = '' as $$
begin
  case rid
    when 'cool_roof' then h.cool_roof := true;
    when 'roof_insulation' then h.roof_insulation := true;
    when 'external_shading' then h.shading := 'full';
    when 'solar_film' then h.solar_film := true;
    when 'ac_setpoint' then h.ac_setpoint_c := greatest(h.ac_setpoint_c, 24);
    when 'smart_plug_tod' then h.smart_plugs := true;
      h.tod_tariff := h.tod_tariff or coalesce((select tod_tariff from public.tariff_states where state = h.state), false);
    when 'ac_5star_inverter' then h.ac_tech := 'inverter'; h.ac_star := 5; h.ac_age_years := 0;
    when 'bldc_fans' then h.bldc_fan_share := 1;
    when 'led_lighting' then h.led_share := 1;
    when 'fridge_5star' then h.fridge_star := 5; h.fridge_age_years := 0;
    when 'solar_water_heater' then h.water_heating := 'solar';
    when 'heat_pump_geyser' then h.water_heating := 'heat_pump';
    when 'induction_cooking' then h.cooking := 'induction'; h.lpg_cylinders_per_year := 0;
    when 'lithium_battery' then h.backup := 'lithium';
    when 'rooftop_solar' then h.pv_kw := greatest(h.pv_kw, coalesce(pv_kw, gg.recommend_kw(h))); h.net_metered := true;
    else raise exception 'unknown retrofit %', rid;
  end case;
  return h;
end $$;

-- 12-month profile (Jan..Dec): metered, annualised with seasonal weights, or modelled (mirrors consumption.profile)
create or replace function gg.profile(h public.homes) returns real[] language plpgsql stable set search_path = '' as $$
declare e gg.energy_t := gg.energy(h); tot real := 0; shape real[]; obs real[]; implied real[]; med real; m int;
        n int := 0; s_obs real := 0; s_shape real := 0; annual real; out real[] := array[]::real[];
begin
  for m in 1..12 loop tot := tot + e.monthly_import[m]; end loop;
  shape := array(select x / nullif(tot, 0) from unnest(e.monthly_import) x);
  if h.kwh_24m is null then return e.monthly_import; end if;
  obs := gg.last12(h.kwh_24m);
  implied := array(select obs[i] / shape[i] from generate_series(1, 12) i where obs[i] is not null and shape[i] > 0 order by 1);
  if coalesce(array_length(implied, 1), 0) >= 4 then
    med := implied[array_length(implied, 1) / 2 + 1];
    for m in 1..12 loop
      if obs[m] is not null and shape[m] > 0 and (obs[m] / shape[m] > med * 4 or obs[m] / shape[m] < med / 4) then obs[m] := null; end if;
    end loop;
  end if;
  for m in 1..12 loop if obs[m] is not null then n := n + 1; s_obs := s_obs + obs[m]; s_shape := s_shape + shape[m]; end if; end loop;
  if n < 6 then return e.monthly_import; end if;
  annual := s_obs / s_shape;
  for m in 1..12 loop out := out || coalesce(obs[m], annual * shape[m]); end loop;
  return out;
end $$;

create or replace function gg.monthly_bill(p_state text, units real) returns real language plpgsql stable set search_path = '' as $$
declare st record; energy real := 0; r record; bill real;
begin
  select * into st from public.tariff_states where state = p_state;
  units := greatest(0, units);
  for r in select * from public.tariff_slabs where state = p_state and structure_min_units <= units and units < structure_max_units order by slab_from loop
    if units > r.slab_from then energy := energy + (least(units, r.slab_to) - r.slab_from) * r.rate_inr_kwh; end if;
  end loop;
  bill := (energy + units * st.fuel_surcharge_inr_kwh + st.fixed_charge_inr_month) * (1 + st.electricity_duty_pct / 100);
  if st.free_units_if_at_or_below > 0 and units <= st.free_units_if_at_or_below then return 0; end if;
  if p_state = 'Delhi' and units > 200 and units <= 400 then bill := bill - least(800, 0.5 * bill); end if;
  return round(bill::numeric, 2);
end $$;

-- returns net annual cost (bills - export credit)
create or replace function gg.annual_cost(p_state text, imp real[], exp real[], net boolean) returns real language plpgsql stable set search_path = '' as $$
declare total real := 0; credit real := 0; m int; rate real;
begin
  select export_rate_inr_kwh into rate from public.tariff_states where state = p_state;
  for m in 1..12 loop
    if net then
      total := total + gg.monthly_bill(p_state, greatest(0, imp[m] - exp[m]));
      credit := credit + greatest(0, exp[m] - imp[m]) * rate;
    else
      total := total + gg.monthly_bill(p_state, imp[m]);
    end if;
  end loop;
  return round((total - credit)::numeric, 0);
end $$;

create or replace function gg.exports(h public.homes) returns real[] language plpgsql stable set search_path = '' as $$
declare e gg.energy_t := gg.energy(h); shape real[] := array[0.080,0.084,0.096,0.097,0.097,0.080,0.068,0.070,0.078,0.086,0.082,0.082];
        y real; daytime real := 0.35 + case when h.wfh then 0.15 else 0 end; self real := 0; m int; gen real;
begin
  if h.pv_kw = 0 then return array_fill(0::real, array[12]); end if;
  select pv_yield_kwh_per_kwp into y from public.cities where city = h.city;
  for m in 1..12 loop gen := h.pv_kw * y * shape[m]; self := self + least(gen, e.monthly_demand[m] * daytime); end loop;
  return array(select (e.pv_gen - self) * s from unnest(shape) s);
end $$;

create or replace function gg.package(h public.homes)
returns table (improvement_potential_pct real, package_saving_inr real, package_co2_saving_kg real, baseline_co2_kg real,
               score_after_package smallint, package_retrofits jsonb)
language plpgsql stable set search_path = '' as $$
declare
  ids text[] := array(select retrofit_id from public.retrofit_catalogue where retrofit_id <> 'heat_pump_geyser' order by order_rank, retrofit_id);
  rid text; cur public.homes := h; nxt public.homes; applied text[] := array[]::text[];
  base_m real[]; mb real[]; ma real[]; after_m real[] := array[]::real[]; m int;
  eb gg.energy_t := gg.energy(h); ea gg.energy_t; e_base real; e_after real; g_base real := 0; g_after real := 0;
  dg_b real; dg_a real; cost_b real; cost_a real; k int; sc record;
begin
  -- package = every retrofit feasible on the original home and not already done
  ids := array(select x from unnest(ids) x where not gg.already_done(h, x) and gg.feasibility(h, x) <> 'Infeasible');
  foreach rid in array ids loop
    if gg.feasibility(cur, rid) = 'Infeasible' then continue; end if;
    if gg.already_done(cur, rid) and rid not in ('rooftop_solar', 'ac_setpoint') then continue; end if;
    nxt := gg.apply(cur, rid, null);
    applied := applied || rid;
    cur := nxt;
  end loop;
  base_m := gg.profile(h);
  mb := eb.monthly_import; ea := gg.energy(cur); ma := ea.monthly_import;
  for m in 1..12 loop
    after_m := after_m || case when mb[m] > 1e-6 then greatest(0, base_m[m] * ma[m] / mb[m]) else greatest(0, base_m[m] + (ma[m] - mb[m])) end;
    g_base := g_base + base_m[m]; g_after := g_after + after_m[m];
  end loop;
  dg_b := case when h.backup = 'dg_set' then h.outage_hours_month * 0.6 * 12 else 0 end;
  dg_a := case when cur.backup = 'dg_set' then cur.outage_hours_month * 0.6 * 12 else 0 end;
  e_base := g_base + eb.lpg_kwh + dg_b; e_after := g_after + ea.lpg_kwh + dg_a;
  improvement_potential_pct := case when e_base > 0 then round((100 * (e_base - e_after) / e_base)::numeric, 1) else null end;
  cost_b := gg.annual_cost(h.state, base_m, gg.exports(h), h.net_metered);
  cost_a := gg.annual_cost(h.state, after_m, gg.exports(cur), cur.net_metered);
  package_saving_inr := round((cost_b - cost_a + (eb.lpg_kwh - ea.lpg_kwh) / (14.2 * 13.6) * 853)::numeric, 0);
  baseline_co2_kg := round((g_base * 0.727 + eb.lpg_kwh * 0.227 + dg_b * 0.89)::numeric, 1);
  package_co2_saving_kg := round((baseline_co2_kg - (g_after * 0.727 + ea.lpg_kwh * 0.227 + dg_a * 0.89))::numeric, 1);
  -- score after: the after-state with its scaled monthly profile as the last 12 readings
  cur.kwh_24m := array_fill(null::real, array[24]);
  for m in 1..12 loop k := 13 + ((m + 2) % 12); cur.kwh_24m[k] := after_m[m]; end loop;
  select * into sc from gg.score(cur);
  score_after_package := case when cardinality(applied) > 0 then sc.score else (select s.score from gg.score(h) s) end;
  package_retrofits := to_jsonb(applied);
  return next;
end $$;

create or replace function gg.fill_packages(p_limit int default 2000) returns int language plpgsql set search_path = '' as $$
declare n int;
begin
  with todo as (select h.* from public.homes h join public.home_scores s using (home_id) where s.improvement_potential_pct is null limit p_limit),
       calc as (select t.home_id, p.* from todo t cross join lateral gg.package(t) p)
  update public.home_scores hs set improvement_potential_pct = coalesce(c.improvement_potential_pct, 0), package_saving_inr = c.package_saving_inr,
         package_co2_saving_kg = c.package_co2_saving_kg, baseline_co2_kg = c.baseline_co2_kg, score_after_package = c.score_after_package,
         package_retrofits = c.package_retrofits, computed_at = now()
  from calc c where hs.home_id = c.home_id;
  get diagnostics n = row_count;
  return n;
end $$;

revoke all on all functions in schema gg from anon, authenticated;
