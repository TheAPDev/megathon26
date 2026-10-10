-- In-database synthetic population generator (port of greenghar/synth/generator.py; same distributions and
-- the same ground-truth construction: physics x hidden household effects). Reproducible via setseed().
-- IDs are prefixed HD/CD so they never collide with the Python dataset (H/C) used for model training.
--   select synth.generate(1, 5000, 0.42);   -- homes 1..5000
--   select gg.rescore(5000);                 -- score them in SQL

create table if not exists synth.truth (
  home_id text primary key references public.homes(home_id) on delete cascade,
  behaviour real, humid real, leak real, income_plug real, wfh_plug real, wfh_cool real, tenant_cool real
);

create or replace function synth.norm() returns double precision language sql volatile as $$
  select sqrt(-2 * ln(greatest(random(), 1e-12))) * cos(2 * pi() * random())
$$;

create or replace function synth.pick(opts text[], w real[]) returns text language plpgsql volatile as $$
declare r double precision := random() * (select sum(x) from unnest(w) x); acc double precision := 0; i int;
begin
  for i in 1..array_length(opts, 1) loop acc := acc + w[i]; if r <= acc then return opts[i]; end if; end loop;
  return opts[array_length(opts, 1)];
end $$;

create or replace function synth.poisson(lambda real) returns int language plpgsql volatile as $$
declare l double precision := exp(-lambda); k int := 0; p double precision := 1;
begin loop k := k + 1; p := p * random(); exit when p <= l; end loop; return k - 1; end $$;

create or replace function synth.apply(h public.homes, rid text) returns public.homes language plpgsql stable as $$
declare kw real;
begin
  case rid
    when 'cool_roof' then h.cool_roof := true;
    when 'roof_insulation' then h.roof_insulation := true;
    when 'external_shading' then h.shading := 'full';
    when 'solar_film' then h.solar_film := true;
    when 'ac_setpoint' then h.ac_setpoint_c := greatest(h.ac_setpoint_c, 24);
    when 'smart_plug_tod' then h.smart_plugs := true;
    when 'ac_5star_inverter' then h.ac_tech := 'inverter'; h.ac_star := 5; h.ac_age_years := 0;
    when 'bldc_fans' then h.bldc_fan_share := 1;
    when 'led_lighting' then h.led_share := 1;
    when 'fridge_5star' then h.fridge_star := 5; h.fridge_age_years := 0;
    when 'solar_water_heater' then h.water_heating := 'solar';
    when 'induction_cooking' then h.cooking := 'induction'; h.lpg_cylinders_per_year := 0;
    when 'lithium_battery' then h.backup := 'lithium';
    when 'rooftop_solar' then
      kw := least(greatest(1, round((gg.energy(h)).total_demand / (select pv_yield_kwh_per_kwp from public.cities where city = h.city) * 2) / 2),
                  least(coalesce(h.roof_area_m2, 0) / 10, 10));
      h.pv_kw := greatest(h.pv_kw, kw); h.net_metered := true;
    else raise exception 'unknown retrofit %', rid;
  end case;
  return h;
end $$;

-- Simplified feasibility used only to pick plausible historic retrofit events (the API uses the full Python rules)
create or replace function synth.feasible(h public.homes, rid text) returns boolean language sql stable as $$
  select case rid
    when 'cool_roof' then (h.floor_position = 'top' or h.dwelling_type <> 'apartment') and not h.cool_roof
    when 'ac_5star_inverter' then h.n_ac > 0 and not (h.ac_tech = 'inverter' and h.ac_star = 5)
    when 'smart_plug_tod' then h.n_ac > 0 and not h.smart_plugs
    when 'bldc_fans' then h.n_fans > 0 and h.bldc_fan_share < 0.99
    when 'led_lighting' then h.led_share < 0.99
    when 'fridge_5star' then h.fridge_star < 5
    when 'solar_water_heater' then h.water_heating = 'electric_geyser' and h.roof_access and h.tenure = 'owner'
    when 'induction_cooking' then h.cooking = 'lpg'
    when 'lithium_battery' then h.backup = 'lead_acid'
    when 'rooftop_solar' then h.roof_access and h.tenure = 'owner' and coalesce(h.roof_area_m2, 0) >= 10 and h.pv_kw = 0
    else false end
