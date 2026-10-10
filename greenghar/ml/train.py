"""Train and evaluate all models against simple baselines on property-grouped splits.

    python -m greenghar.ml.train            (or: make train)

Splits: GroupShuffleSplit on home_id (one customer per home, so this is also a customer split), 70/15/15,
fixed seed. Models are tuned on validation only; test metrics are computed once and written to
reports/eval_report.json. Every model is saved with a content hash so the API can report its version.
"""
from __future__ import annotations

import hashlib
import json
import time
import warnings
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, ndcg_score, r2_score

from ..data_access import DATA_DIR, row_to_home
from ..engine import retrofits as R
from ..engine.physics import modeled_energy
from ..engine.plan import ALL_RETROFITS, run_scenario
from ..engine.tariff import annual_bill
from ..reference import LPG_KWH_PER_CYLINDER, LPG_PRICE_INR_PER_CYLINDER, cities, catalogue
from ..synth.generator import true_monthly_import
from .features import VALUE_FEATURES, category_map, home_frame, prepare

warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", message=".*eval_set.*")
ROOT = Path(__file__).resolve().parents[2]
MODEL_DIR = ROOT / "models"
REPORT_DIR = ROOT / "reports"
SEED = 42


def split_ids(ids: np.ndarray, seed: int = SEED) -> tuple[set, set, set]:
    rng = np.random.default_rng(seed)
    u = np.array(sorted(set(ids)))
    rng.shuffle(u)
    n = len(u)
    a, b = int(0.70 * n), int(0.85 * n)
    return set(u[:a]), set(u[a:b]), set(u[b:])


def mape(y, p) -> float:
    y, p = np.asarray(y), np.asarray(p)
    return float(np.mean(np.abs(p - y) / np.maximum(np.abs(y), 1e-9)) * 100)


def _hash_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:12]


def _metrics(y, p) -> dict:
    return {"MAE_kwh": round(float(mean_absolute_error(y, p)), 1), "MAPE_pct": round(mape(y, p), 2), "R2": round(float(r2_score(y, p)), 4)}


# ---------------------------------------------------------------------------------------------
# 1. Annual energy model (fills missing data, powers estimates for homes without meter data)
# ---------------------------------------------------------------------------------------------

