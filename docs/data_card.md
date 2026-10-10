# Data card: Green Ghar synthetic population (India)

**Version:** 1.0 · **Seed:** 42 · **Built by:** `scripts/generate_data.py` (Python) and `synth.generate()` (Supabase SQL)
**Status:** fully synthetic. No real customer, meter or sale data is used anywhere.

## Why synthetic
India has no open, property-level dataset that links home characteristics, smart-meter readings, retrofits and sale prices. The population is generated from documented distributions anchored to public statistics, and every rule is listed below, so results can be reproduced exactly and nothing leaks private data.

## Tables

| Table | Rows (Python) | Rows (Supabase) | Grain |
|---|---|---|---|
| homes | 50,000 | 50,000 | one home, current state, 24 months of grid import |
| customers | 50,000 | 50,000 | bank customer linked 1:1 to a home, with home-loan fields |
| retrofit_events | 11,310 | 9,200 | completed retrofit with month, cost and true saving |
| sales | 12,470 | 12,237 | historic sale price |
| memory | 7,766 | 5,519 | stated constraint / preference |
| home_scores | 50,000 | 50,000 | precomputed score, sub-scores, package savings |
| meter_readings (view) | n/a | 1,020,576 | long-form monthly readings |
| truth (hidden) | 50,000 | 50,000 (`synth.truth`) | hidden household multipliers; never a model feature |

Python IDs are `H000001`/`C000001`; database-generated IDs are `HD000001`/`CD000001`, so the two populations never collide. Both use the same distributions and the same ground-truth construction. Mean score: Python 44.4, SQL 43.9. Python and SQL scores agree to within 0.001 points per home on sampled homes (`tests/test_sql_parity.py`).

## Generation rules
- **City** (43 cities, 24 states): tier-1 cities weighted 3x tier-2. Climate zone, monthly mean temperatures, PV yield and price levels come from `data/reference/cities.csv`.
- **Income band:** low 15%, middle 45%, upper-middle 28%, high 12% (home-loan customers skew above national averages).
- **Dwelling:** apartment, independent house or row house (72/20/8% in tier-1 cities, 45/43/12% in tier-2). Apartment floor: top 18%, middle 62%, ground 20%.
- **Tenure:** 72% owners, 28% tenants.
- **Carpet area:** lognormal (σ 0.25), median 45/70/100/150 m² by income band, x1.5 for houses.
- **Occupants:** Poisson(3.2) + 1. **Building age:** U(0, 35).
- **Walls:** AAC/hollow/brick 35/25/40% if newer than 10 years, else 5/20/75%.
- **ACs per home:** by income (low 75% none ... high 45% with 3 or more). Cold zone: 85% none.
- **AC technology:** inverter share 75%, 45% or 15% by age. Star mix: 1/2/3/4/5 = 8/12/45/10/25%. Set-point N(23, 1.5).
- **Fans:** area/18 + 1, 30% partly BLDC. **Fridge:** star 1-5, age U(0, 15). **LEDs:** Beta(5, 2) share.
- **Water heating:** by zone (e.g. composite: 70% electric geyser, 8% solar).
- **Cooking:** LPG 78% / PNG 12% / induction 10% (tier-1). Cylinders = 2 + 1.75 x occupants + noise.
- **Outages:** Exponential, mean 4 h/month (tier-1) or 15 h/month (tier-2). Backup: lead-acid, lithium or DG set (houses only).
- **Rooftop PV:** 10% of owners with roof access, 1-5 kW.
- **Smart meter:** 30% tier-1, 15% tier-2. Time-of-day tariff where the state offers one.
- **BEE star label:** mostly on newer buildings, derived from actual intensity; 15% are deliberately wrong (conflicts).

## Ground-truth consumption
`true import = physics model x hidden multipliers + noise`, month by month:
- **Physics:** `greenghar/engine/physics.py`, the same model the engine uses.
- **Hidden multipliers** (unknown to the engine, so the ML layer has something real to learn):
  - behaviour: lognormal(0, 0.12)
  - warm-humid dehumidification: +12% cooling
  - leaky buildings older than 10 years: +0.4% cooling per year
  - income-driven plug loads: 0.70 / 1.0 / 1.30 / 1.75
  - work-from-home: +15% plugs and +10% cooling
  - tenants: -5% cooling