$$;

create or replace function synth.generate(p_start int, p_n int, p_seed double precision default 0.42)
returns int language plpgsql as $$
declare
  i int; c record; hid text; cid text; h public.homes; pre public.homes; post public.homes;
  income text; dwelling text; floor_pos text; tenure text; med real; area real; occ int; age real; exposed boolean;
  roof_access boolean; roof_area real; n_ac int; ac_age real; pv real; outage real; backup text; smart boolean; tod_ok boolean;
  tr real[]; yf real; ev_rid text; ev_month int := -1; opts text[]; wts real[]; k int; mon int; yr int; st public.homes;
  arr_pre_25 real[]; arr_pre_26 real[]; arr_post_25 real[]; arr_post_26 real[]; arr_pre_24 real[]; arr_post_24 real[];
  readings real[]; v real; src text; miss int; idx int; sc record; value real; principal real; has_loan boolean; rate real; emi real;
  outstanding real; months_ago int; r_m double precision; price real; offset_m int; wh text;
  cities_arr text[]; cities_w real[]; n int := 0; cname text;
begin
  perform setseed(p_seed);
  for i in 1..p_start loop perform random(); end loop;  -- advance the stream so batches differ but stay reproducible
  select array_agg(city order by city), array_agg(case when tier = 1 then 3 else 1 end::real order by city) into cities_arr, cities_w from public.cities;
  for i in p_start..(p_start + p_n - 1) loop
    hid := 'HD' || lpad(i::text, 6, '0'); cid := 'CD' || lpad(i::text, 6, '0');
    cname := synth.pick(cities_arr, cities_w);  -- pick first: a volatile call inside WHERE would re-roll per row
    select * into c from public.cities where city = cname;
    income := synth.pick(array['low','middle','upper_middle','high'], array[.15,.45,.28,.12]::real[]);
    dwelling := synth.pick(array['apartment','independent_house','row_house'], case when c.tier = 1 then array[.72,.20,.08]::real[] else array[.45,.43,.12]::real[] end);
    floor_pos := case when dwelling = 'apartment' then synth.pick(array['top','middle','ground'], array[.18,.62,.20]::real[]) else 'top' end;
    tenure := synth.pick(array['owner','tenant'], array[.72,.28]::real[]);
    med := (case income when 'low' then 45 when 'middle' then 70 when 'upper_middle' then 100 else 150 end) * case when dwelling <> 'apartment' then 1.5 else 1 end;
    area := least(600, greatest(25, exp(ln(med) + 0.25 * synth.norm())));
    occ := least(9, greatest(1, synth.poisson(3.2) + 1));
    age := random() * 35;
    exposed := floor_pos = 'top';
    if dwelling <> 'apartment' then roof_access := tenure = 'owner' or random() < 0.2; roof_area := area * (0.6 + 0.4 * random());
    else roof_access := exposed and tenure = 'owner' and random() < 0.35; roof_area := case when roof_access then area * 0.8 else 0 end; end if;
    n_ac := (synth.pick(array['0','1','2','3','4'],
             case when c.nbc_zone = 'cold' then array[.85,.12,.03,0,0]::real[]
                  when income = 'low' then array[.75,.25,0,0,0]::real[] when income = 'middle' then array[.40,.40,.18,.02,0]::real[]
                  when income = 'upper_middle' then array[.12,.38,.35,.15,0]::real[] else array[.03,.17,.35,.30,.15]::real[] end))::int;
    ac_age := random() * 14;
    outage := -ln(greatest(random(), 1e-9)) * case when c.tier = 1 then 4 else 15 end;
    backup := synth.pick(array['none','lead_acid','lithium','dg_set'], case when c.tier = 1 then array[.66,.25,.06,.03]::real[] else array[.46,.45,.06,.03]::real[] end);
    if backup = 'dg_set' and dwelling = 'apartment' then backup := 'none'; end if;
    smart := random() < case when c.tier = 1 then .30 else .15 end;
    select t.tod_tariff into tod_ok from public.tariff_states t where t.state = c.state;
    pv := case when roof_access and tenure = 'owner' and random() < 0.10 then synth.pick(array['1','2','3','4','5'], array[.15,.30,.35,.12,.08]::real[])::real else 0 end;
    if roof_area < pv * 10 then pv := floor(roof_area / 10); end if;
    wh := synth.pick(array['electric_geyser','solar','heat_pump','gas','none'],
          case c.nbc_zone when 'warm_humid' then array[.35,.04,.01,.05,.55]::real[] when 'hot_dry' then array[.50,.08,.01,.06,.35]::real[]
                          when 'temperate' then array[.60,.12,.02,.06,.20]::real[] else array[.70,.08,.02,.05,.15]::real[] end);
    if wh = 'solar' and not roof_access then wh := 'electric_geyser'; end if;
    h := row(hid, cid, c.city, c.state, c.nbc_zone, c.lat + 0.05 * synth.norm(), c.lon + 0.05 * synth.norm(),
             dwelling, floor_pos, tenure, round(area::numeric, 1), occ, round(age::numeric, 1), round(roof_area::numeric, 1), roof_access,
             synth.pick(array['aac','hollow_block','solid_brick'], case when age < 10 then array[.35,.25,.40]::real[] else array[.05,.20,.75]::real[] end),
             round(least(0.6, greatest(0.08, 0.22 + 0.07 * synth.norm()))::numeric, 3), random() < .35,
             synth.pick(array['none','partial','full'], array[.45,.40,.15]::real[]),
             exposed and random() < .08, exposed and random() < .05, random() < .06,
             n_ac, case when random() < (case when ac_age < 4 then .75 when ac_age < 8 then .45 else .15 end) then 'inverter' else 'fixed' end,
             synth.pick(array['1','2','3','4','5'], array[.08,.12,.45,.10,.25]::real[])::int, round(ac_age::numeric, 1),
             synth.pick(array['1.0','1.5','2.0'], array[.25,.60,.15]::real[])::real,
             least(28, greatest(18, round((23 + 1.5 * synth.norm()) * 2) / 2)),
             case when c.nbc_zone in ('hot_dry','composite') and random() < case when income in ('low','middle') then .4 else .15 end then 1 + floor(random() * 2) else 0 end,
             least(14, greatest(1, round(area / 18) + 1)), case when random() < 0.7 then 0 else round((0.2 + 0.8 * random())::numeric, 2) end,
             synth.pick(array['1','2','3','4','5'], array[.10,.15,.40,.15,.20]::real[])::int, round((random() * 15)::numeric, 1),
             least(60, greatest(4, round(area / 7))), round(least(1, greatest(0, 0.71 + 0.16 * synth.norm()))::numeric, 2),
             wh, synth.pick(array['lpg','png','induction'], case when c.tier = 1 then array[.78,.12,.10]::real[] else array[.88,.02,.10]::real[] end),
             null, pv, pv > 0, backup, round(outage::numeric, 1), smart, smart and tod_ok and random() < .4,
             random() < case when income in ('upper_middle','high') then .15 else .04 end, null,
             least(15, greatest(1, round(1 + 1.6 * n_ac + area / 80))), income,
             random() < case when income in ('upper_middle','high') then .25 else .10 end,
             'survey', 'complete', false, null, 'synthetic', now(), now())::public.homes;
    if h.cooking = 'lpg' then h.lpg_cylinders_per_year := round(least(30, greatest(2, 2 + 1.75 * occ + 1.2 * synth.norm()))::numeric, 1); end if;
    -- hidden truth multipliers
    tr := array[exp(0.12 * synth.norm()), case when c.nbc_zone = 'warm_humid' then 1.12 else 1 end, 1 + 0.004 * greatest(0, age - 10),
                case income when 'low' then 0.7 when 'middle' then 1.0 when 'upper_middle' then 1.3 else 1.75 end,
                case when h.wfh then 1.15 else 1 end, case when h.wfh then 1.10 else 1 end, case when tenure = 'tenant' then 0.95 else 1 end]::real[];
    -- one historic retrofit event for ~18% of homes
    pre := h; post := h; ev_month := -1;
    if random() < 0.18 then
      select array_agg(r), array_agg(w) into opts, wts from (values ('ac_5star_inverter',.25::real),('bldc_fans',.15),('led_lighting',.15),('rooftop_solar',.12),
        ('cool_roof',.08),('fridge_5star',.08),('solar_water_heater',.05),('smart_plug_tod',.05),('induction_cooking',.04),('lithium_battery',.03)) v(r, w)
        where synth.feasible(h, r);
      if opts is not null then
        ev_rid := synth.pick(opts, wts); ev_month := 3 + floor(random() * 19)::int;
        post := synth.apply(h, ev_rid); post.has_retrofit_history := true;
      end if;
    end if;
    -- 24 months of true import (month 0 = Oct 2024); weather factor per year; 2026 Apr-Jun heatwave +8%
    readings := array[]::real[];
    for k in 0..23 loop
      mon := ((9 + k) % 12) + 1; yr := 2024 + (9 + k) / 12;
      st := case when ev_month >= 0 and k >= ev_month then post else pre end;
      yf := (1 + 0.06 * synth.norm()) * case when yr = 2026 and mon in (4,5,6) then 1.08 else 1 end;
      v := ((gg.energy(st, tr, yf)).monthly_import)[mon] * exp(0.06 * synth.norm());
      readings := readings || round(v::numeric, 1)::real;
    end loop;
    h := post; h.has_retrofit_history := ev_month >= 0;
    -- data source, missingness, OCR errors, missing area, BEE labels with conflicts
    src := case when h.smart_meter then 'smart_meter' else synth.pick(array['bill_ocr','bbps','survey'], array[.55,.25,.20]::real[]) end;
    h.data_source := src; h.missing_pattern := 'complete';
    if src = 'survey' then readings := null; h.missing_pattern := 'no_data';
    else
      v := random();
      if v < 0.18 then
        miss := case when v < 0.03 then 7 + floor(random() * 5)::int else 1 + floor(random() * 6)::int end;
        for k in 1..miss loop idx := 13 + floor(random() * 12)::int; readings[idx] := null; end loop;
        h.missing_pattern := 'missing_some_of_last_12';
      end if;
      if src = 'bill_ocr' then
        for k in 1..24 loop
          if readings[k] is not null and random() < 0.01 then readings[k] := readings[k] * case when random() < .5 then 10 else 0.1 end; h.missing_pattern := h.missing_pattern || '+ocr_error'; end if;
        end loop;
      end if;
    end if;
    h.kwh_24m := readings;
    if (age < 8 and random() < 0.25) or random() < 0.02 then
      h.bee_star_label := least(5, greatest(1, round(5.5 - coalesce((select avg(x) from unnest(readings[13:24]) x), 250) * 12 / area / 15)))::int;
      if random() < 0.15 then h.bee_star_label := case when h.bee_star_label <= 2 then 5 else 1 end; end if;
    end if;
    if random() < 0.03 then h.carpet_area_m2 := null; end if;
    -- customer and loan
    value := area * 10.7639 * c.price_inr_per_sqft * case when dwelling <> 'apartment' then 1.15 else 1 end;
    has_loan := tenure = 'owner' and random() < 0.7;
    principal := case when has_loan then value * (0.6 + 0.25 * random()) else 0 end;
    months_ago := case when has_loan then 6 + floor(random() * 174)::int else 0 end;
    rate := case when has_loan then 8.25 + 1.35 * random() else 0 end;
    r_m := rate / 1200;
    emi := case when has_loan then principal * r_m * power(1 + r_m, 240) / (power(1 + r_m, 240) - 1) else 0 end;
    outstanding := case when has_loan then principal * (power(1 + r_m, 240) - power(1 + r_m, months_ago)) / (power(1 + r_m, 240) - 1) else 0 end;
    insert into public.customers values (cid, null, c.state, c.city,
      synth.pick(array['25-34','35-44','45-54','55+'], array[.3,.35,.22,.13]::real[]), income,
      synth.pick(array['en','hi','ta','mr','te','kn','bn','gu'], array[.35,.35,.06,.06,.06,.05,.04,.03]::real[]),
      has_loan, round(principal::numeric, -3), round(outstanding::numeric, -3), round(rate::numeric, 2), round(emi::numeric), months_ago,
      round(value::numeric, -4), synth.pick(array['A','B','C','D'], array[.35,.4,.18,.07]::real[]), random() < 0.85, random() < 0.55, now());
    insert into public.homes values (h.*);
    insert into synth.truth values (hid, tr[1], tr[2], tr[3], tr[4], tr[5], tr[6], tr[7]);
    if ev_month >= 0 then
      insert into public.retrofit_events (home_id, retrofit_id, completed_month, cost_inr, financed, true_annual_kwh_saving)
      values (hid, ev_rid, (date '2024-10-01' + ev_month * interval '1 month')::date,
              round(((select cost_min_inr + random() * (cost_max_inr - cost_min_inr) from public.retrofit_catalogue where retrofit_id = ev_rid)
                     * case (select cost_basis from public.retrofit_catalogue where retrofit_id = ev_rid)
                         when 'per_ac' then greatest(1, pre.n_ac) when 'per_fan' then greatest(1, pre.n_fans)
                         when 'per_point' then greatest(1, pre.light_points) when 'per_kw' then greatest(1, post.pv_kw)
                         when 'per_sqft_roof' then greatest(1, pre.roof_area_m2) * 10.76 else 1 end)::numeric, -2),
              random() < case when ev_rid = 'rooftop_solar' then .6 else .2 end,
              (select sum(x) from unnest((gg.energy(pre, tr)).monthly_import) x) - (select sum(x) from unnest((gg.energy(post, tr)).monthly_import) x));
    end if;
    -- historic sale for ~25% of homes: hedonic price x disclosed rating premium (1.5% per 10 points) x market index x noise
    if random() < 0.25 then
      select * into sc from gg.score(h);
      offset_m := -floor(random() * 60)::int;
      price := area * 10.7639 * c.price_inr_per_sqft * case dwelling when 'independent_house' then 1.15 when 'row_house' then 1.05 else 1 end
               * case floor_pos when 'top' then 0.98 when 'ground' then 0.97 else 1 end * greatest(0.7, 1 - 0.008 * greatest(0, age + offset_m / 12.0))
               * (1 + 0.015 * (sc.raw_score - 50) / 10) * power(1.06, offset_m / 12.0) * exp(0.08 * synth.norm());
      insert into public.sales (home_id, sale_month, price_inr, score_at_sale)
      values (hid, (date '2026-09-01' + offset_m * interval '1 month')::date, round(price::numeric, -3), round(sc.raw_score::numeric, 1));
    end if;
    -- stated memory for ~12% of customers
    if random() < 0.12 then
      if tenure = 'tenant' then insert into public.memory (customer_id, home_id, kind, key, value) values (cid, hid, 'constraint', 'tenure', '"renting"'); end if;
      if random() < .5 then insert into public.memory (customer_id, home_id, kind, key, value)
        values (cid, hid, 'constraint', 'budget_inr', to_jsonb(synth.pick(array['20000','50000','100000','200000'], array[.3,.35,.25,.1]::real[])::int)); end if;
      if random() < .2 then insert into public.memory (customer_id, home_id, kind, key, value)
        values (cid, hid, 'constraint', 'exclude', to_jsonb(synth.pick(array['rooftop_solar','induction_cooking','ac_5star_inverter'], array[.4,.4,.2]::real[]))); end if;
    end if;
    n := n + 1;
  end loop;
  return n;
end $$;

revoke all on all functions in schema synth from anon, authenticated;
revoke all on all functions in schema gg from anon, authenticated;
