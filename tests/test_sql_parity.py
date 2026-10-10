"""The Supabase SQL engine (gg.score) and the Python engine agree on homes pulled from the database."""
import json
from pathlib import Path

from greenghar.data_access import row_to_home
from greenghar.engine.score import score_home

FIX = Path(__file__).parent / "fixtures" / "sql_parity_sample.json"


def test_python_matches_sql_scores():
    for x in json.loads(FIX.read_text()):
        s = score_home(row_to_home(x["home"]))
        assert abs(s.raw_score - x["sql_raw"]) < 0.01, x["home"]["home_id"]
        for py, sql in zip([c.score for c in s.components], x["sql_comp"]):
            assert abs(py - sql) < 0.01


def test_python_matches_sql_package_engine():
    """gg.package (migration 009) vs the Python sequential retrofit engine on the same 8 database homes."""
    from greenghar.engine import retrofits as R
    from greenghar.engine.plan import run_scenario
    from greenghar.reference import catalogue
    for x in json.loads(FIX.read_text()):
        home, exp = row_to_home(x["home"]), x["sql_package"]
        feas = [r for r in catalogue() if r != "heat_pump_geyser" and not R.already_done(home, r) and R.feasibility(home, r)[0] != "Infeasible"]
        sc = run_scenario(home, feas)
        hid = home.home_id
        assert [s["retrofit_id"] for s in sc["steps"]] == exp["package_retrofits"], hid
        assert abs(sc["improvement_potential_pct"] - exp["improvement_potential_pct"]) <= 0.1, hid
        assert abs(sc["saving_inr_year"] - exp["package_saving_inr"]) <= 2, hid
        assert abs(sc["co2_saving_kg_year"] - exp["package_co2_saving_kg"]) <= 0.2, hid
        assert abs(sc["baseline"]["co2_kg"] - exp["baseline_co2_kg"]) <= 0.2, hid
        assert sc["score_after"] == exp["score_after_package"], hid
