"""Lender portfolio analytics over precomputed home scores (data/generated/home_scores.parquet or the
Supabase `home_scores` table). Financed emissions use a PCAF-style attribution:
    financed CO2 = annual home CO2 x (loan outstanding / property value at origination)
"""
from __future__ import annotations

import json
from functools import lru_cache

import numpy as np
import pandas as pd

from ..data_access import DATA_DIR
from ..reference import cities


@lru_cache(maxsize=1)
def frame() -> pd.DataFrame:
    s = pd.read_parquet(DATA_DIR / "home_scores.parquet")
    h = pd.read_parquet(DATA_DIR / "homes.parquet", columns=["home_id", "city", "state", "zone", "lat", "lon", "dwelling_type",
                                                              "floor_position", "tenure", "roof_access", "pv_kw", "n_ac", "carpet_area_m2"])
    c = pd.read_parquet(DATA_DIR / "customers.parquet")
    d = s.merge(h, on="home_id").merge(c[["customer_id", "home_id", "has_home_loan", "loan_outstanding_inr", "property_value_inr",
                                           "credit_band", "consent_marketing", "consent_energy_data", "loan_emi_inr", "preferred_language"]], on="home_id")
    d["attribution"] = np.where(d["has_home_loan"], (d["loan_outstanding_inr"] / d["property_value_inr"]).clip(0, 1), 0.0)
    d["financed_co2_kg"] = d["baseline_co2_kg"] * d["attribution"]
    d["financed_co2_reduction_kg"] = d["package_co2_saving_kg"] * d["attribution"]
    # Synthetic housing-society key for apartments (~0.01 deg grid cell within a city)
    d["society_id"] = np.where(d["dwelling_type"] == "apartment",
                               d["city"].str[:3].str.upper() + "-" + (d["lat"] * 100).round().astype(int).astype(str) + "-" + (d["lon"] * 100).round().astype(int).astype(str),
                               None)
    return d


def _filter(d: pd.DataFrame, city: str | None = None, state: str | None = None, loans_only: bool = True) -> pd.DataFrame:
    if loans_only:
        d = d[d["has_home_loan"]]
    if city:
        d = d[d["city"] == city]
    if state:
        d = d[d["state"] == state]
    return d


def summary(city: str | None = None, state: str | None = None) -> dict:
    d = _filter(frame(), city, state)
    bands = ["Highly efficient", "Good", "Moderate", "Poor", "Very poor"]
    hist = np.histogram(d["score"], bins=range(0, 105, 5))
    return {
        "homes_with_loans": int(len(d)), "mean_score": round(float(d["score"].mean()), 1), "median_score": float(d["score"].median()),
        "band_counts": {b: int((d["band"] == b).sum()) for b in bands},
        "poor_or_very_poor_share": round(float(d["band"].isin(["Poor", "Very poor"]).mean()), 4),
        "score_histogram": {"bin_edges": [int(x) for x in hist[1]], "counts": [int(x) for x in hist[0]]},
        "financed_emissions_t_co2": round(float(d["financed_co2_kg"].sum() / 1000), 1),
        "financed_emissions_reduction_potential_t_co2": round(float(d["financed_co2_reduction_kg"].sum() / 1000), 1),
        "loan_book_outstanding_cr": round(float(d["loan_outstanding_inr"].sum() / 1e7), 1),
        "low_confidence_share": round(float((d["confidence"] == "low").mean()), 4),
        "method": "Financed emissions = home CO2 x outstanding / property value (PCAF-style attribution); CEA grid factor",
    }


def poor_homes(limit: int = 50, city: str | None = None, state: str | None = None) -> list[dict]:
    d = _filter(frame(), city, state)
    d = d[d["band"].isin(["Poor", "Very poor"])].sort_values("score").head(limit)
    return [{"home_id": r.home_id, "customer_id": r.customer_id, "city": r.city, "score": int(r.score), "band": r.band,
             "key_issue": r.weakest_component.replace("_", " "), "confidence": r.confidence,
             "warnings": json.loads(r.warnings)} for r in d.itertuples()]


