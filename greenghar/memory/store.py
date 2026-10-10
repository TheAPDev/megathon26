"""Customer memory: stated constraints (renting, budget, exclusions, language), completed retrofits and
past advice with accept/reject. Recommendations are filtered by memory and the 'what changed' diff shows
how advice moves as memory builds."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from ..engine.plan import recommend
from ..schemas import Home


def constraints(items: list[dict]) -> dict:
    out: dict = {"exclude": set()}
    for m in items:
        if m.get("kind") != "constraint" and m.get("kind") != "preference":
            continue
        v = m.get("value")
        try:
            v = json.loads(v) if isinstance(v, str) else v
        except (json.JSONDecodeError, TypeError):
            pass
        if m["key"] == "exclude":
            out["exclude"].add(v)
        elif m["key"] == "rejected":
            out["exclude"].add(v)
        elif m["key"] in ("include", "accepted"):  # undo an earlier exclusion (memory is append-only)
            out["exclude"].discard(v)
        elif m["key"] == "budget_inr" and v in (None, 0, "", "none"):
            out.pop("budget_inr", None)  # budget cleared
        else:
            out[m["key"]] = v
    out["exclude"] = sorted(out["exclude"])
    return out


def apply_memory(home: Home, items: list[dict]) -> tuple[Home, dict]:
    c = constraints(items)
    if c.get("tenure") == "renting" and home.tenure != "tenant":
        home = home.model_copy(update={"tenure": "tenant"})
    return home, c


def personalised_plan(home: Home, items: list[dict], ranker=None) -> dict:
    home2, c = apply_memory(home, items)
    recs = recommend(home2, ranker=ranker)
    budget = c.get("budget_inr")
    out = []
    for r in recs:
        d = r.model_dump()
        if r.retrofit_id in c["exclude"]:
            d["suitability"] = "Excluded"
            d["reason"] = "You asked us not to suggest this."
        elif budget is not None and r.suitability != "Infeasible" and r.cost_inr_min > float(budget):
            d["over_budget"] = True
        out.append(d)
    return {"home_id": home.home_id, "constraints": c, "recommendations": out}


def what_changed(before: dict, after: dict) -> dict:
    """Diff two personalised plans (e.g. before and after a new memory item)."""
    b = {r["retrofit_id"]: r for r in before["recommendations"]}
    a = {r["retrofit_id"]: r for r in after["recommendations"]}
    changes = []
    for rid in sorted(set(a) | set(b)):
        rb, ra = b.get(rid), a.get(rid)
        if rb is None:
            changes.append({"retrofit_id": rid, "change": "added"})
        elif ra is None:
            changes.append({"retrofit_id": rid, "change": "removed"})
        else:
            for f in ("suitability", "over_budget"):
                if rb.get(f) != ra.get(f):
                    changes.append({"retrofit_id": rid, "change": f, "from": rb.get(f), "to": ra.get(f)})
    return {"changes": changes, "constraints_before": before["constraints"], "constraints_after": after["constraints"]}


def memory_item(kind: str, key: str, value, home_id: str, customer_id: str) -> dict:
    return {"memory_id": f"M-RT-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}", "customer_id": customer_id,
            "home_id": home_id, "kind": kind, "key": key, "value": json.dumps(value),
            "created_month": datetime.now(timezone.utc).strftime("%Y-%m")}
