"""Retrofit library: how each retrofit changes a home, whether it is feasible, and what it costs."""
from __future__ import annotations

from ..reference import catalogue, city, subsidy_rules, tariff_states, zone_suitability
from ..schemas import Home

SQFT_PER_M2 = 10.7639
SUIT_ORDER = {"Infeasible": 0, "Low": 1, "Medium": 2, "High": 3}


def roof_exposed(home: Home) -> bool:
    return home.floor_position == "top" or home.dwelling_type != "apartment"


def roof_area_m2(home: Home) -> float:
    if home.roof_area_m2 is not None:
        return home.roof_area_m2
    area = home.carpet_area_m2 or 90.0
    return area * (0.9 if home.dwelling_type != "apartment" else 0.0)


def max_pv_kw(home: Home) -> float:
    """Shadow-free roof needs ~10 m2 per kW; also capped by sanctioned load (+50%) and 10 kW."""
    if not home.roof_access:
        return 0.0
    return max(0.0, min(roof_area_m2(home) / 10.0, max(home.sanctioned_load_kw * 1.5, 3.0), 10.0))


def apply(home: Home, rid: str, params: dict | None = None) -> Home:
    p = params or {}
    upd: dict = {}
    if rid == "cool_roof":
        upd = {"cool_roof": True}
    elif rid == "roof_insulation":
        upd = {"roof_insulation": True}
    elif rid == "external_shading":
        upd = {"shading": "full"}
    elif rid == "solar_film":
        upd = {"solar_film": True}
    elif rid == "ac_setpoint":
        upd = {"ac_setpoint_c": max(home.ac_setpoint_c, p.get("ac_setpoint_c", 24.0))}
    elif rid == "smart_plug_tod":
        upd = {"smart_plugs": True, "tod_tariff": tariff_states()[city(home.city).state]["tod_tariff"] == "yes" or home.tod_tariff}
    elif rid == "ac_5star_inverter":
        upd = {"ac_tech": "inverter", "ac_star": 5, "ac_age_years": 0}
    elif rid == "bldc_fans":
        upd = {"bldc_fan_share": 1.0}
    elif rid == "led_lighting":
        upd = {"led_share": 1.0}
    elif rid == "fridge_5star":
        upd = {"fridge_star": 5, "fridge_age_years": 0}
    elif rid == "solar_water_heater":
        upd = {"water_heating": "solar"}
    elif rid == "heat_pump_geyser":
        upd = {"water_heating": "heat_pump"}
    elif rid == "induction_cooking":
        upd = {"cooking": "induction", "lpg_cylinders_per_year": 0}
    elif rid == "lithium_battery":
        upd = {"backup": "lithium"}
    elif rid == "rooftop_solar":
        kw = p.get("pv_kw")
        if kw is None:
            from .solar import recommend_kw  # local import to avoid a cycle
            kw = recommend_kw(home)
        upd = {"pv_kw": max(home.pv_kw, float(kw)), "net_metered": True}
    else:
        raise ValueError(f"Unknown retrofit '{rid}'")
    return home.model_copy(update=upd)


def already_done(home: Home, rid: str) -> bool:
    return {
        "cool_roof": home.cool_roof,
        "roof_insulation": home.roof_insulation,
        "external_shading": home.shading == "full",
        "solar_film": home.solar_film,
        "ac_setpoint": home.n_ac > 0 and home.ac_setpoint_c >= 24,
        "smart_plug_tod": home.smart_plugs,
        "ac_5star_inverter": home.n_ac > 0 and home.ac_tech == "inverter" and home.ac_star == 5 and home.ac_age_years < 3,
        "bldc_fans": home.bldc_fan_share >= 0.99,
        "led_lighting": home.led_share >= 0.99,
        "fridge_5star": home.fridge_star == 5 and home.fridge_age_years < 5,
        "solar_water_heater": home.water_heating == "solar",
        "heat_pump_geyser": home.water_heating == "heat_pump",
        "induction_cooking": home.cooking == "induction",
        "lithium_battery": home.backup == "lithium",
        "rooftop_solar": home.pv_kw > 0 and home.pv_kw >= max_pv_kw(home) * 0.8,
    }[rid]


