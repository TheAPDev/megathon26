"""Retrofit plan, what-if scenarios and per-fuel savings.

Retrofits are applied cumulatively in interaction order (envelope -> controls -> cooling -> appliances
-> water / fuel switch -> backup -> generation). Each step's saving is the *incremental* change after the
earlier steps, and package savings are baseline - after-all, never a sum of standalone estimates.
"""
from __future__ import annotations

from ..reference import LPG_KWH_PER_CYLINDER, LPG_PRICE_INR_PER_CYLINDER, catalogue, city, ef
from ..schemas import Home, Recommendation
from . import retrofits as R
from .consumption import profile, scaled_after
from .physics import modeled_energy
from .score import score_home
from .tariff import annual_bill

ALL_RETROFITS = sorted(catalogue(), key=lambda r: (catalogue()[r]["order_rank"], r))
SUIT_W = {"High": 1.0, "Medium": 0.7, "Low": 0.35, "Infeasible": 0.0}


def _ordered(rids: list[str]) -> list[str]:
    unknown = [r for r in rids if r not in catalogue()]
    if unknown:
        raise ValueError(f"Unknown retrofit(s): {unknown}")
    return sorted(dict.fromkeys(rids), key=lambda r: (catalogue()[r]["order_rank"], ALL_RETROFITS.index(r)))


def _state_snapshot(home: Home, metered: list[float], base_home: Home) -> dict:
    grid = scaled_after(base_home, home, metered) if home is not base_home else list(metered)
    e = modeled_energy(home)
    st = city(home.city).state
    # exports scale with the same factor the model applies to imports is not meaningful; use modelled export
    export_m = [0.0] * 12
    if e.pv_generation:
        from ..reference import PV_MONTH_SHAPE
        export_m = [e.pv_exported * s for s in PV_MONTH_SHAPE]
    bill = annual_bill(st, grid, export_m, net_metered=home.net_metered)
    return {"grid_monthly": grid, "grid": sum(grid), "lpg": e.lpg_kwh, "dg": e.dg_kwh,
            "pv_generation": e.pv_generation, "pv_exported": e.pv_exported, "bill": bill}


def _co2(grid: float, lpg: float, dg: float) -> float:
    return grid * ef("grid_electricity") + lpg * ef("lpg") + dg * ef("diesel_dg_set")


def run_scenario(home: Home, retrofits: list[str], params: dict | None = None) -> dict:
    """Engine-only what-if. Infeasible retrofits are refused with a reason, never given a number."""
    params = params or {}
    prof = profile(home)
    metered = prof["monthly"]
    base = _state_snapshot(home, metered, home)
    refused, steps = [], []
    cur = home
    prev = base
    for rid in _ordered(retrofits):
        suit, reason = R.feasibility(cur, rid)
        if suit == "Infeasible":
            refused.append({"retrofit_id": rid, "reason": reason})
            continue
        if R.already_done(cur, rid) and rid not in ("rooftop_solar", "ac_setpoint"):
            refused.append({"retrofit_id": rid, "reason": "Already in place."})
            continue
        nxt = R.apply(cur, rid, params)
        snap = _state_snapshot(nxt, metered, home)
        lo, hi = R.cost_range(cur, rid, params)
        subsidy = 0.0
        if rid == "rooftop_solar":
            kw = nxt.pv_kw - cur.pv_kw
            subsidy = R.central_solar_subsidy(kw) + R.state_solar_topup(city(home.city).state, kw)
        d_grid, d_lpg, d_dg = prev["grid"] - snap["grid"], prev["lpg"] - snap["lpg"], prev["dg"] - snap["dg"]
        d_inr = prev["bill"]["net_annual_cost_inr"] - snap["bill"]["net_annual_cost_inr"]
        lpg_inr = d_lpg / LPG_KWH_PER_CYLINDER * LPG_PRICE_INR_PER_CYLINDER
        steps.append({
            "retrofit_id": rid, "name": catalogue()[rid]["name"],
            "saving_kwh_electricity": round(d_grid, 1), "saving_kwh_lpg": round(d_lpg, 1), "saving_kwh_dg": round(d_dg, 1),
            "saving_inr_year": round(d_inr + lpg_inr, 0), "co2_kg_year": round(_co2(d_grid, d_lpg, d_dg), 1),
            "cost_inr": [lo, hi], "subsidy_inr": subsidy,
            "net_cost_inr": [max(0.0, lo - subsidy), max(0.0, hi - subsidy)],
        })
        cur, prev = nxt, snap
    after = prev
    e_base = base["grid"] + base["lpg"] + base["dg"]
    e_after = after["grid"] + after["lpg"] + after["dg"]
    improvement = None if e_base <= 0 else round(100 * (e_base - e_after) / e_base, 1)
    s_before = score_home(home)
    s_after = score_home(cur, annual_override=after["grid"]) if steps else s_before
    lpg_inr_total = (base["lpg"] - after["lpg"]) / LPG_KWH_PER_CYLINDER * LPG_PRICE_INR_PER_CYLINDER
    return {
        "home_id": home.home_id,
        "estimated": True,
        "baseline": {"grid_kwh": round(base["grid"], 1), "lpg_kwh": round(base["lpg"], 1), "dg_kwh": round(base["dg"], 1),
                     "annual_bill_inr": base["bill"]["net_annual_cost_inr"], "co2_kg": round(_co2(base["grid"], base["lpg"], base["dg"]), 1),
                     "monthly_grid_kwh": [round(x, 1) for x in base["grid_monthly"]]},
        "after": {"grid_kwh": round(after["grid"], 1), "lpg_kwh": round(after["lpg"], 1), "dg_kwh": round(after["dg"], 1),
                  "annual_bill_inr": after["bill"]["net_annual_cost_inr"], "co2_kg": round(_co2(after["grid"], after["lpg"], after["dg"]), 1),
                  "monthly_grid_kwh": [round(x, 1) for x in after["grid_monthly"]],
                  "pv_generation_kwh": round(after["pv_generation"], 1), "pv_exported_kwh": round(after["pv_exported"], 1)},
        "per_fuel_saving_kwh": {"electricity": round(base["grid"] - after["grid"], 1), "lpg": round(base["lpg"] - after["lpg"], 1),
                                "diesel": round(base["dg"] - after["dg"], 1)},
        "saving_inr_year": round(base["bill"]["net_annual_cost_inr"] - after["bill"]["net_annual_cost_inr"] + lpg_inr_total, 0),
        "co2_saving_kg_year": round(_co2(base["grid"], base["lpg"], base["dg"]) - _co2(after["grid"], after["lpg"], after["dg"]), 1),
        "improvement_potential_pct": improvement,
        "score_before": s_before.score, "score_after": s_after.score, "band_after": s_after.band,
        "steps": steps, "refused": refused,
        "near_zero_bill": base["bill"]["near_zero_bill"],
        "data_method": prof["method"],
    }


