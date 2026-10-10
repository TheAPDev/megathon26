"""Batch worker: compute the Python-only parts of the portfolio (improvement potential, full package savings,
CO2) for homes in Supabase and upsert them into home_scores. Run nightly (cron) or after new homes arrive.

    SUPABASE_URL=... SUPABASE_SERVICE_ROLE_KEY=... python scripts/rescore_supabase.py --batch 500
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from greenghar.data_access import row_to_home  # noqa: E402
from greenghar.db.supabase_repo import HOME_COLUMNS, SupabaseRepo  # noqa: E402
from greenghar.engine import retrofits as R  # noqa: E402
from greenghar.engine.plan import ALL_RETROFITS, run_scenario  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", type=int, default=500)
    ap.add_argument("--max", type=int, default=100000)
    a = ap.parse_args()
    repo = SupabaseRepo()
    done = 0
    while done < a.max:
        todo = repo._get("home_scores", {"select": "home_id", "improvement_potential_pct": "is.null", "limit": str(a.batch)})
        if not todo:
            break
        ids = ",".join(t["home_id"] for t in todo)
        rows = repo._get("homes", {"home_id": f"in.({ids})", "select": HOME_COLUMNS})
        out = []
        for r in rows:
            h = row_to_home(r)
            feas = [x for x in ALL_RETROFITS if x != "heat_pump_geyser" and not R.already_done(h, x) and R.feasibility(h, x)[0] != "Infeasible"]
            sc = run_scenario(h, feas)
            out.append({"home_id": h.home_id, "improvement_potential_pct": sc["improvement_potential_pct"] or 0.0,
                        "package_saving_inr": sc["saving_inr_year"], "package_co2_saving_kg": sc["co2_saving_kg_year"],
                        "baseline_co2_kg": sc["baseline"]["co2_kg"], "score_after_package": sc["score_after"],
                        "package_retrofits": json.dumps([s["retrofit_id"] for s in sc["steps"]])})
        for row in out:
            repo.client.patch(f"{repo.url}/home_scores", params={"home_id": f"eq.{row['home_id']}"}, json=row).raise_for_status()
        done += len(out)
        print("updated", done)


if __name__ == "__main__":
    main()