def feasibility(home: Home, rid: str) -> tuple[str, str]:
    """Return (suitability, reason). Hard rules first, then the climate-zone table."""
    zone = city(home.city).zone
    floor = home.floor_position
    tenant = home.tenure == "tenant"
    zs = zone_suitability()[rid][zone]

    if rid in ("cool_roof", "roof_insulation"):
        if not roof_exposed(home):
            return "Infeasible", f"No exposed roof above you ({floor}-floor flat), so roof work won't cut your heat gain."
        if tenant and rid == "roof_insulation":
            return "Low", "Structural work needs the owner's consent; ask your landlord."
    if rid in ("external_shading", "solar_film") and home.window_to_wall <= 0.12 and not home.west_glass:
        return "Low", "Little glazing, so there is little solar heat gain to block."
    if rid in ("ac_setpoint", "ac_5star_inverter", "smart_plug_tod") and home.n_ac == 0:
        return "Infeasible", "No AC in the home, so AC upgrades don't apply."
    if rid == "ac_5star_inverter" and home.ac_tech == "inverter" and home.ac_star >= 4 and home.ac_age_years < 4:
        return "Low", "Your AC is already an efficient inverter model; replacing it early wastes embodied carbon."
    if rid == "bldc_fans" and home.n_fans == 0:
        return "Infeasible", "No ceiling fans recorded."
    if rid == "fridge_5star" and home.fridge_star >= 4 and home.fridge_age_years < 6:
        return "Low", "Your fridge is fairly new and efficient."
    if rid in ("solar_water_heater", "heat_pump_geyser") and home.water_heating not in ("electric_geyser",):
        return "Infeasible", "No electric geyser to replace."
    if rid == "solar_water_heater" and not home.roof_access:
        return "Infeasible", "A solar water heater needs roof space you can use; consider a heat-pump geyser instead."
    if rid == "induction_cooking" and home.cooking != "lpg":
        return "Infeasible", "You don't cook on LPG."
    if rid == "lithium_battery" and home.backup != "lead_acid":
        return "Infeasible", "Only relevant if you have a lead-acid inverter battery."
    if rid == "rooftop_solar":
        if tenant:
            return "Infeasible", "PM Surya Ghar needs the roof and the electricity connection in the applicant's name; ask your society (RWA) about common solar."
        if not home.roof_access:
            return "Infeasible", "No private roof; your housing society can install common-area solar under the RWA scheme."
        if max_pv_kw(home) < 1.0:
            return "Infeasible", "Usable roof area is under 10 m2, too small for a 1 kW system."
    if tenant and rid in ("external_shading", "solar_water_heater", "heat_pump_geyser"):
        zs = min(zs, "Medium", key=lambda s: SUIT_ORDER[s])
        return zs, "Possible with the landlord's consent; portable options exist."

    reason = {
        "High": f"Well suited to the {zone.replace('_', '-')} climate zone.",
        "Medium": f"Moderate benefit in the {zone.replace('_', '-')} climate zone.",
        "Low": f"Small benefit in the {zone.replace('_', '-')} climate zone.",
    }[zs]
    if rid == "induction_cooking":
        reason += (" Removes LPG but increases your electricity use; on today's coal-heavy grid that raises CO2 "
                   "unless you also have rooftop solar.")
    return zs, reason


def cost_range(home: Home, rid: str, params: dict | None = None) -> tuple[float, float]:
    """Installed cost range in INR, before subsidy."""
    c = catalogue()[rid]
    lo, hi, basis = c["cost_min_inr"], c["cost_max_inr"], c["cost_basis"]
    if basis == "per_sqft_roof":
        n = roof_area_m2(home) * SQFT_PER_M2 if roof_area_m2(home) else (home.carpet_area_m2 or 90) * SQFT_PER_M2
    elif basis == "per_sqft_glass":
        n = (home.carpet_area_m2 or 90) * 0.35 * home.window_to_wall * SQFT_PER_M2 * (0.5 if home.west_glass else 0.35)
    elif basis == "per_ac":
        n = max(1, home.n_ac)
    elif basis == "per_fan":
        n = max(1, round(home.n_fans * (1 - home.bldc_fan_share)))
    elif basis == "per_point":
        n = max(1, round(home.light_points * (1 - home.led_share)))
    elif basis == "per_kw":
        from .solar import recommend_kw
        n = (params or {}).get("pv_kw") or recommend_kw(home)
    else:
        n = 1
    return round(lo * n, -2), round(hi * n, -2)


def central_solar_subsidy(kw: float) -> float:
    """PM Surya Ghar CFA for a residential system: Rs 30,000/kW up to 2 kW, Rs 18,000 for the 3rd kW, cap Rs 78,000."""
    total = 0.0
    for r in subsidy_rules():
        if r["segment"] != "residential":
            continue
        span = max(0.0, min(kw, r["kw_to"]) - r["kw_from"])
        total += span * r["inr_per_kw"]
    return min(total, 78000.0)


def state_solar_topup(state: str, kw: float) -> float:
    st = tariff_states()[state]
    return min(st["state_solar_topup_inr_per_kw"] * kw, st["state_solar_topup_cap_inr"])