def ranking(limit: int = 50, city: str | None = None, state: str | None = None) -> list[dict]:
    """Rank by improvement potential (% of purchased energy), which uses intensity so big homes aren't penalised."""
    d = _filter(frame(), city, state).sort_values(["improvement_potential_pct", "package_co2_saving_kg"], ascending=False).head(limit)
    return [{"home_id": r.home_id, "customer_id": r.customer_id, "city": r.city, "score": int(r.score),
             "improvement_potential_pct": r.improvement_potential_pct, "score_after_package": int(r.score_after_package),
             "package_saving_inr_year": r.package_saving_inr, "co2_saving_t_year": round(r.package_co2_saving_kg / 1000, 2),
             "financed_co2_reduction_t_year": round(r.financed_co2_reduction_kg / 1000, 3),
             "package": json.loads(r.package_retrofits)} for r in d.itertuples()]


def city_map() -> list[dict]:
    d = _filter(frame())
    g = d.groupby("city").agg(homes=("home_id", "count"), mean_score=("score", "mean"),
                              poor_share=("band", lambda b: b.isin(["Poor", "Very poor"]).mean()),
                              financed_t=("financed_co2_kg", lambda x: x.sum() / 1000),
                              reduction_t=("financed_co2_reduction_kg", lambda x: x.sum() / 1000)).reset_index()
    out = []
    for r in g.itertuples():
        c = cities()[r.city]
        out.append({"city": r.city, "state": c.state, "lat": c.lat, "lon": c.lon, "zone": c.zone, "homes": int(r.homes),
                    "mean_score": round(r.mean_score, 1), "poor_share": round(r.poor_share, 3),
                    "financed_emissions_t": round(r.financed_t, 1), "reduction_potential_t": round(r.reduction_t, 1)})
    return sorted(out, key=lambda x: -x["financed_emissions_t"])


def green_finance_targets(limit: int = 100, city: str | None = None) -> list[dict]:
    """Customers who would benefit from a solar loan or a home-loan top-up: consented, owners, decent credit,
    high improvement potential and a package whose saving can carry the EMI."""
    d = _filter(frame(), city)
    d = d[(d["consent_marketing"]) & (d["tenure"] == "owner") & (d["credit_band"].isin(["A", "B"])) &
          (d["improvement_potential_pct"] >= 40)]
    d = d.assign(offer=np.where(d["roof_access"] & (d["pv_kw"] == 0), "Rooftop solar loan + efficiency top-up", "Efficiency top-up"))
    d = d.sort_values("package_saving_inr", ascending=False).head(limit)
    return [{"customer_id": r.customer_id, "home_id": r.home_id, "city": r.city, "score": int(r.score), "offer": r.offer,
             "package_saving_inr_year": r.package_saving_inr, "improvement_potential_pct": r.improvement_potential_pct,
             "credit_band": r.credit_band, "language": r.preferred_language} for r in d.itertuples()]


def rwa_leads(min_homes: int = 4, limit: int = 50) -> list[dict]:
    """Housing societies where many apartment customers can't install private solar: pooled common-area solar
    under PM Surya Ghar RWA/GHS assistance (Rs 18,000/kW) and one loan for the society."""
    d = frame()
    d = d[(d["dwelling_type"] == "apartment") & d["society_id"].notna()]
    g = d.groupby(["society_id", "city"]).agg(customers=("customer_id", "count"), mean_score=("score", "mean"),
                                               no_roof=("roof_access", lambda x: (~x).sum())).reset_index()
    g = g[g["customers"] >= min_homes].sort_values(["customers", "mean_score"], ascending=[False, True]).head(limit)
    return [{"society_id": r.society_id, "city": r.city, "customers": int(r.customers), "without_private_roof": int(r.no_roof),
             "mean_score": round(r.mean_score, 1), "suggested_common_solar_kw": int(min(500, max(5, r.customers * 1.5))),
             "rwa_subsidy_inr": int(min(500, max(5, r.customers * 1.5)) * 18000)} for r in g.itertuples()]
