"""Turns whatever metered data we have into a 12-month profile, honestly labelled.

- 12 months present: used as-is.
- 6-11 months present: annualised with seasonal weights from the home's modelled monthly shape.
- <6 months or none: predicted (ML model if loaded, else the physics model), flagged as estimated.
Missing months are never filled with zero.
"""
from __future__ import annotations

from typing import Callable, Optional

from ..schemas import Home
from .physics import modeled_energy

_predictor: Optional[Callable[[Home], float]] = None  # annual grid kWh predictor (ML), set at startup


def set_energy_predictor(fn: Optional[Callable[[Home], float]]) -> None:
    global _predictor
    _predictor = fn


def predicted_annual(home: Home) -> tuple[float, str]:
    if _predictor is not None:
        try:
            return float(_predictor(home)), "ml_model"
        except Exception:  # model unavailable for this input; fall back to physics, but say so
            pass
    return modeled_energy(home).grid_import, "physics_model"


def profile(home: Home) -> dict:
    model_monthly = modeled_energy(home).monthly_grid_import
    shape_total = sum(model_monthly) or 1.0
    shape = [m / shape_total for m in model_monthly]
    obs = list(home.monthly_kwh or [None] * 12)
    reasons: list[str] = []
    # Reading errors (e.g. OCR dropped or added a digit): a month whose implied annual use is >4x or <1/4 of
    # the median implied annual use is excluded and reported, not silently used.
    implied = sorted(obs[i] / shape[i] for i in range(12) if obs[i] is not None and shape[i] > 0)
    if len(implied) >= 4:
        med = implied[len(implied) // 2]
        bad = [i for i in range(12) if obs[i] is not None and shape[i] > 0 and med > 0
               and not (med / 4 <= obs[i] / shape[i] <= med * 4)]
        for i in bad:
            obs[i] = None
        if bad:
            reasons.append(f"{len(bad)} month(s) look like meter/bill reading errors and were excluded")
    present = [i for i, v in enumerate(obs) if v is not None]
    if len(present) == 12:
        monthly = [float(v) for v in obs]
        return {"monthly": monthly, "annual": sum(monthly), "estimated": False, "months_observed": 12,
                "method": "metered_12_months", "reasons": reasons}
    if len(present) >= 6:
        observed_sum = sum(obs[i] for i in present)
        annual = observed_sum / sum(shape[i] for i in present)
        monthly = [float(obs[i]) if obs[i] is not None else annual * shape[i] for i in range(12)]
        reasons.append(f"{12 - len(present)} of 12 months missing; annualised with seasonal weights")
        return {"monthly": monthly, "annual": annual, "estimated": True, "months_observed": len(present),
                "method": "annualised_seasonal", "reasons": reasons}
    annual, method = predicted_annual(home)
    monthly = [annual * s for s in shape]
    reasons.append("Fewer than 6 months of usage data; annual use is predicted from home characteristics"
                   if present else "No usage data; annual use is predicted from home characteristics")
    return {"monthly": monthly, "annual": annual, "estimated": True, "months_observed": len(present),
            "method": method, "reasons": reasons}


def scaled_after(home_before: Home, home_after: Home, metered_monthly: list[float]) -> list[float]:
    """Apply the model's month-by-month relative change to the metered profile
    (physics gives the shape of the change, the meter gives the level)."""
    b = modeled_energy(home_before).monthly_grid_import
    a = modeled_energy(home_after).monthly_grid_import
    out = []
    for m in range(12):
        if b[m] > 1e-6:
            out.append(max(0.0, metered_monthly[m] * a[m] / b[m]))
        else:
            out.append(max(0.0, metered_monthly[m] + (a[m] - b[m])))
    return out
