"""Bias check: score distribution and energy-model error by climate zone, dwelling type, tenure and income band.

    python scripts/bias_report.py   -> reports/bias_report.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from greenghar.data_access import DATA_DIR, row_to_home  # noqa: E402
from greenghar.ml.predict import predict_annual_kwh  # noqa: E402
from greenghar.ml.train import split_ids  # noqa: E402

GROUPS = ["zone", "dwelling_type", "tenure", "income_band"]


def main() -> None:
    homes = pd.read_parquet(DATA_DIR / "homes.parquet")
    scores = pd.read_parquet(DATA_DIR / "home_scores.parquet")
    d = homes.merge(scores[["home_id", "score", "improvement_potential_pct"]], on="home_id")
    out = {"score_by_group": {}, "energy_model_mape_by_group": {}}
    for g in GROUPS:
        out["score_by_group"][g] = d.groupby(g).agg(n=("score", "size"), mean_score=("score", "mean"),
                                                    mean_improvement_pct=("improvement_potential_pct", "mean")).round(2).to_dict("index")
    _, _, te = split_ids(homes["home_id"].values)
    t = homes[homes["home_id"].isin(te) & (homes["missing_pattern"] == "complete") & homes["carpet_area_m2"].notna()].sample(3000, random_state=1)
    t = t.assign(y=[sum(k[12:]) for k in t["kwh_24m"]],
                 p=[predict_annual_kwh(row_to_home({**r, "kwh_24m": None})) for r in t.to_dict("records")])
    t["ape"] = (t["p"] - t["y"]).abs() / t["y"]
    for g in GROUPS:
        out["energy_model_mape_by_group"][g] = (t.groupby(g)["ape"].mean() * 100).round(2).to_dict()
    worst = max((v, f"{g}={k}") for g in GROUPS for k, v in out["energy_model_mape_by_group"][g].items())
    best = min((v, f"{g}={k}") for g in GROUPS for k, v in out["energy_model_mape_by_group"][g].items())
    out["summary"] = {"worst_group_mape_pct": worst, "best_group_mape_pct": best,
                      "max_gap_pct_points": round(worst[0] - best[0], 2),
                      "note": "Scores differ by group by design (real efficiency differences); model error gaps above ~5 points warrant review."}
    (ROOT / "reports" / "bias_report.json").write_text(json.dumps(out, indent=2, default=float))
    print(json.dumps(out["summary"], indent=2, default=float))


if __name__ == "__main__":
    main()
