-- Green Ghar Score: core schema. Invariants live in the schema, not only in the application.
create extension if not exists pgcrypto;
create schema if not exists gg;     -- engine functions (score, modelled energy)
create schema if not exists synth;  -- synthetic data generator (not exposed through the API)

-- ---------------------------------------------------------------- reference data (versioned CSVs)
create table public.cities (
  city text primary key,
  state text not null,
  lat double precision not null check (lat between 6 and 37),
  lon double precision not null check (lon between 68 and 98),
  nbc_zone text not null check (nbc_zone in ('hot_dry','warm_humid','composite','temperate','cold')),
  tier smallint not null check (tier in (1,2,3)),
  temps real[] not null check (array_length(temps,1) = 12),
  pv_yield_kwh_per_kwp real not null check (pv_yield_kwh_per_kwp between 800 and 2200),
  price_inr_per_sqft real not null check (price_inr_per_sqft > 0)
);

create table public.tariff_states (
  state text primary key,
  discom text not null,
  fixed_charge_inr_month real not null check (fixed_charge_inr_month >= 0),
  fuel_surcharge_inr_kwh real not null default 0,
  electricity_duty_pct real not null default 0,
  free_units_if_at_or_below real not null default 0,
  subsidy_note text,
  net_metering text not null default 'net',
  export_rate_inr_kwh real not null,
  state_solar_topup_inr_per_kw real not null default 0,
  state_solar_topup_cap_inr real not null default 0,
  tod_tariff boolean not null default false
);

create table public.tariff_slabs (
  id bigint generated always as identity primary key,
  state text not null references public.tariff_states(state) on delete cascade,
  structure_min_units real not null,
  structure_max_units real not null,
  slab_from real not null,
  slab_to real not null,
  rate_inr_kwh real not null check (rate_inr_kwh >= 0),
  check (slab_to > slab_from), check (structure_max_units > structure_min_units)
);
create index on public.tariff_slabs (state);

create table public.emission_factors (
  fuel text primary key, unit text not null, kg_co2_per_unit real not null check (kg_co2_per_unit >= 0),
  version text not null, source text not null
);

create table public.subsidy_rules (
  id bigint generated always as identity primary key,
  scheme text not null, segment text not null, kw_from real not null, kw_to real not null,
  inr_per_kw real not null, cap_inr real not null, notes text, source text
);

create table public.finance_products (
  product text primary key, lender_type text not null, max_amount_inr real not null, rate_pct real not null,
  tenure_years real not null, min_kw real, max_kw real, collateral text, notes text
);

create table public.appliances (
  appliance text not null, variant text not null, metric text not null, value real not null, unit text, source text,
  primary key (appliance, variant)
);

create table public.retrofit_catalogue (
  retrofit_id text primary key, name text not null,
  category text not null check (category in ('envelope','controls','cooling','appliance','water','fuel_switch','backup','generation')),
  order_rank smallint not null check (order_rank between 1 and 9),
  cost_min_inr real not null, cost_max_inr real not null, cost_basis text not null,
  effect_type text not null, effect_value real not null, lifetime_years real not null, description text,
  check (cost_max_inr >= cost_min_inr)
);

create table public.zone_suitability (
  retrofit_id text not null references public.retrofit_catalogue(retrofit_id) on delete cascade,
  zone text not null check (zone in ('hot_dry','warm_humid','composite','temperate','cold')),
  suitability text not null check (suitability in ('High','Medium','Low')),
  primary key (retrofit_id, zone)
);

create table public.benchmarks (
  zone text primary key, median_kwh_m2 real not null check (median_kwh_m2 > 0), n_homes int, method text
);