- **Weather:** a per-city, per-year factor N(1, 0.06), plus +8% in April-June 2026 for the record heatwave.
- **Month noise:** lognormal(0, 0.06).
- **Retrofit history:** 18% of homes (5% with two retrofits) have a retrofit in months 3-21; readings after that month come from the post-retrofit state.

## Injected data-quality problems (documented rates)
- 15% of homes miss 1-6 of the last 12 months; 3% miss 7-11.
- 20% have no meter data (survey only).
- 1% of bill-OCR months carry a digit error (x10 or ÷10).
- 3% have no carpet area.
- 15% of BEE labels conflict with actual use.

## Calibration
- Median annual grid use is 3.6 MWh. No-AC homes have a median of 2.3 MWh, against the CLASP-BEE 2024 urban mean of 1.94 MWh; the gap is because this population skews to bank customers.
- Zone benchmarks (`data/reference/benchmarks.csv`) are medians of complete-data homes, the Indian stand-in for NEED medians.

## Sales (value model labels)
Price = area x city price/sq ft x type x floor x age x (1 + **1.5% per 10 score points**) x market index (6%/yr) x lognormal(0, 0.08).
The rating premium is an **assumption**. The value model recovers it (1.63% per 10 points), which shows internal consistency, not real-world accuracy.

## Fields unavailable at prediction time (leakage guard)
The following are never used as model features, enforced by `ml/features.py:FORBIDDEN` and `tests/test_leakage.py`:
- `kwh_24m` / `monthly_kwh` (for the energy model)
- `price_inr`, `score_at_sale`
- `true_annual_kwh_saving`
- all truth multipliers
- `missing_pattern`, `data_source`, `carpet_area_true_m2`, `bee_star_label`

## Splits
Grouped by `home_id`, which is also the customer (1:1), at 70/15/15 with seed 42. Models are tuned on validation, and test metrics are reported once.

## Real public data alongside the synthetic population
The synthetic homes are kept, because no public Indian dataset links home attributes, appliances, bills and retrofits per household. Beside them, Supabase schema `realdata` holds 80,811 rows of real public data (migrations 012-019; sources, licences and fetch times are in `realdata.sources`):
- **Census 2011** (640 districts, all 118 fields).
- **NFHS-5** (36 states/UTs × 132 indicators, and 340 districts × 104 indicators).
- **Open-Meteo/ERA5** daily weather for all 43 engine cities over the exact billing window (Oct 2024 - Sep 2026).
- **NASA POWER** climatology.
- **OWID** India energy and CO₂ series.
- **WRI** power plants.
- **World Bank** WDI.

**How it is used**
- **Calibration report** (`realdata.synth_vs_real_state`, `/reference/real/calibration`). Synthetic urban bank-customer homes use clean cooking fuel 100% of the time, against 71-99% for urban households in NFHS-5. They are owner-occupied 67-82%, against 50-98% (Census 2011, rural included). Mean occupancy is about 4.2, against 3.9-5.9. These gaps are reported openly. They come from the target segment (urban homes with a home loan), not from a bug.
- **Climate check** (`realdata.city_climate_check`). The engine's PV yields agree with NASA irradiance to within about 5%. Real CDD24 and heatwave days are available for every billing month.
- **Weather signature** (`realdata.home_weather_signature`). Each home's 24 monthly readings are regressed on real CDD24. This gives kWh per degree-day and a weather-normalised annual use for 42,524 homes (mean R² 0.55).

## Licence and sources
- **Licence:** synthetic data, free to use.
- **Reference inputs:** see `data/reference/SOURCES.md` (IMD normals, NBC/ECBC zones, state ERC tariffs, CEA v20, PM Surya Ghar, BEE tables). These are indicative as of October 2026.
