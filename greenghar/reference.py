"""Loads the versioned reference tables in data/reference (cached)."""
from __future__ import annotations

import csv
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

REF_DIR = Path(__file__).resolve().parent.parent / "data" / "reference"
MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
DAYS_IN_MONTH = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
ZONES = ["hot_dry", "warm_humid", "composite", "temperate", "cold"]


def _read(name: str) -> list[dict]:
    with open(REF_DIR / name, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


@dataclass(frozen=True)
class City:
    city: str
    state: str
    lat: float
    lon: float
    zone: str
    tier: int
    temps: tuple[float, ...]
    pv_yield: float
    price_per_sqft: float


@lru_cache
def cities() -> dict[str, City]:
    out = {}
    for r in _read("cities.csv"):
        out[r["city"]] = City(
            city=r["city"], state=r["state"], lat=float(r["lat"]), lon=float(r["lon"]),
            zone=r["nbc_zone"], tier=int(r["tier"]),
            temps=tuple(float(r[f"t_{m}"]) for m in MONTHS),
            pv_yield=float(r["pv_yield_kwh_per_kwp"]),
            price_per_sqft=float(r["price_inr_per_sqft"]),
        )
    return out


def city(name: str) -> City:
    try:
        return cities()[name]
    except KeyError as e:
        raise KeyError(f"Unknown city '{name}'. Known: {sorted(cities())}") from e


@lru_cache
def tariff_states() -> dict[str, dict]:
    out = {}
    for r in _read("tariff_states.csv"):
        for k in ("fixed_charge_inr_month", "fuel_surcharge_inr_kwh", "electricity_duty_pct",
                  "free_units_if_at_or_below", "export_rate_inr_kwh",
                  "state_solar_topup_inr_per_kw", "state_solar_topup_cap_inr"):
            r[k] = float(r[k])
        out[r["state"]] = r
    return out


@lru_cache
def tariff_slabs() -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for r in _read("tariff_slabs.csv"):
        row = {k: (r[k] if k == "state" else float(r[k])) for k in r}
        out.setdefault(r["state"], []).append(row)
    return out


@lru_cache
def emission_factors() -> dict[str, dict]:
    return {r["fuel"]: {**r, "kg_co2_per_unit": float(r["kg_co2_per_unit"])} for r in _read("emission_factors.csv")}


def ef(fuel: str) -> float:
    return emission_factors()[fuel]["kg_co2_per_unit"]


@lru_cache
def appliances() -> dict[tuple[str, str], float]:
    return {(r["appliance"], r["variant"]): float(r["value"]) for r in _read("appliances.csv")}


def appl(appliance: str, variant: str) -> float:
    return appliances()[(appliance, variant)]


@lru_cache
def catalogue() -> dict[str, dict]:
    out = {}
    for r in _read("retrofit_catalogue.csv"):
        for k in ("order_rank", "cost_min_inr", "cost_max_inr", "effect_value", "lifetime_years"):
            r[k] = float(r[k])
        r["order_rank"] = int(r["order_rank"])
        out[r["retrofit_id"]] = r
    return out


@lru_cache
def zone_suitability() -> dict[str, dict[str, str]]:
    return {r["retrofit_id"]: {z: r[z] for z in ZONES} for r in _read("zone_suitability.csv")}


@lru_cache
def subsidy_rules() -> list[dict]:
    rows = _read("subsidy_rules.csv")
    for r in rows:
        for k in ("kw_from", "kw_to", "inr_per_kw", "cap_inr"):
            r[k] = float(r[k])
    return rows


@lru_cache
def finance_products() -> list[dict]:
    rows = _read("finance_products.csv")
    for r in rows:
        for k in ("max_amount_inr", "rate_pct", "tenure_years", "min_kw", "max_kw"):
            r[k] = float(r[k])
    return rows


# Monthly PV output shape for India (fraction of annual), drier pre-monsoon peak, monsoon dip.
PV_MONTH_SHAPE = (0.080, 0.084, 0.096, 0.097, 0.097, 0.080, 0.068, 0.070, 0.078, 0.086, 0.082, 0.082)
# Benchmark annual energy intensity (grid + LPG kWh per m2 carpet area): median of complete-data homes per
# zone in the synthetic population (data/reference/benchmarks.csv, written by scripts/generate_data.py),
# the Indian stand-in for NEED medians. Defaults below are used before the first data build.
_DEFAULT_BENCHMARK = {"hot_dry": 60.0, "warm_humid": 62.0, "composite": 60.0, "temperate": 48.0, "cold": 52.0}


def _load_benchmarks() -> dict[str, float]:
    p = REF_DIR / "benchmarks.csv"
    if not p.exists():
        return dict(_DEFAULT_BENCHMARK)
    return {r["zone"]: float(r["median_kwh_m2"]) for r in _read("benchmarks.csv")}


ZONE_BENCHMARK_KWH_M2 = _load_benchmarks()
LPG_KWH_PER_CYLINDER = 14.2 * 13.6  # 14.2 kg cylinder x 13.6 kWh/kg net calorific value ~ 193 kWh
LPG_PRICE_INR_PER_CYLINDER = 853.0  # 14.2 kg domestic cylinder, Delhi (Apr 2025 revision); verify current price
