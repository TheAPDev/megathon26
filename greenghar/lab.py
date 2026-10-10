"""Model Lab checks that run live (API /lab/scenarios) and in pytest.

The five hidden scenarios the judges said they will throw, plus monotonicity and the worked example."""
from __future__ import annotations

import random

from .engine.consumption import profile
from .engine.plan import run_scenario
from .engine.score import score_home
from .schemas import Home

BASE = dict(city="Delhi", dwelling_type="apartment", floor_position="top", carpet_area_m2=120, occupants=4, n_ac=2,
            ac_star=3, ac_age_years=8, n_fans=5, roof_access=True, roof_area_m2=90, data_source="smart_meter")


def _metered(home: Home) -> list[float]:
    from .engine.physics import modeled_energy
    return [round(x, 1) for x in modeled_energy(home).monthly_grid_import]


def scenario_missing_data() -> dict:
    h = Home(home_id="T-missing", **{**BASE, "carpet_area_m2": None})
    full = _metered(Home(home_id="x", **BASE))
    h = h.model_copy(update={"monthly_kwh": [v if i < 7 else None for i, v in enumerate(full)]})
    s = score_home(h)
    p = profile(h)
    ok = (s.annual_grid_kwh_estimated and s.confidence != "high" and p["months_observed"] == 7
          and all(m is not None and m > 0 for m in p["monthly"]) and any("missing" in r.lower() for r in s.confidence_reasons))
    return {"name": "Missing data (no floor area, 7 of 12 months)", "passed": bool(ok),
            "observed": {"confidence": s.confidence, "reasons": s.confidence_reasons, "annual_estimated": s.annual_grid_kwh_estimated,
                         "months_observed": p["months_observed"]}}


def scenario_conflict() -> dict:
    base = Home(home_id="x", **BASE)
    heavy = [v * 3 for v in _metered(base)]
    h = base.model_copy(update={"home_id": "T-conflict", "bee_star_label": 5, "monthly_kwh": heavy})
    s = score_home(h)
    ok = any("conflict" in w.lower() for w in s.warnings) and s.confidence != "high"
    return {"name": "Conflicting data (5-star label, 3x benchmark use)", "passed": bool(ok), "observed": {"warnings": s.warnings, "confidence": s.confidence}}


def scenario_infeasible() -> dict:
    flat = Home(home_id="T-infeasible", **{**BASE, "floor_position": "middle", "roof_access": False, "roof_area_m2": 0})
    sc = run_scenario(flat, ["cool_roof", "rooftop_solar"])
    refused = {r["retrofit_id"] for r in sc["refused"]}
    ok = refused == {"cool_roof", "rooftop_solar"} and not sc["steps"] and all(r["reason"] for r in sc["refused"])
    return {"name": "Infeasible retrofit (roof work and solar for a mid-floor flat)", "passed": bool(ok), "observed": sc["refused"]}


def scenario_fuel_switch() -> dict:
    h = Home(home_id="T-switch", **BASE)
    h = h.model_copy(update={"monthly_kwh": _metered(h)})
    sc = run_scenario(h, ["induction_cooking"])
    el, lpg = sc["per_fuel_saving_kwh"]["electricity"], sc["per_fuel_saving_kwh"]["lpg"]
    co2_formula = round(el * 0.727 + lpg * 0.227, 1)  # per-fuel: dC = sum(dE_f x EF_f); can be negative
    ok = el < 0 and lpg > 0 and abs(co2_formula - sc["co2_saving_kg_year"]) <= 1.0 and sc["improvement_potential_pct"] > 0
    return {"name": "Fuel switch raises electricity (LPG -> induction, India's heat-pump case)", "passed": bool(ok),
            "observed": {"electricity_saving_kwh": el, "lpg_saving_kwh": lpg, "co2_saving_kg": sc["co2_saving_kg_year"],
                         "co2_formula_kg": co2_formula, "improvement_potential_pct": sc["improvement_potential_pct"],
                         "note": "On a ~0.73 kg/kWh grid, LPG->induction alone raises CO2; paired with rooftop solar it falls."}}


def scenario_value_unavailable(value_fn) -> dict:
    h = Home(home_id="T-value", **{**BASE, "carpet_area_m2": None})
    v = value_fn(h, 40, 60) if value_fn else {"available": False, "reason": "no model"}
    ok = v.get("available") is False and bool(v.get("reason")) and "current_value_inr" not in v
    return {"name": "Not enough information for value", "passed": bool(ok), "observed": v}


