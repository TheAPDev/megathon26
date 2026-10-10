"""Paisa view: subsidy stack, loan EMI vs monthly bill saving, payback and 25-year savings.
Property value appears only as a wide, caveated range (see ml/value_model.py)."""
from __future__ import annotations

from ..reference import city, finance_products
from ..schemas import Home
from .plan import run_scenario

TARIFF_ESCALATION = 0.03   # assumed nominal tariff growth per year
PV_DEGRADATION = 0.005     # per year


def emi(principal: float, annual_rate_pct: float, years: float) -> float:
    if principal <= 0:
        return 0.0
    n = int(round(years * 12))
    r = annual_rate_pct / 1200
    if r == 0:
        return principal / n
    return principal * r * (1 + r) ** n / ((1 + r) ** n - 1)


def _product(name_prefix: str) -> dict:
    for p in finance_products():
        if p["product"].startswith(name_prefix):
            return p
    raise KeyError(name_prefix)


def finance_plan(home: Home, retrofits: list[str], params: dict | None = None, down_payment_inr: float = 0.0) -> dict:
    sc = run_scenario(home, retrofits, params)
    solar_steps = [s for s in sc["steps"] if s["retrofit_id"] == "rooftop_solar"]
    other_steps = [s for s in sc["steps"] if s["retrofit_id"] != "rooftop_solar"]
    mid = lambda r: (r[0] + r[1]) / 2  # noqa: E731
    solar_net = sum(mid(s["net_cost_inr"]) for s in solar_steps)
    solar_gross = sum(mid(s["cost_inr"]) for s in solar_steps)
    subsidy = sum(s["subsidy_inr"] for s in solar_steps)
    other_cost = sum(mid(s["net_cost_inr"]) for s in other_steps)
    loans = []
    remaining_down = down_payment_inr
    if solar_steps:
        kw = (params or {}).get("pv_kw") or run_scenario(home, ["rooftop_solar"], params)["after"]["pv_generation_kwh"] / city(home.city).pv_yield
        prod = _product("Rooftop solar loan (<=3 kW)" if kw <= 3 else "Rooftop solar loan (3-10 kW)")
        # Subsidy is credited after commissioning, so the loan funds the gross cost and the subsidy prepays it.
        principal = max(0.0, min(prod["max_amount_inr"], solar_gross - remaining_down) - subsidy)
        remaining_down = max(0.0, remaining_down - solar_gross)
        loans.append({"product": prod["product"], "principal_inr": round(principal), "rate_pct": prod["rate_pct"],
                      "tenure_years": prod["tenure_years"], "emi_inr": round(emi(principal, prod["rate_pct"], prod["tenure_years"]))})
    if other_cost > 0:
        principal = max(0.0, other_cost - remaining_down)
        prod = _product("Home-loan top-up") if principal > 60000 else _product("Consumer durable EMI")
        tenure = prod["tenure_years"] if principal > 60000 else 2
        loans.append({"product": prod["product"], "principal_inr": round(principal), "rate_pct": prod["rate_pct"],
                      "tenure_years": tenure, "emi_inr": round(emi(principal, prod["rate_pct"], tenure))})
    total_emi = sum(l["emi_inr"] for l in loans)
    monthly_saving = sc["saving_inr_year"] / 12
    total_net = solar_net + other_cost
    savings_25 = sum(sc["saving_inr_year"] * (1 + TARIFF_ESCALATION) ** y * (1 - PV_DEGRADATION * y if solar_steps else 1) for y in range(25))
    return {
        "home_id": home.home_id, "estimated": True, "retrofits": [s["retrofit_id"] for s in sc["steps"]],
        "refused": sc["refused"],
        "gross_cost_inr": round(solar_gross + other_cost), "subsidy_inr": round(subsidy), "net_cost_inr": round(total_net),
        "loans": loans, "total_emi_inr_month": round(total_emi), "bill_saving_inr_month": round(monthly_saving),
        "emi_covered_by_saving": total_emi <= monthly_saving,
        "simple_payback_years": round(total_net / sc["saving_inr_year"], 1) if sc["saving_inr_year"] > 0 else None,
        "savings_25yr_inr": round(savings_25), "co2_saving_kg_year": sc["co2_saving_kg_year"],
        "near_zero_bill": sc["near_zero_bill"],
        "pivot_note": ("Your bill is already near zero under your state's free-units scheme, so the case rests on comfort, "
                       "backup and export income rather than bill savings.") if sc["near_zero_bill"] else None,
        "assumptions": {"tariff_escalation_pct": TARIFF_ESCALATION * 100, "pv_degradation_pct": PV_DEGRADATION * 100,
                        "rates": "Indicative lender rates; verify current offers"},
    }


def subsidy_navigator(home: Home, kw: float) -> dict:
    """Steps and amounts for PM Surya Ghar; the application itself is pre-filled by the API."""
    from . import retrofits as R
    st = city(home.city).state
    eligible = home.tenure == "owner" and home.roof_access
    return {
        "eligible": eligible,
        "why_not": None if eligible else R.feasibility(home, "rooftop_solar")[1],
        "kw": kw, "central_subsidy_inr": R.central_solar_subsidy(kw), "state_topup_inr": R.state_solar_topup(st, kw),
        "steps": [
            "Register on pmsuryaghar.gov.in with your state, discom and consumer number",
            "Apply for rooftop solar and get the discom's feasibility approval",
            "Choose an MNRE-registered vendor and install the system",
            "Submit plant details and apply for the net meter",
            "Discom inspects and commissions; a commissioning certificate is issued",
            "Submit bank details and a cancelled cheque; subsidy is credited within ~30 days",
        ],
        "documents": ["Latest electricity bill", "Aadhaar", "Proof of roof ownership", "Bank account details"],
    }