def train_energy(homes: pd.DataFrame, events: pd.DataFrame) -> dict:
    recent = set(events.loc[events["month_index"] >= 12, "home_id"]) if len(events) else set()
    d = homes[(homes["missing_pattern"] == "complete") & (homes["data_source"] != "survey")
              & homes["carpet_area_m2"].notna() & ~homes["home_id"].isin(recent)].copy()
    d["y"] = [float(sum(k[12:])) for k in d["kwh_24m"]]
    objs = [row_to_home({**r, "kwh_24m": None}) for r in d.to_dict("records")]
    X = home_frame(objs)
    X.index = d.index
    tr, va, te = split_ids(d["home_id"].values)
    m_tr, m_va, m_te = d["home_id"].isin(tr), d["home_id"].isin(va), d["home_id"].isin(te)
    y = d["y"]
    phys = X["physics_kwh"]
    # Baseline: median of train by zone x dwelling x AC count (capped at 3)
    key = d["zone"] + "|" + d["dwelling_type"] + "|" + d["n_ac"].clip(upper=3).astype(str)
    med = y[m_tr].groupby(key[m_tr]).median()
    base_pred = key.map(med).fillna(y[m_tr].median())
    # Hybrid: LightGBM learns log(actual / physics)
    params = dict(n_estimators=600, learning_rate=0.05, num_leaves=63, min_child_samples=40, subsample=0.8,
                  subsample_freq=1, colsample_bytree=0.8, random_state=SEED, verbose=-1)
    resid = np.log(y / phys.clip(lower=50))
    hyb = lgb.LGBMRegressor(**params)
    hyb.fit(X[m_tr], resid[m_tr], eval_set=[(X[m_va], resid[m_va])], callbacks=[lgb.early_stopping(50, verbose=False)])
    direct = lgb.LGBMRegressor(**params)
    direct.fit(X[m_tr], np.log(y[m_tr]), eval_set=[(X[m_va], np.log(y[m_va]))], callbacks=[lgb.early_stopping(50, verbose=False)])
    preds = {
        "baseline_median_zone_type_ac": base_pred,
        "physics_only": phys,
        "lightgbm_direct": pd.Series(np.exp(direct.predict(X)), index=X.index),
        "hybrid_physics_x_lightgbm": pd.Series(phys.clip(lower=50) * np.exp(hyb.predict(X)), index=X.index),
    }
    val = {k: _metrics(y[m_va], p[m_va]) for k, p in preds.items()}
    test = {k: _metrics(y[m_te], p[m_te]) for k, p in preds.items()}
    chosen = min(val, key=lambda k: val[k]["MAE_kwh"])
    MODEL_DIR.mkdir(exist_ok=True)
    hyb.booster_.save_model(str(MODEL_DIR / "energy_hybrid.txt"))
    meta = {"features": list(X.columns), "categories": category_map(X), "target": "log(actual/physics)",
            "version": _hash_file(MODEL_DIR / "energy_hybrid.txt")}
    (MODEL_DIR / "energy_hybrid.json").write_text(json.dumps(meta, indent=2))
    contrib = hyb.booster_.predict(X[m_te], pred_contrib=True)
    imp = pd.Series(np.abs(contrib[:, :-1]).mean(axis=0), index=X.columns).sort_values(ascending=False)
    return {"n_train": int(m_tr.sum()), "n_val": int(m_va.sum()), "n_test": int(m_te.sum()), "validation": val, "test": test,
            "selected_on_validation": chosen, "improvement_vs_baseline_test_mae_pct":
                round(100 * (1 - test["hybrid_physics_x_lightgbm"]["MAE_kwh"] / test["baseline_median_zone_type_ac"]["MAE_kwh"]), 1),
            "top_features_mean_abs_shap": {k: round(float(v), 4) for k, v in imp.head(10).items()},
            "version": meta["version"]}


# ---------------------------------------------------------------------------------------------
# 2. Retrofit relevance ranker and savings validation (labels from the ground-truth simulator)
# ---------------------------------------------------------------------------------------------

def _true_saving(home, rid, t) -> dict:
    yf = {m: 1.0 for m in range(12)}
    post = R.apply(home, rid)
    b, a = true_monthly_import(home, t, yf), true_monthly_import(post, t, yf)
    st = cities()[home.city].state
    eb, ea = modeled_energy(home), modeled_energy(post)
    from ..reference import PV_MONTH_SHAPE
    exp_b = [eb.pv_exported * s for s in PV_MONTH_SHAPE] if eb.pv_generation else None
    exp_a = [ea.pv_exported * s for s in PV_MONTH_SHAPE] if ea.pv_generation else None
    bill_b = annual_bill(st, b, exp_b, net_metered=home.net_metered)["net_annual_cost_inr"]
    bill_a = annual_bill(st, a, exp_a, net_metered=post.net_metered)["net_annual_cost_inr"]
    d_lpg = eb.lpg_kwh - ea.lpg_kwh
    inr = bill_b - bill_a + d_lpg / LPG_KWH_PER_CYLINDER * LPG_PRICE_INR_PER_CYLINDER
    return {"true_kwh": sum(b) - sum(a), "true_lpg": d_lpg, "true_inr": inr}