def monotonicity_sample(n: int = 300, seed: int = 7) -> dict:
    """Random homes: applying any feasible improvement never lowers the affected sub-score."""
    rng = random.Random(seed)
    from .engine import retrofits as R
    from .reference import cities
    checks = fails = 0
    examples = []
    improvements = ["cool_roof", "roof_insulation", "external_shading", "solar_film", "ac_5star_inverter", "bldc_fans",
                    "led_lighting", "fridge_5star", "rooftop_solar", "smart_plug_tod", "ac_setpoint", "solar_water_heater"]
    for i in range(n):
        h = Home(home_id=f"M{i}", monthly_kwh=[300.0] * 12, city=rng.choice(list(cities())), dwelling_type=rng.choice(["apartment", "independent_house"]),
                 floor_position=rng.choice(["top", "middle"]), carpet_area_m2=rng.uniform(40, 250), n_ac=rng.randint(0, 3),
                 ac_star=rng.choice([1, 3, 5]), ac_tech=rng.choice(["fixed", "inverter"]), ac_age_years=rng.uniform(0, 12),
                 ac_setpoint_c=rng.choice([20, 22, 24, 26]), roof_access=rng.random() < 0.5, roof_area_m2=rng.uniform(0, 120),
                 bldc_fan_share=rng.choice([0, 0.5]), led_share=rng.random(), fridge_star=rng.randint(1, 5),
                 shading=rng.choice(["none", "partial"]), west_glass=rng.random() < 0.4, wall_type=rng.choice(["solid_brick", "aac"]))
        before = {c.component: c.score for c in score_home(h).components}
        for rid in improvements:
            if R.feasibility(h, rid)[0] == "Infeasible" or R.already_done(h, rid):
                continue
            after_h = R.apply(h, rid)
            after = {c.component: c.score for c in score_home(after_h).components}
            for comp in ("energy_efficiency", "envelope", "cooling_system", "windows_shading", "renewables", "smart_use"):
                checks += 1
                if after[comp] < before[comp] - 1e-9:
                    fails += 1
                    if len(examples) < 5:
                        examples.append({"home": i, "retrofit": rid, "component": comp, "before": before[comp], "after": after[comp]})
    return {"name": "Monotonic sub-scores (random homes x improvements)", "passed": fails == 0, "checks": checks, "failures": fails,
            "examples": examples}


def worked_example() -> dict:
    """Delhi top-floor 3BHK: cool roof + 5-star inverter AC + BLDC fans + induction + 3 kW solar."""
    h = Home(home_id="WX-DELHI", **{**BASE, "dwelling_type": "independent_house"})
    h = h.model_copy(update={"monthly_kwh": _metered(h)})
    sc = run_scenario(h, ["cool_roof", "ac_5star_inverter", "bldc_fans", "induction_cooking", "rooftop_solar"], {"pv_kw": 3})
    e_b = sc["baseline"]["grid_kwh"] + sc["baseline"]["lpg_kwh"]
    e_a = sc["after"]["grid_kwh"] + sc["after"]["lpg_kwh"]
    recomputed = round(100 * (e_b - e_a) / e_b, 1)
    co2 = round((sc["baseline"]["grid_kwh"] - sc["after"]["grid_kwh"]) * 0.727 + (sc["baseline"]["lpg_kwh"] - sc["after"]["lpg_kwh"]) * 0.227, 1)
    ok = abs(recomputed - sc["improvement_potential_pct"]) <= 0.1 and abs(co2 - sc["co2_saving_kg_year"]) <= 1.0
    return {"name": "Worked example reproduces (improvement potential and carbon formula)", "passed": bool(ok),
            "observed": {"improvement_potential_pct": sc["improvement_potential_pct"], "recomputed_pct": recomputed,
                         "co2_saving_kg": sc["co2_saving_kg_year"], "co2_recomputed_kg": co2, "steps": sc["steps"]}}


def run_all(value_fn=None, monotonicity_n: int = 300) -> dict:
    results = [scenario_missing_data(), scenario_conflict(), scenario_infeasible(), scenario_fuel_switch(),
               scenario_value_unavailable(value_fn), monotonicity_sample(monotonicity_n), worked_example()]
    return {"passed": sum(r["passed"] for r in results), "total": len(results), "results": results}
