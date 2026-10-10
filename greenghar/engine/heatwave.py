"""Heatwave mode: before summer, show how many degrees a cool roof or shading takes off the indoor
peak and how many AC hours it avoids in April-June.

Indoor peak reductions are literature-based ranges for Indian top-floor RCC homes (cool roof
coatings typically 1.5-3.5 C; over-deck insulation 1.5-3 C; external shading 0.5-1.5 C), shown as ranges.
AC hours come from the same physics model as everything else.
"""
from __future__ import annotations

from ..reference import DAYS_IN_MONTH, city
from ..schemas import Home
from . import retrofits as R
from .physics import AC_COOLING_BASE_C, AC_HOURS_PER_DEGREE, AC_MAX_HOURS_DAY, envelope_cooling_factor, setpoint_factor

INDOOR_PEAK_DROP_C = {"cool_roof": (1.5, 3.5), "roof_insulation": (1.5, 3.0), "external_shading": (0.5, 1.5), "solar_film": (0.3, 1.0)}
SUMMER = (3, 4, 5)  # Apr, May, Jun (0-based)


def ac_hours_summer(home: Home) -> float:
    c = city(home.city)
    env, sp = envelope_cooling_factor(home), setpoint_factor(home.ac_setpoint_c)
    total = 0.0
    for m in SUMMER:
        cdd = max(0.0, c.temps[m] - AC_COOLING_BASE_C) * DAYS_IN_MONTH[m]
        total += min(AC_MAX_HOURS_DAY * DAYS_IN_MONTH[m], AC_HOURS_PER_DEGREE * cdd * env * sp)
    return total * max(1, home.n_ac)


def heatwave_report(home: Home) -> dict:
    c = city(home.city)
    base_hours = ac_hours_summer(home)
    measures = []
    for rid, (lo, hi) in INDOOR_PEAK_DROP_C.items():
        if R.already_done(home, rid):
            continue
        suit, reason = R.feasibility(home, rid)
        if suit == "Infeasible":
            measures.append({"retrofit_id": rid, "suitability": suit, "reason": reason})
            continue
        after = ac_hours_summer(R.apply(home, rid))
        measures.append({"retrofit_id": rid, "suitability": suit, "indoor_peak_drop_c": [lo, hi],
                         "ac_hours_avoided_apr_jun": round(base_hours - after) if home.n_ac else 0,
                         "cost_inr": list(R.cost_range(home, rid)), "reason": reason})
    return {"home_id": home.home_id, "city": home.city, "zone": c.zone,
            "summer_mean_temp_c": round(sum(c.temps[m] for m in SUMMER) / 3, 1),
            "ac_hours_apr_jun": round(base_hours), "has_ac": home.n_ac > 0, "measures": measures,
            "advice": "Do roof and shading work before May; set ACs to 24 C or higher.",
            "estimated": True}
