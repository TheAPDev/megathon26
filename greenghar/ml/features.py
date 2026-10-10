"""Feature construction with an explicit allow-list per model (leakage guard).

Anything not available at prediction time is forbidden: metered readings (for the energy model),
sale prices, post-retrofit outcomes, precomputed scores of the target period and the hidden truth table.
tests/test_leakage.py fails if a forbidden column appears in any model's feature list.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..engine.physics import ac_iseer, modeled_energy
from ..reference import cities
from ..schemas import Home

CATEGORICAL = ["zone", "dwelling_type", "floor_position", "tenure", "wall_type", "shading", "ac_tech",
               "water_heating", "cooking", "backup", "income_band", "city"]
NUMERIC = ["carpet_area_m2", "occupants", "building_age_years", "window_to_wall", "n_ac", "ac_star", "ac_age_years",
           "ac_tonnage", "ac_setpoint_c", "n_coolers", "n_fans", "bldc_fan_share", "fridge_star", "fridge_age_years",
           "light_points", "led_share", "lpg_cylinders_per_year", "pv_kw", "outage_hours_month", "sanctioned_load_kw"]
BOOLEAN = ["west_glass", "cool_roof", "roof_insulation", "solar_film", "roof_access", "smart_plugs", "wfh", "smart_meter"]
DERIVED = ["iseer_eff", "physics_kwh", "physics_cooling_kwh", "physics_plug_kwh", "city_tier", "mean_summer_temp"]

ENERGY_FEATURES = CATEGORICAL + NUMERIC + BOOLEAN + DERIVED
FORBIDDEN = {"kwh_24m", "monthly_kwh", "price_inr", "score_at_sale", "true_annual_kwh_saving", "behaviour", "humid_cooling",
             "leak_cooling", "income_plug", "wfh_plug", "wfh_cooling", "tenant_cooling", "annual_grid_kwh", "missing_pattern",
             "carpet_area_true_m2", "data_source", "has_retrofit_history", "bee_star_label"}

VALUE_FEATURES = ["city", "zone", "city_tier", "dwelling_type", "floor_position", "carpet_area_m2", "age_at_sale",
                  "month_offset", "score", "city_price_per_sqft"]


def home_frame(homes: list[Home]) -> pd.DataFrame:
    rows = []
    for h in homes:
        c = cities()[h.city]
        e = modeled_energy(h)
        d = h.model_dump(exclude={"monthly_kwh"})
        d.update({
            "zone": c.zone, "city_tier": c.tier, "iseer_eff": ac_iseer(h) if h.n_ac else 0.0,
            "physics_kwh": e.grid_import, "physics_cooling_kwh": e.cooling, "physics_plug_kwh": e.plug_other,
            "mean_summer_temp": float(np.mean(c.temps[3:6])),
        })
        rows.append(d)
    return prepare(pd.DataFrame(rows), ENERGY_FEATURES)


def prepare(df: pd.DataFrame, features: list[str]) -> pd.DataFrame:
    bad = FORBIDDEN.intersection(features)
    if bad:
        raise ValueError(f"Leakage guard: forbidden features {sorted(bad)}")
    X = df[features].copy()
    for col in X.columns:
        if col in CATEGORICAL or col == "retrofit_id":
            X[col] = X[col].astype(str).astype("category")
        elif pd.api.types.is_bool_dtype(X[col]):
            X[col] = X[col].astype(int)
        else:  # numeric by contract; None -> NaN (LightGBM handles missing natively)
            X[col] = pd.to_numeric(X[col], errors="coerce").astype(float)
    return X


def align_categories(X: pd.DataFrame, categories: dict[str, list]) -> pd.DataFrame:
    for col, cats in categories.items():
        if col in X:
            X[col] = pd.Categorical(X[col].astype(str), categories=cats)
    return X


def category_map(X: pd.DataFrame) -> dict[str, list]:
    return {c: [str(v) for v in X[c].cat.categories] for c in X.columns if str(X[c].dtype) == "category"}
