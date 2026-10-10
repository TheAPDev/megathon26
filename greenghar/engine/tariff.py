"""Slab-aware electricity bills. Savings are always bill(before) - bill(after), month by month,
so each saved unit is priced at the household's real marginal slab, including free-unit schemes."""
from __future__ import annotations

from ..reference import tariff_slabs, tariff_states


def _structure(state: str, units: float) -> list[dict]:
    """Slabs for the consumption category the month falls in (e.g. Telangana switches at 200 units)."""
    rows = [r for r in tariff_slabs()[state] if r["structure_min_units"] <= units < r["structure_max_units"]]
    return sorted(rows, key=lambda r: r["slab_from"])


def energy_charge(state: str, units: float) -> float:
    units = max(0.0, units)
    total = 0.0
    for r in _structure(state, units):
        lo, hi = r["slab_from"], r["slab_to"]
        if units > lo:
            total += (min(units, hi) - lo) * r["rate_inr_kwh"]
    return total


def monthly_bill(state: str, units: float, apply_subsidy: bool = True) -> float:
    """Bill in INR for one month of billed units (after net metering)."""
    st = tariff_states()[state]
    units = max(0.0, units)
    energy = energy_charge(state, units)
    fuel = units * st["fuel_surcharge_inr_kwh"]
    bill = (energy + fuel + st["fixed_charge_inr_month"]) * (1 + st["electricity_duty_pct"] / 100)
    if apply_subsidy:
        free = st["free_units_if_at_or_below"]
        if free and units <= free:
            return 0.0
        if state == "Delhi" and 200 < units <= 400:
            bill -= min(800.0, 0.5 * bill)
    return round(bill, 2)


def marginal_rate(state: str, units: float) -> float:
    """INR per extra unit at this consumption level, before free-unit subsidies (includes duty)."""
    return round((monthly_bill(state, units + 10, apply_subsidy=False) - monthly_bill(state, units, apply_subsidy=False)) / 10, 2)


def annual_bill(state: str, monthly_import: list[float], monthly_export: list[float] | None = None,
                net_metered: bool = False) -> dict:
    """Annual bill with optional net metering (monthly netting, surplus credited at the export rate)."""
    st = tariff_states()[state]
    monthly_export = monthly_export or [0.0] * 12
    bills, credit = [], 0.0
    for imp, exp in zip(monthly_import, monthly_export):
        if net_metered:
            billed = max(0.0, imp - exp)
            credit += max(0.0, exp - imp) * st["export_rate_inr_kwh"]
        else:
            billed = imp
        bills.append(monthly_bill(state, billed))
    total = sum(bills)
    return {"annual_bill_inr": round(total, 0), "export_credit_inr": round(credit, 0),
            "net_annual_cost_inr": round(total - credit, 0), "monthly_bills_inr": [round(b, 0) for b in bills],
            "near_zero_bill": total < 1200}


def free_units_state(state: str) -> float:
    return tariff_states()[state]["free_units_if_at_or_below"]