def build_pairs(homes: pd.DataFrame, truth: pd.DataFrame, n_homes: int = 4000) -> pd.DataFrame:
    rng = np.random.default_rng(SEED)
    pool = homes[homes["data_source"] != "survey"]
    sample = pool.iloc[rng.choice(len(pool), size=min(n_homes, len(pool)), replace=False)]
    tmap = truth.set_index("home_id").to_dict("index")
    rows = []
    for r in sample.to_dict("records"):
        home = row_to_home(r)
        t = tmap[home.home_id]
        for rid in ALL_RETROFITS:
            if R.already_done(home, rid):
                continue
            suit, _ = R.feasibility(home, rid)
            if suit == "Infeasible":
                continue
            sc = run_scenario(home, [rid])
            if not sc["steps"]:
                continue
            st = sc["steps"][0]
            cost = (st["net_cost_inr"][0] + st["net_cost_inr"][1]) / 2
            phys_kwh = modeled_energy(home).grid_import - modeled_energy(R.apply(home, rid)).grid_import
            tr = _true_saving(home, rid, t)
            rows.append({"home_id": home.home_id, "retrofit_id": rid, "suitability": suit,
                         "suit_ord": {"Low": 1, "Medium": 2, "High": 3}[suit], "order_rank": catalogue()[rid]["order_rank"],
                         "cost_mid": cost, "pred_inr": st["saving_inr_year"], "pred_kwh_hybrid": st["saving_kwh_electricity"],
                         "pred_kwh_physics": phys_kwh, "pred_lpg": st["saving_kwh_lpg"],
                         "pred_roi": st["saving_inr_year"] / cost if cost > 0 else st["saving_inr_year"] / 1000,
                         "zone": cities()[home.city].zone, "dwelling_type": home.dwelling_type, "n_ac": home.n_ac,
                         "income_band": home.income_band, "wfh": int(home.wfh), "building_age_years": home.building_age_years or 15,
                         "tenure": home.tenure, "occupants": home.occupants,
                         **tr, "true_roi": tr["true_inr"] / cost if cost > 0 else tr["true_inr"] / 1000})
    df = pd.DataFrame(rows)
    # graded relevance within each home by true ROI
    df["rank_true"] = df.groupby("home_id")["true_roi"].rank(ascending=False, method="first")
    df["rel"] = np.select([df["true_inr"] <= 0, df["rank_true"] == 1, df["rank_true"] <= 3, df["rank_true"] <= 5], [0, 3, 2, 1], 0)
    return df


def _ndcg_at(df: pd.DataFrame, score_col: str, k: int) -> float:
    vals = []
    for _, g in df.groupby("home_id"):
        if len(g) < 2 or g["rel"].max() == 0:
            continue
        vals.append(ndcg_score([g["rel"].values], [g[score_col].values], k=k))
    return float(np.mean(vals))


def _p_at(df: pd.DataFrame, score_col: str, k: int) -> float:
    vals = []
    for _, g in df.groupby("home_id"):
        top = g.sort_values(score_col, ascending=False).head(k)
        vals.append(float((top["rel"] >= 2).mean()))
    return float(np.mean(vals))


RANK_FEATURES = ["retrofit_id", "suit_ord", "order_rank", "cost_mid", "pred_inr", "pred_kwh_hybrid", "pred_lpg", "pred_roi",
                 "zone", "dwelling_type", "n_ac", "income_band", "wfh", "building_age_years", "tenure", "occupants"]


