"""Green Ghar Score (0-100).

Fixed weights, written as fractions that sum to 1 (only the final score is rounded):
  energy efficiency 0.25 | consumption intensity 0.20 | envelope 0.15 | cooling system 0.15 |
  windows & shading 0.10 | renewables 0.10 | smart use 0.05
Every sub-score is a documented, monotonic mapping: a better state never scores lower
(property-tested in tests/test_monotonicity.py).

Overlaps, stated on purpose:
- Energy efficiency is the *asset* rating (BEE star label, else a modelled kWh/m2 rating), intensity is the
  *operational* metered kWh/m2. One rates the home, the other measures how it is used.
- Rooftop solar affects renewables (the asset) and intensity (lower metered import). One rewards the
  capability, the other measures the outcome.
- The modelled rating excludes PV so solar is not counted a third time.
"""
from __future__ import annotations

from ..reference import ZONE_BENCHMARK_KWH_M2, city
from ..schemas import Home, ScoreResult, SubScore
from .consumption import profile
from .physics import ac_iseer, modeled_energy

WEIGHTS = {
    "energy_efficiency": 0.25,
    "consumption_intensity": 0.20,
    "envelope": 0.15,
    "cooling_system": 0.15,
    "windows_shading": 0.10,
    "renewables": 0.10,
    "smart_use": 0.05,
}
assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-12

# A 4-5 star label with metered use above 1.5x the benchmark (or a 1-2 star label below 0.6x) is a data conflict.
CONFLICT_HIGH, CONFLICT_LOW = 1.5, 0.6
BANDS = [(80, "Highly efficient"), (65, "Good"), (50, "Moderate"), (30, "Poor"), (0, "Very poor")]
DEFAULT_AREA_BY_TYPE = {"apartment": 85.0, "independent_house": 140.0, "row_house": 110.0}


def band(score: float) -> str:
    for lo, name in BANDS:
        if score >= lo:
            return name
    return "Very poor"


