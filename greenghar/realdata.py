"""Real public data layer, offline mode.

The full layer lives in Supabase (schema `realdata`, migrations 012-019): Census 2011, NFHS-5 (states and districts),
OWID energy/CO2, WRI power plants, Open-Meteo daily weather 2024-26, NASA POWER climatology and World Bank WDI.
Locally (GG_REPO=local) we rebuild the parts that need no network from the raw CSVs in data/real/raw
(`python scripts/fetch_real_data.py`): the state profile and the synthetic-vs-real calibration. Weather-based
outputs need the database.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

import pandas as pd

RAW = Path(__file__).resolve().parent.parent / "data" / "real" / "raw"

SOURCES = [
    {"source_id": "census2011_districts", "title": "Census of India 2011: district households, amenities and assets", "publisher": "ORGI", "licence": "Government Open Data",
     "url": "https://raw.githubusercontent.com/nishusharma1608/India-Census-2011-Analysis/master/india-districts-census-2011.csv"},
    {"source_id": "nfhs5_states", "title": "NFHS-5 state fact sheets", "publisher": "IIPS / MoHFW", "licence": "CC BY 4.0",
     "url": "https://raw.githubusercontent.com/pratapvardhan/NFHS-5/master/NFHS-5-States.csv"},
    {"source_id": "nfhs5_districts", "title": "NFHS-5 district fact sheets", "publisher": "IIPS / MoHFW", "licence": "CC BY 4.0",
     "url": "https://raw.githubusercontent.com/pratapvardhan/NFHS-5/master/NFHS-5-Districts.csv"},
    {"source_id": "owid_energy", "title": "Our World in Data energy dataset (India)", "publisher": "Our World in Data", "licence": "CC BY 4.0",
     "url": "https://raw.githubusercontent.com/owid/energy-data/master/owid-energy-data.csv"},
    {"source_id": "owid_co2", "title": "Our World in Data CO2 dataset (India)", "publisher": "Our World in Data", "licence": "CC BY 4.0",
     "url": "https://raw.githubusercontent.com/owid/co2-data/master/owid-co2-data.csv"},
    {"source_id": "wri_gppd", "title": "Global Power Plant Database (India)", "publisher": "World Resources Institute", "licence": "CC BY 4.0",
     "url": "https://raw.githubusercontent.com/wri/global-power-plant-database/master/output_database/global_power_plant_database.csv"},
    {"source_id": "open_meteo_archive", "title": "Open-Meteo historical weather (ERA5), daily, 43 cities", "publisher": "Open-Meteo / ECMWF", "licence": "CC BY 4.0",
     "url": "https://archive-api.open-meteo.com/v1/archive"},
    {"source_id": "nasa_power", "title": "NASA POWER monthly climatology, 43 cities", "publisher": "NASA LaRC", "licence": "Public domain",
     "url": "https://power.larc.nasa.gov/api/temporal/climatology/point"},
    {"source_id": "worldbank_wdi", "title": "World Bank WDI: India", "publisher": "World Bank", "licence": "CC BY 4.0",
     "url": "https://api.worldbank.org/v2/country/IND/indicator"},
]

TELANGANA_2011 = {"ADILABAD", "NIZAMABAD", "KARIMNAGAR", "MEDAK", "HYDERABAD", "RANGAREDDY", "MAHBUBNAGAR", "NALGONDA", "WARANGAL", "KHAMMAM"}


def norm_state(s: str) -> str:
    u = str(s).strip().upper()
    if u in ("NCT OF DELHI", "NCT DELHI", "DELHI"):
        return "Delhi"
    if u in ("ORISSA", "ODISHA"):
        return "Odisha"
    if u in ("PONDICHERRY", "PUDUCHERRY"):
        return "Puducherry"
    if u.startswith("ANDAMAN"):
        return "Andaman and Nicobar Islands"
    if u.startswith("DADRA") or u.startswith("DAMAN"):
        return "Dadra and Nagar Haveli and Daman and Diu"
    return u.replace("&", "AND").title().replace(" And ", " and ")


@lru_cache(maxsize=1)
def state_profiles() -> pd.DataFrame:
    """Same definitions as realdata.state_profile (Census + NFHS-5 parts)."""
    c = pd.read_csv(RAW / "census2011_districts.csv").copy()
    c["state"] = [("Telangana" if s.upper() == "ANDHRA PRADESH" and d.upper() in TELANGANA_2011 else norm_state(s))
                  for s, d in zip(c["State name"], c["District name"])]
    sizes = {"Household_size_1_person_Households": 1, "Household_size_2_persons_Households": 2, "Household_size_3_persons_Households": 3,
             "Household_size_4_persons_Households": 4, "Household_size_5_persons_Households": 5,
             "Household_size_6_8_persons_Households": 6.8, "Household_size_9_persons_and_above_Households": 10}
    g = c.groupby("state")
    hh = g["Households"].sum()
    out = pd.DataFrame({
        "population": g["Population"].sum(), "households": hh,
        "urban_hh_pct": 100 * g["Urban_Households"].sum() / hh,
        "electric_lighting_pct_2011": 100 * g["Housholds_with_Electric_Lighting"].sum() / hh,
        "lpg_png_pct_2011": 100 * g["LPG_or_PNG_Households"].sum() / hh,
        "owned_pct_2011": 100 * g["Ownership_Owned_Households"].sum() / (g["Ownership_Owned_Households"].sum() + g["Ownership_Rented_Households"].sum()),
        "dilapidated_pct_2011": 100 * g["Condition_of_occupied_census_houses_Dilapidated_Households"].sum() / hh,
        "computer_pct_2011": 100 * g["Households_with_Computer"].sum() / hh,
        "car_pct_2011": 100 * g["Households_with_Car_Jeep_Van"].sum() / hh,
        "tv_pct_2011": 100 * g["Households_with_Television"].sum() / hh,
        "mean_hh_size_2011": sum(g[k].sum() * v for k, v in sizes.items()) / sum(g[k].sum() for k in sizes),
        "hh_above_330k_pct_2011": 100 * (g["Power_Parity_Rs_330000_545000"].sum() + g["Power_Parity_Above_Rs_545000"].sum()) / g["Total_Power_Parity"].sum(),
        "hh_above_545k_pct_2011": 100 * g["Power_Parity_Above_Rs_545000"].sum() / g["Total_Power_Parity"].sum(),
    })
    n = pd.read_csv(RAW / "nfhs5_states.csv")
    n["no"] = n["indicator"].str.extract(r"^(\d+)\.")[0].astype(float)
    n["state"] = [s if s == "India" else norm_state(s) for s in n["state"]]
    pick = {(7, "nfhs5_total"): "electricity_pct", (7, "nfhs5_urban"): "electricity_urban_pct", (10, "nfhs5_total"): "clean_cooking_pct",
            (10, "nfhs5_urban"): "clean_cooking_urban_pct", (10, "nfhs4_total"): "clean_cooking_pct_nfhs4",
            (9, "nfhs5_urban"): "improved_sanitation_urban_pct", (12, "nfhs5_total"): "health_insurance_pct",
            (18, "nfhs5_urban"): "women_internet_urban_pct", (19, "nfhs5_urban"): "men_internet_urban_pct"}
    for (no, col), name in pick.items():
        v = n[n["no"] == no].set_index("state")[col]
        out = out.join(pd.to_numeric(v, errors="coerce").rename(name), how="outer")
    out = out.drop(index="India", errors="ignore").round(2)
    out.index.name = "state"
    return out


def _clean(d: dict) -> dict:
    return {k: (None if pd.isna(v) else (round(float(v), 2) if isinstance(v, float) else (int(v) if hasattr(v, "item") else v)))
            for k, v in d.items()}


def available() -> bool:
    return (RAW / "census2011_districts.csv").exists() and (RAW / "nfhs5_states.csv").exists()


def state_profile(state: str) -> Optional[dict]:
    if not available():
        return None
    df = state_profiles()
    return {"state": state, **_clean(df.loc[state].to_dict())} if state in df.index else None


def synth_vs_real(homes: pd.DataFrame) -> list[dict]:
    if not available():
        return []
    prof = state_profiles()
    h = homes.copy()
    h["clean"] = h["cooking"].isin(["lpg", "png", "induction"])
    h["owned"] = h["tenure"].eq("owner")
    h["upper"] = h["income_band"].isin(["upper_middle", "high"])
    g = h.groupby("state")
    s = pd.DataFrame({"homes": g.size(), "synth_clean_cooking_pct": 100 * g["clean"].mean(), "synth_owned_pct": 100 * g["owned"].mean(),
                      "synth_mean_occupants": g["occupants"].mean(), "synth_upper_income_pct": 100 * g["upper"].mean()})
    real = prof[["clean_cooking_urban_pct", "owned_pct_2011", "mean_hh_size_2011", "hh_above_330k_pct_2011"]]
    s = s.join(real.rename(columns=lambda c: f"real_{c}"))  # same names as realdata.synth_vs_real_state
    s["gap_clean_cooking_pp"] = s["synth_clean_cooking_pct"] - s["real_clean_cooking_urban_pct"]
    s["gap_owned_pp"] = s["synth_owned_pct"] - s["real_owned_pct_2011"]
    s["gap_hh_size"] = s["synth_mean_occupants"] - s["real_mean_hh_size_2011"]
    s = s.round(2).sort_values("homes", ascending=False).reset_index()
    return [_clean(r) for r in s.to_dict("records")]
