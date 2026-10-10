"""Rooftop solar sizing against the home's load, roof and sanctioned load."""
from __future__ import annotations

from ..reference import city
from ..schemas import Home
from . import retrofits as R
from .physics import modeled_energy

EFFICIENCY_FIRST = ("cool_roof", "roof_insulation", "ac_setpoint", "ac_5star_inverter", "bldc_fans", "led_lighting")


def recommend_kw(home: Home, after_efficiency: bool = True) -> float:
    """Size PV to cover the annual load *after* efficiency upgrades, so panels aren't oversized
    for a load that is about to shrink. Rounded to 0.5 kW, minimum 1 kW, capped by the roof."""
    h = home
    if after_efficiency:
        for rid in EFFICIENCY_FIRST:
            if R.feasibility(h, rid)[0] in ("High", "Medium") and not R.already_done(h, rid):
                h = R.apply(h, rid)
    load = modeled_energy(h.model_copy(update={"pv_kw": 0})).total_electric_demand
    yield_ = city(home.city).pv_yield
    kw = load / yield_
    cap = R.max_pv_kw(home)
    kw = min(kw, cap) if cap else kw
    kw = round(max(1.0, kw) * 2) / 2
    return min(kw, cap) if cap else kw


def solar_quote(home: Home, kw: float | None = None) -> dict:
    kw = kw or recommend_kw(home)
    lo, hi = R.cost_range(home, "rooftop_solar", {"pv_kw": kw})
    central = R.central_solar_subsidy(kw)
    state = R.state_solar_topup(city(home.city).state, kw)
    gen = kw * city(home.city).pv_yield
    return {
        "kw": kw, "annual_generation_kwh": round(gen), "roof_needed_m2": round(kw * 10, 1),
        "gross_cost_inr": [lo, hi], "central_subsidy_inr": central, "state_topup_inr": state,
        "net_cost_inr": [max(0.0, lo - central - state), max(0.0, hi - central - state)],
    }
