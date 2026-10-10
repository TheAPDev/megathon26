"""Synthetic Indian housing population (seeded, documented in docs/data_card.md).

Produces:
  homes            one row per home (current state), with 24 months of metered grid import
  customers        bank customers linked to homes, with home-loan details (for the lender portfolio)
  retrofit_events  completed retrofits with month and the true step change they caused
  sales            historic sale prices (hedonic function + disclosed rating premium + noise)
  memory           stated customer constraints and past accept/reject of advice
  truth            hidden multipliers (NOT features; used only to validate that models recover them)

Ground truth consumption = documented physics model x hidden household effects the physics engine
does not know about (income-driven plug loads, humidity, leaky old buildings, work-from-home,
behaviour). That gives the ML layer something real to learn and keeps labels from being identical
to the engine's own output.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..engine import retrofits as R
from ..engine.physics import modeled_energy
from ..reference import cities, tariff_states
from ..data_access import row_to_home
from ..schemas import Home

SEED = 42
N_MONTHS = 24
START = pd.Timestamp("2024-10-01")  # month 0 = Oct 2024, month 23 = Sep 2026
MONTHS = pd.date_range(START, periods=N_MONTHS, freq="MS")
SALES_HISTORY_MONTHS = 60
RATING_PREMIUM_PER_10_POINTS = 0.015  # disclosed assumption: +1.5% price per 10 score points
INCOME_PLUG = {"low": 0.70, "middle": 1.0, "upper_middle": 1.30, "high": 1.75}
EVENT_WEIGHTS = {"ac_5star_inverter": .25, "bldc_fans": .15, "led_lighting": .15, "rooftop_solar": .12, "cool_roof": .08,
                 "fridge_5star": .08, "solar_water_heater": .05, "smart_plug_tod": .05, "induction_cooking": .04,
                 "lithium_battery": .03}


@dataclass
class GenConfig:
    n_homes: int = 50_000
    seed: int = SEED
    missing_some_rate: float = 0.15     # 1-6 of the last 12 months missing
    missing_most_rate: float = 0.03     # 7-11 months missing -> predicted path
    area_missing_rate: float = 0.03
    ocr_error_rate: float = 0.01        # per-month digit errors on bill-OCR homes
    label_conflict_rate: float = 0.15   # share of BEE-labelled homes whose label disagrees with reality
    event_rate: float = 0.18
    second_event_rate: float = 0.05
    sale_rate: float = 0.25


def _choice(rng, options, probs, size=None):
    p = np.asarray(probs, dtype=float)
    return rng.choice(options, p=p / p.sum(), size=size)


def sample_homes(cfg: GenConfig, rng: np.random.Generator) -> list[dict]:
    cs = list(cities().values())
    w = np.array([3.0 if c.tier == 1 else 1.0 for c in cs])
    city_idx = rng.choice(len(cs), p=w / w.sum(), size=cfg.n_homes)
    rows = []
    for i in range(cfg.n_homes):
        c = cs[city_idx[i]]
        zone, tier = c.zone, c.tier
        income = _choice(rng, ["low", "middle", "upper_middle", "high"], [.15, .45, .28, .12])
        dwelling = _choice(rng, ["apartment", "independent_house", "row_house"], [.72, .20, .08] if tier == 1 else [.45, .43, .12])
        floor = _choice(rng, ["top", "middle", "ground"], [.18, .62, .20]) if dwelling == "apartment" else "top"
        tenure = _choice(rng, ["owner", "tenant"], [.72, .28])
        med = {"low": 45, "middle": 70, "upper_middle": 100, "high": 150}[income] * (1.5 if dwelling != "apartment" else 1.0)
        area = float(np.clip(rng.lognormal(math.log(med), 0.25), 25, 600))
        occ = int(np.clip(rng.poisson(3.2) + 1, 1, 9))
        age = float(rng.uniform(0, 35))
        exposed = floor == "top"
        if dwelling != "apartment":
            roof_access, roof_area = tenure == "owner" or rng.random() < 0.2, area * rng.uniform(0.6, 1.0)
        else:
            roof_access = exposed and tenure == "owner" and rng.random() < 0.35
            roof_area = area * 0.8 if roof_access else 0.0
        wall = _choice(rng, ["aac", "hollow_block", "solid_brick"], [.35, .25, .40] if age < 10 else [.05, .20, .75])
        n_ac_p = {"low": [.75, .25, 0, 0, 0], "middle": [.40, .40, .18, .02, 0], "upper_middle": [.12, .38, .35, .15, 0],
                  "high": [.03, .17, .35, .30, .15]}[income]
        if zone == "cold":
            n_ac_p = [.85, .12, .03, 0, 0]
        elif zone == "temperate":
            n_ac_p = [min(1, n_ac_p[0] * 1.6)] + [x * 0.7 for x in n_ac_p[1:]]
        n_ac = int(_choice(rng, [0, 1, 2, 3, 4], n_ac_p))
        ac_age = float(rng.uniform(0, 14))
        ac_tech = "inverter" if rng.random() < (0.75 if ac_age < 4 else 0.45 if ac_age < 8 else 0.15) else "fixed"
        ac_star = int(_choice(rng, [1, 2, 3, 4, 5], [.08, .12, .45, .10, .25]))
        n_fans = int(np.clip(round(area / 18) + 1, 1, 14))
        bldc = 0.0 if rng.random() < 0.7 else float(rng.uniform(0.2, 1.0))
        wh_opts = ["electric_geyser", "solar", "heat_pump", "gas", "none"]
        wh_p = {"cold": [.70, .08, .02, .05, .15], "composite": [.70, .08, .02, .05, .15], "temperate": [.60, .12, .02, .06, .20],
                "hot_dry": [.50, .08, .01, .06, .35], "warm_humid": [.35, .04, .01, .05, .55]}[zone]
        cooking = _choice(rng, ["lpg", "png", "induction"], [.78, .12, .10] if tier == 1 else [.88, .02, .10])
        outage = float(rng.exponential(4 if tier == 1 else 15))
        backup = _choice(rng, ["none", "lead_acid", "lithium", "dg_set"],
                         [.66, .25, .06, .03] if tier == 1 else [.46, .45, .06, .03])
        smart_meter = rng.random() < (.30 if tier == 1 else .15)
        tod_ok = tariff_states()[c.state]["tod_tariff"] == "yes"
        pv = 0.0
        if roof_access and tenure == "owner" and rng.random() < 0.10:
            pv = float(_choice(rng, [1, 2, 3, 4, 5], [.15, .30, .35, .12, .08]))
        h = dict(
            city=c.city, dwelling_type=dwelling, floor_position=floor, tenure=tenure,
            carpet_area_m2=round(area, 1), occupants=occ, building_age_years=round(age, 1),
            roof_area_m2=round(float(roof_area), 1), roof_access=bool(roof_access), wall_type=wall,
            window_to_wall=round(float(np.clip(rng.normal(0.22, 0.07), 0.08, 0.6)), 3), west_glass=bool(rng.random() < .35),
            shading=_choice(rng, ["none", "partial", "full"], [.45, .40, .15]),
            cool_roof=bool(exposed and rng.random() < .08), roof_insulation=bool(exposed and rng.random() < .05),
            solar_film=bool(rng.random() < .06),
            n_ac=n_ac, ac_tech=ac_tech, ac_star=ac_star, ac_age_years=round(ac_age, 1),
            ac_tonnage=float(_choice(rng, [1.0, 1.5, 2.0], [.25, .60, .15])),
            ac_setpoint_c=float(np.clip(round(rng.normal(23, 1.5) * 2) / 2, 18, 28)),
            n_coolers=int(rng.integers(1, 3)) if zone in ("hot_dry", "composite") and rng.random() < (.4 if income in ("low", "middle") else .15) else 0,
            n_fans=n_fans, bldc_fan_share=round(bldc, 2),
            fridge_star=int(_choice(rng, [1, 2, 3, 4, 5], [.10, .15, .40, .15, .20])), fridge_age_years=round(float(rng.uniform(0, 15)), 1),
            light_points=int(np.clip(round(area / 7), 4, 60)), led_share=round(float(rng.beta(5, 2)), 2),
            water_heating=_choice(rng, wh_opts, wh_p), cooking=cooking,
            lpg_cylinders_per_year=round(float(np.clip(2 + 1.75 * occ + rng.normal(0, 1.2), 2, 30)), 1) if cooking == "lpg" else None,
            pv_kw=pv, net_metered=pv > 0, backup=backup, outage_hours_month=round(outage, 1),
            smart_meter=bool(smart_meter), tod_tariff=bool(smart_meter and tod_ok and rng.random() < .4),
            smart_plugs=bool(rng.random() < (.15 if income in ("upper_middle", "high") else .04)),
            sanctioned_load_kw=float(min(15, max(1, round(1 + 1.6 * n_ac + area / 80)))),
            income_band=income, wfh=bool(rng.random() < (.25 if income in ("upper_middle", "high") else .10)),
        )
        if h["water_heating"] == "solar" and not roof_access:
            h["water_heating"] = "electric_geyser"
        if backup == "dg_set" and dwelling == "apartment":
            h["backup"] = "none"  # society DG, not household
        rows.append(h)
    return rows


def truth_multipliers(h: dict, rng: np.random.Generator) -> dict:
    zone = cities()[h["city"]].zone
    return {
        "behaviour": float(rng.lognormal(0, 0.12)),
        "humid_cooling": 1.12 if zone == "warm_humid" else 1.0,
        "leak_cooling": 1 + 0.004 * max(0.0, h["building_age_years"] - 10),
        "income_plug": INCOME_PLUG[h["income_band"]],
        "wfh_plug": 1.15 if h["wfh"] else 1.0,
        "wfh_cooling": 1.10 if h["wfh"] else 1.0,
        "tenant_cooling": 0.95 if h["tenure"] == "tenant" else 1.0,
    }


def true_monthly_import(home: Home, t: dict, year_factor: dict[int, float]) -> list[float]:
    """12 calendar months (Jan..Dec) of true grid import for a given home state."""
    e = modeled_energy(home)
    eu = e.monthly_enduse
    out = []
    daytime = 0.35 + (0.15 if home.wfh else 0.0)
    for m in range(12):
        cool = eu["cooling"][m] * t["humid_cooling"] * t["leak_cooling"] * t["wfh_cooling"] * t["tenant_cooling"] * year_factor.get(m, 1.0)
        plug = eu["plug_other"][m] * t["income_plug"] * t["wfh_plug"]
        rest = sum(eu[k][m] for k in ("fans_coolers", "fridge", "lighting", "water_heating", "cooking_electric", "backup_losses"))
        demand = (cool + plug + rest) * t["behaviour"]
        gen = e.monthly_pv_generation[m] if e.monthly_pv_generation else 0.0
        out.append(max(0.0, demand - min(gen, demand * daytime)))
    return out


def _event_pick(home: Home, rng) -> str | None:
    opts = [r for r in EVENT_WEIGHTS if R.feasibility(home, r)[0] != "Infeasible" and not R.already_done(home, r)]
    if not opts:
        return None
    w = np.array([EVENT_WEIGHTS[r] for r in opts])
    return str(rng.choice(opts, p=w / w.sum()))


def generate(cfg: GenConfig | None = None) -> dict[str, pd.DataFrame]:
    cfg = cfg or GenConfig()
    rng = np.random.default_rng(cfg.seed)
    raw = sample_homes(cfg, rng)
    # weather: per city per year cooling factor; summer 2026 heatwave bump (Apr-Jun)
    city_year = {(c, y): float(rng.normal(1.0, 0.06)) for c in cities() for y in (2024, 2025, 2026)}
    homes, events, truth = [], [], []
    for i, h in enumerate(raw):
        hid = f"H{i + 1:06d}"
        t = truth_multipliers(h, rng)
        current = Home(home_id=hid, **{k: v for k, v in h.items()})
        # Optionally construct a pre-retrofit state and event month(s)
        states = [(0, current)]
        n_ev = 0
        if rng.random() < cfg.event_rate:
            n_ev = 2 if rng.random() < cfg.second_event_rate / cfg.event_rate else 1
        pre = current
        ev_list = []
        # build backwards: choose retrofits that the *pre* state lacked
        for _ in range(n_ev):
            rid = _event_pick(pre, rng)
            if rid is None:
                break
            month = int(rng.integers(3, N_MONTHS - 2))
            post = R.apply(pre, rid)
            ev_list.append((month, rid, pre, post))
            pre = post
        if ev_list:
            ev_list.sort(key=lambda x: x[0])
            # current state is the state after all events
            current = ev_list[-1][3]
            states = [(0, ev_list[0][2])] + [(m, post) for m, _, _, post in ev_list]
        # 24 months of readings
        readings = []
        cache = {}
        for k, ts in enumerate(MONTHS):
            st = [s for m0, s in states if m0 <= k][-1]
            key = (id(st), ts.year)
            if key not in cache:
                yf = {m: city_year[(h["city"], ts.year)] * (1.08 if ts.year == 2026 and m in (3, 4, 5) else 1.0) for m in range(12)}
                cache[key] = true_monthly_import(st, t, yf)
            v = cache[key][ts.month - 1] * float(rng.lognormal(0, 0.06))
            readings.append(round(v, 1))
        for (month, rid, pre_s, post_s) in ev_list:
            lo, hi = R.cost_range(pre_s, rid)
            yf = {m: 1.0 for m in range(12)}
            before = sum(true_monthly_import(pre_s, t, yf))
            after = sum(true_monthly_import(post_s, t, yf))
            events.append({"event_id": f"E{len(events) + 1:06d}", "home_id": hid, "retrofit_id": rid,
                           "completed_month": MONTHS[month].strftime("%Y-%m"), "month_index": month,
                           "cost_inr": round(float(rng.uniform(lo, hi)), -2),
                           "financed": bool(rng.random() < (.6 if rid == "rooftop_solar" else .2)),
                           "true_annual_kwh_saving": round(before - after, 1)})
        row = current.model_dump()
        row.pop("monthly_kwh", None)
        row["home_id"] = hid
        row["state"] = cities()[h["city"]].state
        row["zone"] = cities()[h["city"]].zone
        c = cities()[h["city"]]
        row["lat"] = round(c.lat + float(rng.normal(0, 0.05)), 4)
        row["lon"] = round(c.lon + float(rng.normal(0, 0.05)), 4)
        row["has_retrofit_history"] = bool(ev_list)
        row["kwh_24m"] = readings
        homes.append(row)
        truth.append({"home_id": hid, **t})
    df = pd.DataFrame(homes)
    _inject_data_quality(df, cfg, rng)
    customers = _customers(df, rng)
    sales = _sales(df, rng)
    memory = _memory(df, customers, rng)
    return {"homes": df, "customers": customers, "retrofit_events": pd.DataFrame(events), "sales": sales,
            "memory": memory, "truth": pd.DataFrame(truth)}


def _inject_data_quality(df: pd.DataFrame, cfg: GenConfig, rng) -> None:
    n = len(df)
    src = []
    for sm in df["smart_meter"]:
        src.append("smart_meter" if sm else str(_choice(rng, ["bill_ocr", "bbps", "survey"], [.55, .25, .20])))
    df["data_source"] = src
    kwh = [list(x) for x in df["kwh_24m"]]
    missing_pattern = []
    for i in range(n):
        pat = "complete"
        if src[i] == "survey":
            kwh[i] = [None] * N_MONTHS
            pat = "no_data"
        else:
            r = rng.random()
            if r < cfg.missing_most_rate:
                k = int(rng.integers(7, 12))
                for j in rng.choice(range(12, 24), size=k, replace=False):
                    kwh[i][j] = None
                pat = f"missing_{k}_of_last_12"
            elif r < cfg.missing_most_rate + cfg.missing_some_rate:
                k = int(rng.integers(1, 7))
                for j in rng.choice(range(12, 24), size=k, replace=False):
                    kwh[i][j] = None
                pat = f"missing_{k}_of_last_12"
            if src[i] == "bill_ocr":
                for j in range(N_MONTHS):
                    if kwh[i][j] is not None and rng.random() < cfg.ocr_error_rate:
                        kwh[i][j] = round(kwh[i][j] * (10 if rng.random() < .5 else 0.1), 1)
                        pat += "+ocr_error"
        missing_pattern.append(pat)
    df["kwh_24m"] = kwh
    df["missing_pattern"] = missing_pattern
    area_missing = rng.random(n) < cfg.area_missing_rate
    df["carpet_area_true_m2"] = df["carpet_area_m2"]
    df.loc[area_missing, "carpet_area_m2"] = None
    # BEE labels: rare, mostly newer buildings; correlated with true efficiency, with some conflicts
    label = [None] * n
    for i in range(n):
        if df.at[i, "building_age_years"] < 8 and rng.random() < 0.25 or rng.random() < 0.02:
            last12 = [x for x in kwh[i][12:] if x is not None]
            if src[i] == "survey" or not last12:
                stars = int(rng.integers(2, 6))
            else:
                inten = np.median(last12) * 12 / max(df.at[i, "carpet_area_true_m2"], 20)
                stars = int(np.clip(round(5.5 - inten / 15), 1, 5))
            if rng.random() < cfg.label_conflict_rate:
                stars = 5 if stars <= 2 else 1
            label[i] = stars
    df["bee_star_label"] = label


def _customers(df: pd.DataFrame, rng) -> pd.DataFrame:
    rows = []
    for i, r in df.iterrows():
        cid = f"C{i + 1:06d}"
        c = cities()[r["city"]]
        area_sqft = (r["carpet_area_true_m2"] or 80) * 10.7639
        value = area_sqft * c.price_per_sqft * (1.15 if r["dwelling_type"] != "apartment" else 1.0)
        has_loan = r["tenure"] == "owner" and rng.random() < 0.7
        principal = value * rng.uniform(0.6, 0.85) if has_loan else 0.0
        start_months_ago = int(rng.integers(6, 180)) if has_loan else 0
        rate = float(rng.uniform(8.25, 9.6)) if has_loan else 0.0
        tenure_m = 240
        r_m = rate / 1200
        emi_v = principal * r_m * (1 + r_m) ** tenure_m / ((1 + r_m) ** tenure_m - 1) if has_loan else 0.0
        paid = start_months_ago
        outstanding = principal * ((1 + r_m) ** tenure_m - (1 + r_m) ** paid) / ((1 + r_m) ** tenure_m - 1) if has_loan else 0.0
        rows.append({"customer_id": cid, "home_id": r["home_id"], "region": c.state, "city": r["city"],
                     "age_band": str(_choice(rng, ["25-34", "35-44", "45-54", "55+"], [.3, .35, .22, .13])),
                     "income_band": r["income_band"], "preferred_language": str(_choice(rng, ["en", "hi", "ta", "mr", "te", "kn", "bn", "gu"],
                                                                                        [.35, .35, .06, .06, .06, .05, .04, .03])),
                     "has_home_loan": bool(has_loan), "loan_principal_inr": round(principal, -3), "loan_outstanding_inr": round(outstanding, -3),
                     "loan_rate_pct": round(rate, 2), "loan_emi_inr": round(emi_v), "loan_start_months_ago": start_months_ago,
                     "property_value_inr": round(value, -4), "credit_band": str(_choice(rng, ["A", "B", "C", "D"], [.35, .4, .18, .07])),
                     "consent_energy_data": bool(rng.random() < 0.85), "consent_marketing": bool(rng.random() < 0.55)})
    return pd.DataFrame(rows)


def market_index(month_offset: int, city_name: str) -> float:
    """Price index relative to Sep 2026 (=1.0); ~6%/yr nominal growth with a city tilt."""
    tilt = (hash(city_name) % 7 - 3) / 1000.0
    return (1.06 + tilt) ** (month_offset / 12)


def _sales(df: pd.DataFrame, rng) -> pd.DataFrame:
    from ..engine.score import score_home
    rows = []
    for i, r in df.iterrows():
        if rng.random() >= 0.25:
            continue
        c = cities()[r["city"]]
        h = row_to_home({**r.to_dict(), "carpet_area_m2": r["carpet_area_true_m2"], "kwh_24m": None})
        score = score_home(h).raw_score
        offset = -int(rng.integers(0, SALES_HISTORY_MONTHS))
        area_sqft = r["carpet_area_true_m2"] * 10.7639
        type_f = {"apartment": 1.0, "independent_house": 1.15, "row_house": 1.05}[r["dwelling_type"]]
        floor_f = {"top": 0.98, "middle": 1.0, "ground": 0.97}[r["floor_position"]]
        age_at_sale = max(0.0, r["building_age_years"] + offset / 12)
        age_f = max(0.7, 1 - 0.008 * age_at_sale)
        premium = 1 + RATING_PREMIUM_PER_10_POINTS * (score - 50) / 10
        price = area_sqft * c.price_per_sqft * type_f * floor_f * age_f * premium * market_index(offset, r["city"]) * rng.lognormal(0, 0.08)
        sale_month = (MONTHS[-1] + pd.DateOffset(months=offset)).strftime("%Y-%m")
        rows.append({"sale_id": f"S{len(rows) + 1:06d}", "home_id": r["home_id"], "sale_month": sale_month, "month_offset": offset,
                     "price_inr": round(price, -3), "score_at_sale": round(score, 1)})
    return pd.DataFrame(rows)


def _memory(df: pd.DataFrame, customers: pd.DataFrame, rng) -> pd.DataFrame:
    rows = []
    for i, r in customers.iterrows():
        if rng.random() > 0.12:
            continue
        h = df.iloc[i]
        facts = []
        if h["tenure"] == "tenant":
            facts.append({"kind": "constraint", "key": "tenure", "value": "renting"})
        if rng.random() < .5:
            facts.append({"kind": "constraint", "key": "budget_inr", "value": int(_choice(rng, [20000, 50000, 100000, 200000], [.3, .35, .25, .1]))})
        if rng.random() < .2:
            facts.append({"kind": "constraint", "key": "exclude", "value": str(_choice(rng, ["rooftop_solar", "induction_cooking", "ac_5star_inverter"], [.4, .4, .2]))})
        if rng.random() < .3:
            facts.append({"kind": "preference", "key": "language", "value": r["preferred_language"]})
        for f in facts:
            rows.append({"memory_id": f"M{len(rows) + 1:06d}", "customer_id": r["customer_id"], "home_id": h["home_id"],
                         "kind": f["kind"], "key": f["key"], "value": json.dumps(f["value"]),
                         "created_month": MONTHS[int(rng.integers(0, N_MONTHS))].strftime("%Y-%m")})
    return pd.DataFrame(rows)
