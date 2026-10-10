"""Load the canonical Python dataset (data/generated/*.parquet, H/C ids) into Supabase with COPY.

    SUPABASE_DB_URL=postgresql://postgres:<pw>@db.<ref>.supabase.co:5432/postgres python scripts/push_to_supabase.py

The database already holds an in-database population (HD/CD ids) built by synth.generate(); this script adds the
Python population alongside it so the API in GG_REPO=supabase mode serves exactly the homes the models were trained on.
Idempotent: rows are upserted on their primary keys.
"""
from __future__ import annotations

import io
import json
import os
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
GEN = ROOT / "data" / "generated"

HOME_COLS = ["home_id", "customer_id", "city", "state", "zone", "lat", "lon", "dwelling_type", "floor_position", "tenure", "carpet_area_m2",
             "occupants", "building_age_years", "roof_area_m2", "roof_access", "wall_type", "window_to_wall", "west_glass", "shading",
             "cool_roof", "roof_insulation", "solar_film", "n_ac", "ac_tech", "ac_star", "ac_age_years", "ac_tonnage", "ac_setpoint_c",
             "n_coolers", "n_fans", "bldc_fan_share", "fridge_star", "fridge_age_years", "light_points", "led_share", "water_heating",
             "cooking", "lpg_cylinders_per_year", "pv_kw", "net_metered", "backup", "outage_hours_month", "smart_meter", "tod_tariff",
             "smart_plugs", "bee_star_label", "sanctioned_load_kw", "income_band", "wfh", "data_source", "missing_pattern",
             "has_retrofit_history", "kwh_24m"]


def pg_array(v) -> str:
    if v is None:
        return None
    return "{" + ",".join("NULL" if x is None or x != x else repr(float(x)) for x in v) + "}"


def copy(cur, table: str, df: pd.DataFrame, conflict: str) -> None:
    tmp = f"tmp_{table}"
    cur.execute(f"create temp table {tmp} (like public.{table} including defaults) on commit drop")
    buf = io.StringIO()
    df.to_csv(buf, index=False, header=False, na_rep="\\N")
    buf.seek(0)
    cols = ",".join(df.columns)
    with cur.copy(f"copy {tmp} ({cols}) from stdin with (format csv, null '\\N')") as cp:
        cp.write(buf.read())
    cur.execute(f"insert into public.{table} ({cols}) select {cols} from {tmp} on conflict ({conflict}) do nothing")
    print(table, cur.rowcount, "rows inserted")


def main() -> None:
    import psycopg
    url = os.environ.get("SUPABASE_DB_URL") or sys.exit("Set SUPABASE_DB_URL")
    homes = pd.read_parquet(GEN / "homes.parquet")
    cust = pd.read_parquet(GEN / "customers.parquet")
    homes["customer_id"] = homes["home_id"].str.replace("H", "C", n=1)
    homes["kwh_24m"] = homes["kwh_24m"].map(lambda v: pg_array(list(v)) if v is not None else None)
    ev = pd.read_parquet(GEN / "retrofit_events.parquet")
    ev["completed_month"] = ev["completed_month"] + "-01"
    sales = pd.read_parquet(GEN / "sales.parquet")
    sales["sale_month"] = sales["sale_month"] + "-01"
    mem = pd.read_parquet(GEN / "memory.parquet")
    scores = pd.read_parquet(GEN / "home_scores.parquet")
    with psycopg.connect(url, autocommit=False) as conn, conn.cursor() as cur:
        copy(cur, "customers", cust.drop(columns=["home_id"]), "customer_id")
        copy(cur, "homes", homes[HOME_COLS], "home_id")
        copy(cur, "retrofit_events", ev[["event_id", "home_id", "retrofit_id", "completed_month", "cost_inr", "financed", "true_annual_kwh_saving"]], "event_id")
        copy(cur, "sales", sales[["sale_id", "home_id", "sale_month", "price_inr", "score_at_sale"]], "sale_id")
        mem2 = mem.assign(value=mem["value"].map(lambda v: json.dumps(json.loads(v))))
        copy(cur, "memory", mem2[["memory_id", "customer_id", "home_id", "kind", "key", "value"]], "memory_id")
        sc = scores.rename(columns={"package_saving_inr": "package_saving_inr"}).assign(engine="python", engine_version="greenghar 1.0")
        cols = ["home_id", "score", "raw_score", "band", "confidence", "annual_grid_kwh", "annual_estimated", "intensity_kwh_m2",
                "s_energy_efficiency", "s_consumption_intensity", "s_envelope", "s_cooling_system", "s_windows_shading", "s_renewables",
                "s_smart_use", "weakest_component", "warnings", "improvement_potential_pct", "package_saving_inr", "package_co2_saving_kg",
                "baseline_co2_kg", "score_after_package", "package_retrofits", "engine", "engine_version"]
        copy(cur, "home_scores", sc[cols], "home_id")
        conn.commit()


if __name__ == "__main__":
    main()
