"""Build the synthetic population, benchmarks and precomputed portfolio scores.

    python scripts/generate_data.py --n 50000 --seed 42
Writes data/generated/*.parquet and data/reference/benchmarks.csv.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from greenghar.synth.generator import GenConfig, generate  # noqa: E402

OUT = ROOT / "data" / "generated"


def _score_chunk(records: list[dict]) -> list[dict]:
    from greenghar.data_access import row_to_home
    from greenghar.engine import retrofits as R
    from greenghar.engine.plan import ALL_RETROFITS, run_scenario
    from greenghar.engine.score import score_home
    out = []
    for r in records:
        home = row_to_home(r)
        s = score_home(home)
        feas = [x for x in ALL_RETROFITS if x != "heat_pump_geyser" and not R.already_done(home, x)
                and R.feasibility(home, x)[0] != "Infeasible"]
        sc = run_scenario(home, feas)
        comp = {c.component: c.score for c in s.components}
        worst = min(comp, key=comp.get)
        out.append({"home_id": home.home_id, "score": s.score, "raw_score": s.raw_score, "band": s.band,
                    "confidence": s.confidence, "annual_grid_kwh": s.annual_grid_kwh, "annual_estimated": s.annual_grid_kwh_estimated,
                    "intensity_kwh_m2": s.intensity_kwh_m2, "warnings": json.dumps(s.warnings),
                    **{f"s_{k}": round(v, 1) for k, v in comp.items()}, "weakest_component": worst,
                    "improvement_potential_pct": sc["improvement_potential_pct"], "package_saving_inr": sc["saving_inr_year"],
                    "package_co2_saving_kg": sc["co2_saving_kg_year"], "baseline_co2_kg": sc["baseline"]["co2_kg"],
                    "score_after_package": sc["score_after"], "package_retrofits": json.dumps([x["retrofit_id"] for x in sc["steps"]])})
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=50_000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--workers", type=int, default=2)
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    t = time.time()
    data = generate(GenConfig(n_homes=a.n, seed=a.seed))
    print(f"generated {a.n} homes in {time.time() - t:.0f}s")
    homes = data["homes"]
    # Benchmarks: median (grid + LPG) kWh/m2 of complete 12-month homes per zone
    from greenghar.engine.physics import modeled_energy
    from greenghar.data_access import row_to_home
    comp = homes[(homes["missing_pattern"] == "complete") & homes["carpet_area_m2"].notna()]
    rows = []
    for zone, g in comp.groupby("zone"):
        vals = []
        for _, r in g.sample(min(len(g), 3000), random_state=a.seed).iterrows():
            lpg = modeled_energy(row_to_home(r)).lpg_kwh
            k = sum(r["kwh_24m"][12:])
            vals.append((k + lpg) / r["carpet_area_m2"] * (1 / 1.1 if r["dwelling_type"] != "apartment" else 1))
        rows.append({"zone": zone, "median_kwh_m2": round(float(np.median(vals)), 1), "n_homes": len(vals),
                     "method": "median (grid+LPG)/m2, complete-data homes, house values deflated by 1.1"})
    pd.DataFrame(rows).to_csv(ROOT / "data" / "reference" / "benchmarks.csv", index=False)
    print(pd.DataFrame(rows))
    for name, df in data.items():
        df.to_parquet(OUT / f"{name}.parquet", index=False)
    # Portfolio scores (benchmarks must be reloaded in workers, which import fresh)
    recs = homes.to_dict("records")
    chunks = [recs[i:i + 500] for i in range(0, len(recs), 500)]
    t = time.time()
    with ProcessPoolExecutor(max_workers=a.workers) as ex:
        scored = [row for part in ex.map(_score_chunk, chunks) for row in part]
    pd.DataFrame(scored).to_parquet(OUT / "home_scores.parquet", index=False)
    print(f"scored {len(scored)} homes in {time.time() - t:.0f}s")
    manifest = {"seed": a.seed, "n_homes": a.n, "tables": {k: len(v) for k, v in data.items()} | {"home_scores": len(scored)},
                "generator": "greenghar.synth.generator", "built_at": pd.Timestamp.now(tz="Asia/Kolkata").isoformat()}
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