def recommend(home: Home, include_infeasible: bool = True, ranker=None) -> list[Recommendation]:
    """All retrofits with suitability; feasible ones costed in interaction order (incremental savings)."""
    feasible, recs = [], []
    for rid in ALL_RETROFITS:
        if R.already_done(home, rid):
            continue
        suit, reason = R.feasibility(home, rid)
        if suit == "Infeasible":
            if include_infeasible:
                c = catalogue()[rid]
                recs.append(Recommendation(retrofit_id=rid, name=c["name"], category=c["category"], order_rank=c["order_rank"],
                                           suitability="Infeasible", reason=reason))
            continue
        feasible.append((rid, suit, reason))
    # Exclude mutually exclusive water heating alternative: keep the better-suited one in the package
    rids = [f[0] for f in feasible]
    if "solar_water_heater" in rids and "heat_pump_geyser" in rids:
        rids.remove("heat_pump_geyser")
    sc = run_scenario(home, rids)
    by_id = {s["retrofit_id"]: s for s in sc["steps"]}
    for rid, suit, reason in feasible:
        c = catalogue()[rid]
        s = by_id.get(rid)
        if s is None:  # alternative not in the package: cost it standalone
            alone = run_scenario(home, [rid])["steps"]
            s = alone[0] if alone else None
        if s is None:
            continue
        mid = (s["net_cost_inr"][0] + s["net_cost_inr"][1]) / 2
        payback = round(mid / s["saving_inr_year"], 1) if s["saving_inr_year"] > 0 and mid > 0 else (0.0 if mid == 0 and s["saving_inr_year"] > 0 else None)
        roi = (s["saving_inr_year"] / mid) if mid > 0 else (5.0 if s["saving_inr_year"] > 0 else 0.0)
        rank = SUIT_W[suit] * (min(roi, 5.0) + s["co2_kg_year"] / 2000.0)
        if ranker is not None:
            rank = ranker(home, rid, s, suit)
        recs.append(Recommendation(
            retrofit_id=rid, name=c["name"], category=c["category"], order_rank=c["order_rank"], suitability=suit,
            reason=reason, cost_inr_min=s["net_cost_inr"][0], cost_inr_max=s["net_cost_inr"][1],
            saving_kwh_electricity=s["saving_kwh_electricity"], saving_kwh_lpg=s["saving_kwh_lpg"],
            saving_inr_year=s["saving_inr_year"], co2_kg_year=s["co2_kg_year"], payback_years=payback, rank_score=round(rank, 4)))
    recs.sort(key=lambda r: (r.suitability == "Infeasible", r.order_rank, -r.rank_score))
    return recs