def train_ranker(pairs: pd.DataFrame) -> dict:
    tr, va, te = split_ids(pairs["home_id"].values)
    pairs = pairs.sort_values("home_id").reset_index(drop=True)
    X = prepare(pairs, RANK_FEATURES)
    m = {k: pairs["home_id"].isin(s) for k, s in (("tr", tr), ("va", va), ("te", te))}
    grp = lambda mask: pairs[mask].groupby("home_id", sort=False).size().values  # noqa: E731
    ranker = lgb.LGBMRanker(n_estimators=400, learning_rate=0.05, num_leaves=31, min_child_samples=30, random_state=SEED, verbose=-1)
    ranker.fit(X[m["tr"]], pairs.loc[m["tr"], "rel"], group=grp(m["tr"]), eval_set=[(X[m["va"]], pairs.loc[m["va"], "rel"])],
               eval_group=[grp(m["va"])], eval_at=[5], callbacks=[lgb.early_stopping(50, verbose=False)])
    pairs["s_model"] = ranker.predict(X)
    pop = pairs[m["tr"]].groupby("retrofit_id")["rel"].mean()
    pairs["s_popularity"] = pairs["retrofit_id"].map(pop).fillna(0)
    pairs["s_rules"] = pairs["pred_roi"] * pairs["suit_ord"]
    out = {}
    for split in ("va", "te"):
        d = pairs[m[split]]
        out[{"va": "validation", "te": "test"}[split]] = {
            name: {"NDCG@5": round(_ndcg_at(d, col, 5), 4), "Precision@3": round(_p_at(d, col, 3), 4)}
            for name, col in (("popularity_baseline", "s_popularity"), ("rules_physics_roi", "s_rules"), ("lightgbm_lambdarank", "s_model"))}
    MODEL_DIR.mkdir(exist_ok=True)
    ranker.booster_.save_model(str(MODEL_DIR / "ranker.txt"))
    meta = {"features": RANK_FEATURES, "categories": category_map(X), "version": _hash_file(MODEL_DIR / "ranker.txt")}
    (MODEL_DIR / "ranker.json").write_text(json.dumps(meta, indent=2))
    out["infeasible_recommendation_rate"] = 0.0  # candidates are rule-gated; asserted in tests
    out["n_pairs"] = int(len(pairs)); out["n_homes"] = int(pairs["home_id"].nunique()); out["version"] = meta["version"]
    # Savings model validation on the same held-out pairs
    d = pairs[m["te"]]
    out["savings_validation_test"] = {
        "electricity_MAE_kwh": {"physics_only": round(float(mean_absolute_error(d["true_kwh"], d["pred_kwh_physics"])), 1),
                                "hybrid_metered_scaled": round(float(mean_absolute_error(d["true_kwh"], d["pred_kwh_hybrid"])), 1)},
        "lpg_MAE_kwh": round(float(mean_absolute_error(d["true_lpg"], d["pred_lpg"])), 1),
        "sign_accuracy_electricity": round(float((np.sign(d["true_kwh"].round(0)) == np.sign(d["pred_kwh_hybrid"].round(0))).mean()), 4),
        "induction_electricity_increase_detected": bool((d.loc[d["retrofit_id"] == "induction_cooking", "pred_kwh_hybrid"] < 0).all()),
    }
    return out


# ---------------------------------------------------------------------------------------------
# 3. Hedonic value model with split-conformal intervals and a counterfactual uplift
# ---------------------------------------------------------------------------------------------

def value_frame(sales: pd.DataFrame, homes: pd.DataFrame) -> pd.DataFrame:
    d = sales.merge(homes[["home_id", "city", "zone", "dwelling_type", "floor_position", "carpet_area_true_m2", "building_age_years"]], on="home_id")
    d["carpet_area_m2"] = d["carpet_area_true_m2"]
    d["age_at_sale"] = (d["building_age_years"] + d["month_offset"] / 12).clip(lower=0)
    d["score"] = d["score_at_sale"]
    d["city_tier"] = d["city"].map(lambda c: cities()[c].tier)
    d["city_price_per_sqft"] = d["city"].map(lambda c: cities()[c].price_per_sqft)
    return d


