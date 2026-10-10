"""Budget-constrained retrofit roadmap: 'You have Rs 50,000: do these 3 now, solar in year 2.'

Each year is a 0/1 knapsack over feasible retrofits (cost in Rs 1,000 units), maximising the chosen
objective within budget, subject to the interaction order: rooftop solar (generation) is only scheduled once every affordable
envelope, controls and cooling item has been scheduled in an earlier year, so panels are never sized before the cooling
load has been cut. Items whose payback exceeds their lifetime are dropped. Items too expensive for any single year's budget are reported as not scheduled.
"""
from __future__ import annotations

from ..reference import catalogue
from ..schemas import Home
from .plan import recommend


def _knapsack(items: list[dict], budget_k: int, key: str) -> list[dict]:
    n = len(items)
    best = [[0.0] * (budget_k + 1) for _ in range(n + 1)]
    for i, it in enumerate(items, 1):
        w, v = it["cost_k"], it[key]
        for b in range(budget_k + 1):
            best[i][b] = best[i - 1][b]
            if w <= b and best[i - 1][b - w] + v > best[i][b]:
                best[i][b] = best[i - 1][b - w] + v
    chosen, b = [], budget_k
    for i in range(n, 0, -1):
        if best[i][b] != best[i - 1][b]:
            chosen.append(items[i - 1])
            b -= items[i - 1]["cost_k"]
    return chosen


def roadmap(home: Home, budget_per_year_inr: float, years: int = 3, objective: str = "inr") -> dict:
    key = {"inr": "saving_inr_year", "co2": "co2_kg_year", "kwh": "saving_kwh_electricity"}[objective]
    recs = [r for r in recommend(home, include_infeasible=False) if r.suitability in ("High", "Medium")
            and getattr(r, key) > 0 and r.retrofit_id != "heat_pump_geyser"
            and (r.payback_years is None or r.payback_years <= catalogue()[r.retrofit_id]["lifetime_years"])]
    pool = [{"retrofit_id": r.retrofit_id, "name": r.name, "order_rank": r.order_rank,
             "cost_inr": (r.cost_inr_min + r.cost_inr_max) / 2,
             "cost_k": max(0, int(round((r.cost_inr_min + r.cost_inr_max) / 2 / 1000))),
             "saving_inr_year": r.saving_inr_year, "co2_kg_year": r.co2_kg_year,
             "saving_kwh_electricity": r.saving_kwh_electricity} for r in recs]
    plan = []
    budget_k = int(budget_per_year_inr // 1000)
    unaffordable = [p for p in pool if p["cost_k"] > budget_k]
    pool = [p for p in pool if p["cost_k"] <= budget_k]
    for year in range(1, years + 1):
        if not pool:
            break
        efficiency_left = [p for p in pool if p["order_rank"] <= 3]  # envelope, controls, cooling first
        eligible = [p for p in pool if p["retrofit_id"] != "rooftop_solar"] if efficiency_left else pool
        chosen = _knapsack(eligible, budget_k, key)
        for p in chosen:
            pool.remove(p)
        plan.append({"year": year, "items": [{k: v for k, v in p.items() if k != "cost_k"} for p in chosen],
                     "spend_inr": round(sum(p["cost_inr"] for p in chosen)),
                     "saving_inr_year": round(sum(p["saving_inr_year"] for p in chosen)),
                     "co2_kg_year": round(sum(p["co2_kg_year"] for p in chosen), 1)})
    pool += unaffordable
    return {"home_id": home.home_id, "budget_per_year_inr": budget_per_year_inr, "objective": objective,
            "years": plan, "not_scheduled": [p["retrofit_id"] for p in pool],
            "note": "Savings per item are incremental in interaction order; estimates, not guarantees."}