def clip(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def benchmark(home: Home) -> float:
    b = ZONE_BENCHMARK_KWH_M2[city(home.city).zone]
    return b * (1.1 if home.dwelling_type != "apartment" else 1.0)


def area(home: Home) -> tuple[float, bool]:
    if home.carpet_area_m2:
        return home.carpet_area_m2, False
    return DEFAULT_AREA_BY_TYPE[home.dwelling_type], True


# ---- sub-score mappings -----------------------------------------------------------------------

def s_energy_efficiency(home: Home) -> tuple[float, str, bool]:
    if home.bee_star_label:
        return 20.0 * home.bee_star_label, f"BEE star label: {home.bee_star_label} star", False
    e = modeled_energy(home.model_copy(update={"pv_kw": 0}))
    a, est = area(home)
    r = (e.total_electric_demand + e.lpg_kwh) / a / benchmark(home)
    s = clip(100 * (1.6 - r) / 1.1)  # r <= 0.5 -> 100, r >= 1.6 -> 0
    return s, f"No BEE label; modelled rating is {r:.2f}x the {city(home.city).zone.replace('_', '-')} benchmark", True


def intensity_ratio(home: Home, annual_grid_kwh: float, lpg_kwh: float) -> float:
    a, _ = area(home)
    return (annual_grid_kwh + lpg_kwh) / a / benchmark(home)


def s_intensity(r: float) -> float:
    return clip(100 * (2.0 - r) / 1.5)  # r <= 0.5 -> 100, r >= 2.0 -> 0


def s_envelope(home: Home) -> tuple[float, str]:
    wall = {"solid_brick": 0.0, "hollow_block": 50.0, "aac": 100.0}[home.wall_type]
    exposed = home.floor_position == "top" or home.dwelling_type != "apartment"
    if not exposed:
        return wall, f"No exposed roof (N/A, rescaled); walls: {home.wall_type.replace('_', ' ')}"
    roof = (55.0 if home.roof_insulation else 0.0) + (45.0 if home.cool_roof else 0.0)
    s = 0.55 * roof + 0.45 * wall
    parts = []
    parts.append("cool roof" if home.cool_roof else "no cool roof")
    parts.append("roof insulated" if home.roof_insulation else "roof uninsulated")
    return s, f"Exposed roof: {', '.join(parts)}; walls: {home.wall_type.replace('_', ' ')}"


def s_cooling(home: Home) -> tuple[float, str]:
    fans = 100.0 * home.bldc_fan_share
    if home.n_ac == 0:
        return 0.7 * 85.0 + 0.3 * fans, f"No AC; {round(home.bldc_fan_share * 100)}% BLDC fans"
    iseer = ac_iseer(home)
    ac = clip(100 * (iseer - 2.6) / (5.8 - 2.6))
    sp = clip((home.ac_setpoint_c - 20) / 4 * 100) / 100  # set-point below 24 C trims the AC part
    ac_part = ac * (0.85 + 0.15 * sp)
    return 0.7 * ac_part + 0.3 * fans, (f"{home.n_ac} AC, {home.ac_tech} {home.ac_star}-star, effective ISEER {iseer:.1f}; "
                                       f"{round(home.bldc_fan_share * 100)}% BLDC fans")


def s_windows(home: Home) -> tuple[float, str]:
    base = clip(100 - 120 * max(0.0, home.window_to_wall - 0.15))
    shade = {"none": 0.7, "partial": 0.85, "full": 1.0}[home.shading]
    west = 0.85 if (home.west_glass and not home.solar_film and home.shading != "full") else 1.0
    film = 1.05 if home.solar_film else 1.0
    s = clip(base * shade * west * film)
    return s, f"Window-to-wall {home.window_to_wall:.0%}, shading {home.shading}{', west glass' if home.west_glass else ''}{', solar film' if home.solar_film else ''}"


def s_renewables(home: Home) -> tuple[float, str]:
    e = modeled_energy(home)
    swh = 0.0
    if home.water_heating == "solar":
        e0 = modeled_energy(home.model_copy(update={"water_heating": "electric_geyser"}))
        swh = e0.water_heating - e.water_heating
    demand = e.total_electric_demand + e.lpg_kwh + swh
    r = (e.pv_generation + swh) / demand if demand else 0.0
    return min(100.0, 200 * r), f"Renewables cover {r:.0%} of demand ({home.pv_kw:g} kW PV{', solar water heater' if swh else ''})"


def s_smart(home: Home) -> tuple[float, str]:
    s = 30.0 * home.smart_meter + 20.0 * home.tod_tariff + 25.0 * home.smart_plugs
    s += 25.0 if (home.n_ac == 0 or home.ac_setpoint_c >= 24) else 25.0 * clip((home.ac_setpoint_c - 18) / 6, 0, 1)
    bits = [b for b, on in (("smart meter", home.smart_meter), ("time-of-day tariff", home.tod_tariff),
                            ("smart plugs/timers", home.smart_plugs)) if on]
    return s, (", ".join(bits) or "no smart controls") + (f"; AC set to {home.ac_setpoint_c:g} C" if home.n_ac else "")


# ---- full score -------------------------------------------------------------------------------

def score_home(home: Home, annual_override: float | None = None) -> ScoreResult:
    prof = profile(home)
    annual = annual_override if annual_override is not None else prof["annual"]
    e = modeled_energy(home)
    a, area_est = area(home)
    r = intensity_ratio(home, annual, e.lpg_kwh)
    warnings: list[str] = []
    conf_reasons: list[str] = list(prof["reasons"])

    ee, ee_why, ee_est = s_energy_efficiency(home)
    parts = {
        "energy_efficiency": (ee, ee_why, ee_est),
        "consumption_intensity": (s_intensity(r), f"{(annual + e.lpg_kwh) / a:.0f} kWh/m2/yr vs benchmark {benchmark(home):.0f} ({r:.2f}x)",
                                  prof["estimated"] or area_est),
        "envelope": (*s_envelope(home), False),
        "cooling_system": (*s_cooling(home), False),
        "windows_shading": (*s_windows(home), False),
        "renewables": (*s_renewables(home), False),
        "smart_use": (*s_smart(home), False),
    }
    comps = [SubScore(component=k, weight=WEIGHTS[k], score=round(v[0], 2), contribution=round(WEIGHTS[k] * v[0], 3),
                      why=v[1], estimated=v[2]) for k, v in parts.items()]
    raw = sum(WEIGHTS[k] * v[0] for k, v in parts.items())

    # Data conflicts: show both, never silently pick a side.
    if home.bee_star_label:
        if home.bee_star_label >= 4 and r > CONFLICT_HIGH:
            warnings.append(f"Data conflict: BEE label says {home.bee_star_label} star but metered use is {r:.1f}x the benchmark. "
                            "Check the label, the bills or how the home is used.")
        if home.bee_star_label <= 2 and r < CONFLICT_LOW:
            warnings.append(f"Data conflict: BEE label says {home.bee_star_label} star but metered use is only {r:.1f}x the benchmark.")
    if area_est:
        conf_reasons.append("Carpet area missing; a typical size for the dwelling type was used")

    months = prof["months_observed"]
    if home.data_source in ("smart_meter",) and months == 12 and not area_est:
        conf = "high"
    elif months >= 6 and not (area_est and months < 12):
        conf = "medium"
    else:
        conf = "low"
    if warnings and conf == "high":
        conf = "medium"
    if conf != "high" and not conf_reasons:
        conf_reasons.append(f"Usage data from {home.data_source.replace('_', ' ')}")

    return ScoreResult(
        home_id=home.home_id, score=int(round(raw)), band=band(round(raw)), raw_score=round(raw, 3),
        components=comps, confidence=conf, confidence_reasons=conf_reasons, warnings=warnings,
        annual_grid_kwh=round(annual, 1), annual_grid_kwh_estimated=prof["estimated"],
        intensity_kwh_m2=round((annual + e.lpg_kwh) / a, 2),
    )
