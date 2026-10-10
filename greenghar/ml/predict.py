"""Runtime inference: loads trained models if present and plugs them into the engine.
Everything degrades gracefully: with no models the engine falls back to physics and rules."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

from ..reference import cities
from ..schemas import Home
from .features import VALUE_FEATURES, align_categories, home_frame, prepare

MODEL_DIR = Path(__file__).resolve().parents[2] / "models"


@lru_cache
def _load(name: str):
    p = MODEL_DIR / f"{name}.txt"
    if not p.exists():
        return None, None
    meta_p = MODEL_DIR / f"{name}.json"
    meta = json.loads(meta_p.read_text()) if meta_p.exists() else {}
    return lgb.Booster(model_file=str(p)), meta


@lru_cache
def _boot_models() -> tuple:
    return tuple(lgb.Booster(model_file=str(p)) for p in sorted(MODEL_DIR.glob("value_boot_*.txt")))


def model_versions() -> dict:
    out = {}
    for n in ("energy_hybrid", "ranker", "value_hedonic"):
        _, meta = _load(n)
        out[n] = (meta or {}).get("version", "not trained")
    return out


def predict_annual_kwh(home: Home) -> float:
    booster, meta = _load("energy_hybrid")
    if booster is None:
        raise RuntimeError("energy model not trained")
    X = align_categories(home_frame([home])[meta["features"]], meta["categories"])
    phys = max(50.0, float(X["physics_kwh"].iloc[0]))
    return phys * float(np.exp(booster.predict(X)[0]))


def rank_score(home: Home, rid: str, step: dict, suitability: str) -> float:
    booster, meta = _load("ranker")
    if booster is None:
        return 0.0
    cost = (step["net_cost_inr"][0] + step["net_cost_inr"][1]) / 2
    from ..reference import catalogue
    row = {"retrofit_id": rid, "suit_ord": {"Low": 1, "Medium": 2, "High": 3}[suitability],
           "order_rank": catalogue()[rid]["order_rank"], "cost_mid": cost, "pred_inr": step["saving_inr_year"],
           "pred_kwh_hybrid": step["saving_kwh_electricity"], "pred_lpg": step["saving_kwh_lpg"],
           "pred_roi": step["saving_inr_year"] / cost if cost > 0 else step["saving_inr_year"] / 1000,
           "zone": cities()[home.city].zone, "dwelling_type": home.dwelling_type, "n_ac": home.n_ac,
           "income_band": home.income_band, "wfh": int(home.wfh), "building_age_years": home.building_age_years or 15,
           "tenure": home.tenure, "occupants": home.occupants}
    X = align_categories(prepare(pd.DataFrame([row]), meta["features"]), meta["categories"])
    return float(booster.predict(X)[0])


def _value_X(home: Home, score: float) -> pd.DataFrame:
    c = cities()[home.city]
    row = {"city": home.city, "zone": c.zone, "city_tier": c.tier, "dwelling_type": home.dwelling_type,
           "floor_position": home.floor_position, "carpet_area_m2": home.carpet_area_m2, "age_at_sale": home.building_age_years or 15,
           "month_offset": 0, "score": score, "city_price_per_sqft": c.price_per_sqft}
    _, meta = _load("value_hedonic")
    return align_categories(prepare(pd.DataFrame([row]), VALUE_FEATURES), meta["categories"])


def value_range(home: Home, score_before: float, score_after: float | None = None) -> dict:
    booster, meta = _load("value_hedonic")
    if booster is None:
        return {"available": False, "reason": "Value model not trained"}
    if not home.carpet_area_m2:
        return {"available": False, "reason": "Carpet area is missing, so a value estimate would be invented. Add the carpet area to get one."}
    if home.city not in cities():
        return {"available": False, "reason": "No price data for this city"}
    q = meta["conformal_q_log"]
    lp = float(booster.predict(_value_X(home, score_before))[0])
    out = {"available": True, "label": "Indicative, not proven causal",
           "current_value_inr": round(float(np.exp(lp)), -4),
           "current_value_range_inr": [round(float(np.exp(lp - q)), -4), round(float(np.exp(lp + q)), -4)],
           "interval": f"{int((1 - meta['alpha']) * 100)}% split-conformal interval"}
    if score_after is not None and score_after > score_before:
        ups = []
        xa, xb = _value_X(home, score_after), _value_X(home, score_before)
        for mb in _boot_models():
            ups.append(float(np.exp(mb.predict(xa)[0] - mb.predict(xb)[0]) - 1))
        main_up = float(np.exp(booster.predict(_value_X(home, score_after))[0] - lp) - 1)
        lo, hi = (np.percentile(ups, 10), np.percentile(ups, 90)) if ups else (main_up * 0.5, main_up * 1.5)
        out["uplift_pct"] = round(100 * main_up, 1)
        out["uplift_range_pct"] = [round(100 * max(0.0, lo), 1), round(100 * max(0.0, hi), 1)]
        out["method"] = "Counterfactual: same home predicted at the current and post-retrofit score, everything else fixed"
        out["caveat"] = ("No public Indian data links energy ratings to sale prices; this premium is learnt from synthetic sales with a "
                         "disclosed assumption and is only a sanity-checked, indicative range.")
    return out


def install() -> dict:
    """Plug trained models into the engine (call at API startup)."""
    from ..engine.consumption import set_energy_predictor
    if _load("energy_hybrid")[0] is not None:
        set_energy_predictor(predict_annual_kwh)
    return model_versions()