-- ---------------------------------------------------------------- customers and homes
create table public.customers (
  customer_id text primary key,
  auth_user_id uuid unique references auth.users(id) on delete set null,  -- links a Supabase Auth login
  region text not null, city text not null references public.cities(city),
  age_band text, income_band text check (income_band in ('low','middle','upper_middle','high')),
  preferred_language text not null default 'en',
  has_home_loan boolean not null default false,
  loan_principal_inr numeric(14,0) not null default 0 check (loan_principal_inr >= 0),
  loan_outstanding_inr numeric(14,0) not null default 0 check (loan_outstanding_inr >= 0),
  loan_rate_pct real, loan_emi_inr numeric(12,0), loan_start_months_ago int,
  property_value_inr numeric(14,0) check (property_value_inr > 0),
  credit_band text check (credit_band in ('A','B','C','D')),
  consent_energy_data boolean not null default false,
  consent_marketing boolean not null default false,
  created_at timestamptz not null default now(),
  check (not has_home_loan or loan_principal_inr > 0)
);

create table public.homes (
  home_id text primary key,
  customer_id text references public.customers(customer_id) on delete set null,
  city text not null references public.cities(city),
  state text not null, zone text not null,
  lat double precision, lon double precision,
  dwelling_type text not null check (dwelling_type in ('apartment','independent_house','row_house')),
  floor_position text not null check (floor_position in ('ground','middle','top')),
  tenure text not null check (tenure in ('owner','tenant')),
  carpet_area_m2 real check (carpet_area_m2 > 10 and carpet_area_m2 < 2000),
  occupants smallint not null check (occupants between 1 and 15),
  building_age_years real check (building_age_years between 0 and 120),
  roof_area_m2 real check (roof_area_m2 >= 0), roof_access boolean not null default false,
  wall_type text not null check (wall_type in ('solid_brick','hollow_block','aac')),
  window_to_wall real not null check (window_to_wall between 0 and 0.9),
  west_glass boolean not null default false,
  shading text not null check (shading in ('none','partial','full')),
  cool_roof boolean not null default false, roof_insulation boolean not null default false, solar_film boolean not null default false,
  n_ac smallint not null check (n_ac between 0 and 10),
  ac_tech text not null check (ac_tech in ('fixed','inverter')),
  ac_star smallint not null check (ac_star between 1 and 5),
  ac_age_years real not null check (ac_age_years between 0 and 30),
  ac_tonnage real not null check (ac_tonnage between 0.75 and 3),
  ac_setpoint_c real not null check (ac_setpoint_c between 16 and 30),
  n_coolers smallint not null default 0 check (n_coolers between 0 and 6),
  n_fans smallint not null check (n_fans between 0 and 20),
  bldc_fan_share real not null check (bldc_fan_share between 0 and 1),
  fridge_star smallint not null check (fridge_star between 1 and 5),
  fridge_age_years real not null check (fridge_age_years between 0 and 30),
  light_points smallint not null check (light_points between 0 and 80),
  led_share real not null check (led_share between 0 and 1),
  water_heating text not null check (water_heating in ('electric_geyser','solar','heat_pump','gas','none')),
  cooking text not null check (cooking in ('lpg','png','induction')),
  lpg_cylinders_per_year real check (lpg_cylinders_per_year between 0 and 40),
  pv_kw real not null default 0 check (pv_kw between 0 and 50),
  net_metered boolean not null default false,
  backup text not null check (backup in ('none','lead_acid','lithium','dg_set')),
  outage_hours_month real not null default 0 check (outage_hours_month between 0 and 300),
  smart_meter boolean not null default false, tod_tariff boolean not null default false, smart_plugs boolean not null default false,
  bee_star_label smallint check (bee_star_label between 1 and 5),
  sanctioned_load_kw real not null check (sanctioned_load_kw between 0.5 and 50),
  income_band text not null check (income_band in ('low','middle','upper_middle','high')),
  wfh boolean not null default false,
  data_source text not null check (data_source in ('smart_meter','bill_ocr','bbps','survey')),
  missing_pattern text,
  has_retrofit_history boolean not null default false,
  -- 24 months of grid import, month 0 = 2024-10 ... month 23 = 2026-09; null = missing, never zero-filled
  kwh_24m real[] check (kwh_24m is null or array_length(kwh_24m,1) = 24),
  source text not null default 'synthetic' check (source in ('synthetic','user','telegram','api')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (pv_kw = 0 or roof_access or source <> 'synthetic'),
  check (dwelling_type = 'apartment' or floor_position = 'top')
);
create index on public.homes (customer_id);
create index on public.homes (city);
create index on public.homes (zone, dwelling_type);

-- Long form of the readings for analytics
create view public.meter_readings with (security_invoker = true) as
select h.home_id, (date '2024-10-01' + (g.k - 1) * interval '1 month')::date as month, h.kwh_24m[g.k] as kwh, h.data_source
from public.homes h cross join lateral generate_series(1, 24) as g(k)
where h.kwh_24m is not null;

create table public.retrofit_events (
  event_id text primary key default ('E-' || encode(gen_random_bytes(6), 'hex')),
  home_id text not null references public.homes(home_id) on delete cascade,
  retrofit_id text not null references public.retrofit_catalogue(retrofit_id),
  completed_month date not null,
  cost_inr numeric(12,0) check (cost_inr >= 0),
  financed boolean not null default false,
  true_annual_kwh_saving real,
  created_at timestamptz not null default now()
);
create index on public.retrofit_events (home_id);

create table public.sales (
  sale_id text primary key default ('S-' || encode(gen_random_bytes(6), 'hex')),
  home_id text not null references public.homes(home_id) on delete cascade,
  sale_month date not null,
  price_inr numeric(14,0) not null check (price_inr > 0),
  score_at_sale real check (score_at_sale between 0 and 100)
);
create index on public.sales (home_id);

create table public.memory (
  memory_id text primary key default ('M-' || encode(gen_random_bytes(6), 'hex')),
  customer_id text not null references public.customers(customer_id) on delete cascade,
  home_id text references public.homes(home_id) on delete cascade,
  kind text not null check (kind in ('constraint','preference','feedback')),
  key text not null,
  value jsonb not null,
  created_at timestamptz not null default now()
);
create index on public.memory (customer_id);

-- ---------------------------------------------------------------- engine outputs and logs
create table public.home_scores (
  home_id text primary key references public.homes(home_id) on delete cascade,
  score smallint not null check (score between 0 and 100),
  raw_score real not null,
  band text not null check (band in ('Highly efficient','Good','Moderate','Poor','Very poor')),
  confidence text not null check (confidence in ('high','medium','low')),
  annual_grid_kwh real, annual_estimated boolean not null default true, intensity_kwh_m2 real,
  s_energy_efficiency real, s_consumption_intensity real, s_envelope real, s_cooling_system real,
  s_windows_shading real, s_renewables real, s_smart_use real,
  weakest_component text, warnings jsonb not null default '[]',
  improvement_potential_pct real, package_saving_inr real, package_co2_saving_kg real, baseline_co2_kg real,
  score_after_package smallint, package_retrofits jsonb,
  engine text not null default 'python', engine_version text,
  computed_at timestamptz not null default now()
);
create index on public.home_scores (band);
create index on public.home_scores (improvement_potential_pct desc nulls last);

create table public.advisor_logs (
  id bigint generated always as identity primary key,
  home_id text references public.homes(home_id) on delete set null,
  customer_id text references public.customers(customer_id) on delete set null,
  channel text not null default 'api' check (channel in ('api','telegram','web')),
  question text not null, answer text not null, language text, provider text, model text,
  grounded boolean not null, figures_total int, figures_verified int, tool_calls jsonb,
  latency_ms int, prompt_tokens int, completion_tokens int,
  created_at timestamptz not null default now()
);
create index on public.advisor_logs (created_at desc);

create table public.telegram_links (
  chat_id bigint primary key,
  home_id text references public.homes(home_id) on delete set null,
  language text not null default 'en',
  created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);

create table public.bill_uploads (
  id bigint generated always as identity primary key,
  home_id text references public.homes(home_id) on delete cascade,
  storage_path text, parsed jsonb, provider text, warnings jsonb,
  created_at timestamptz not null default now()
);

create table public.model_registry (
  name text not null, version text not null, metrics jsonb, trained_at timestamptz not null default now(),
  primary key (name, version)
);

create or replace function public.touch_updated_at() returns trigger language plpgsql set search_path = '' as $$
begin new.updated_at := now(); return new; end $$;
create trigger homes_touch before update on public.homes for each row execute function public.touch_updated_at();
create trigger tg_touch before update on public.telegram_links for each row execute function public.touch_updated_at();