def train_value(sales: pd.DataFrame, homes: pd.DataFrame, alpha: float = 0.2) -> dict:
    d = value_frame(sales, homes)
    X = prepare(d, VALUE_FEATURES)
    y = np.log(d["price_inr"])
    tr, va, te = split_ids(d["home_id"].values)
    m_tr, m_va, m_te = d["home_id"].isin(tr), d["home_id"].isin(va), d["home_id"].isin(te)
    model = lgb.LGBMRegressor(n_estimators=800, learning_rate=0.03, num_leaves=31, min_child_samples=30, subsample=0.8,
                              subsample_freq=1, random_state=SEED, verbose=-1, monotone_constraints=[1 if f == "score" else 0 for f in VALUE_FEATURES])
    model.fit(X[m_tr], y[m_tr], eval_set=[(X[m_va], y[m_va])], callbacks=[lgb.early_stopping(50, verbose=False)])
    pred = pd.Series(model.predict(X), index=X.index)
    # split conformal on the validation fold: q = (1-alpha) quantile of |log residual|
    resid = np.abs(y[m_va] - pred[m_va]).sort_values().values
    n = len(resid)
    q = float(resid[min(n - 1, int(np.ceil((n + 1) * (1 - alpha))) - 1)])
    cover = float(((y[m_te] >= pred[m_te] - q) & (y[m_te] <= pred[m_te] + q)).mean())
    # baselines
    sqft = d["carpet_area_m2"] * 10.7639
    psf = (d.loc[m_tr, "price_inr"] / sqft[m_tr]).groupby(d.loc[m_tr, "city"] + "|" + d.loc[m_tr, "dwelling_type"]).median()
    base1 = (d["city"] + "|" + d["dwelling_type"]).map(psf) * sqft
    flat = d["city_price_per_sqft"] * sqft * (1 + 0.015 * (d["score"] - 50) / 10)
    res = {"test_MAPE_pct": {"baseline_city_type_median_psf": round(mape(d.loc[m_te, "price_inr"], base1[m_te]), 2),
                             "baseline_flat_rating_rule": round(mape(d.loc[m_te, "price_inr"], flat[m_te]), 2),
                             "hedonic_lightgbm": round(mape(d.loc[m_te, "price_inr"], np.exp(pred[m_te])), 2)},
           "conformal_alpha": alpha, "conformal_q_log": round(q, 4), "interval_coverage_test": round(cover, 4),
           "interval_width_pct": round(100 * (np.exp(2 * q) - 1), 1)}
    # implied premium per 10 points (consistency check against the disclosed generator assumption)
    Xp = X[m_te].copy()
    lo = np.exp(model.predict(Xp.assign(score=40.0)))
    hi = np.exp(model.predict(Xp.assign(score=60.0)))
    res["implied_premium_per_10_points_pct"] = round(float(np.median(hi / lo) ** 0.5 - 1) * 100, 2)
    res["generator_assumed_premium_per_10_points_pct"] = 1.5
    res["note"] = "Recovering the assumed premium shows internal consistency, not real-world accuracy."
    MODEL_DIR.mkdir(exist_ok=True)
    model.booster_.save_model(str(MODEL_DIR / "value_hedonic.txt"))
    meta = {"features": VALUE_FEATURES, "categories": category_map(X), "conformal_q_log": q, "alpha": alpha,
            "version": _hash_file(MODEL_DIR / "value_hedonic.txt")}
    (MODEL_DIR / "value_hedonic.json").write_text(json.dumps(meta, indent=2))
    # Bootstrap ensemble (B=10) for the uncertainty of the counterfactual uplift
    rng = np.random.default_rng(SEED)
    tr_idx = np.where(m_tr)[0]
    for b in range(10):
        idx = rng.choice(tr_idx, size=len(tr_idx), replace=True)
        mb = lgb.LGBMRegressor(n_estimators=model.best_iteration_ or 300, learning_rate=0.03, num_leaves=31, min_child_samples=30,
                               random_state=SEED + b, verbose=-1, monotone_constraints=[1 if f == "score" else 0 for f in VALUE_FEATURES])
        mb.fit(X.iloc[idx], y.iloc[idx])
        mb.booster_.save_model(str(MODEL_DIR / f"value_boot_{b}.txt"))
    res["bootstrap_models"] = 10
    res["version"] = meta["version"]; res["n_sales"] = int(len(d))
    return res


def main() -> None:
    t0 = time.time()
    homes = pd.read_parquet(DATA_DIR / "homes.parquet")
    events = pd.read_parquet(DATA_DIR / "retrofit_events.parquet")
    sales = pd.read_parquet(DATA_DIR / "sales.parquet")
    truth = pd.read_parquet(DATA_DIR / "truth.parquet")
    report = {"seed": SEED, "split": "GroupShuffleSplit-equivalent on home_id (=customer), 70/15/15"}
    report["energy_model"] = train_energy(homes, events); print("energy done", time.time() - t0)
    cache = DATA_DIR / "ranker_pairs.parquet"
    if cache.exists():
        pairs = pd.read_parquet(cache)
    else:
        pairs = build_pairs(homes, truth)
        pairs.to_parquet(cache, index=False)
    print("pairs", len(pairs), time.time() - t0)
    report["ranker_and_savings"] = train_ranker(pairs); print("ranker done", time.time() - t0)
    report["value_model"] = train_value(sales, homes); print("value done", time.time() - t0)
    REPORT_DIR.mkdir(exist_ok=True)
    (REPORT_DIR / "eval_report.json").write_text(json.dumps(report, indent=2, default=float))
    print(json.dumps(report, indent=2, default=float))


if __name__ == "__main__":
    main()
