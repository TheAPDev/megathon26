"""Monthly end-use energy model for an Indian home.

Deterministic and documented. The home is modelled as cooling demand (driven by cooling degree-days
and the envelope) -> equipment efficiency -> electricity, plus fans, fridge, lighting, water heating,
plug loads, cooking fuel, backup losses and rooftop PV. Retrofits change the home's state and the
model is re-run, so interactions fall out naturally (a cool roof shrinks the load an inverter AC then
serves; solar is sized against what is left).
"""
from __future__ import annotations

from ..reference import DAYS_IN_MONTH, LPG_KWH_PER_CYLINDER, PV_MONTH_SHAPE, appl, catalogue, city
from ..schemas import EnergyBreakdown, Home

AC_COOLING_BASE_C = 24.0      # mean-temperature base for AC cooling degree-days
AC_HOURS_PER_DEGREE = 1.0     # AC run-hours per cooling degree-day
AC_MAX_HOURS_DAY = 16.0
AC_PART_LOAD = 0.5            # average part-load fraction of rated capacity
KW_PER_TON = 3.517
COOLER_W = 200.0
FAN_BASE_C = 20.0
FAN_USE_SHARE = 0.6          # share of installed fans running at a time
LIGHT_HOURS_DAY = 5.0
WATER_ZONE_FACTOR = {"cold": 1.6, "composite": 1.0, "temperate": 0.6, "hot_dry": 0.6, "warm_humid": 0.3}
DAYTIME_LOAD_SHARE = 0.35     # share of demand during solar hours (higher with work-from-home)
BATTERY_STANDBY_KWH_YR = {"none": 0.0, "lead_acid": 150.0, "lithium": 40.0, "dg_set": 0.0}
OUTAGE_LOAD_KW = 0.6          # average load carried by backup during outages


def ac_iseer(home: Home) -> float:
    variant = f"{home.ac_tech}_{ {1: '1star', 2: '1star', 3: '3star', 4: '3star', 5: '5star'}[home.ac_star] }"
    iseer = appl("ac", variant)
    if home.ac_star in (2, 4):  # interpolate between labelled points
        lo = appl("ac", f"{home.ac_tech}_{'1star' if home.ac_star == 2 else '3star'}")
        hi = appl("ac", f"{home.ac_tech}_{'3star' if home.ac_star == 2 else '5star'}")
        iseer = (lo + hi) / 2
    degradation = appl("ac", "degradation_per_year") / 100.0
    return iseer * max(0.6, 1 - degradation * home.ac_age_years)


def envelope_cooling_factor(home: Home) -> float:
    """Multiplier on cooling demand from the building envelope (1.0 = typical mid-floor flat)."""
    f = 1.0
    roof_exposed = home.floor_position == "top" or home.dwelling_type != "apartment"
    if roof_exposed:
        roof = 1.25
        if home.cool_roof:
            roof *= 1 - catalogue()["cool_roof"]["effect_value"]
        if home.roof_insulation:
            roof *= 1 - catalogue()["roof_insulation"]["effect_value"]
        f *= roof
    f *= {"solid_brick": 1.05, "hollow_block": 1.0, "aac": 0.94}[home.wall_type]
    glass = 1 + 0.35 * max(0.0, home.window_to_wall - 0.15)
    if home.west_glass:
        glass *= 1.08
    shade_cut = catalogue()["external_shading"]["effect_value"]
    glass_shading = {"none": 1.0, "partial": 1 - shade_cut / 2, "full": 1 - shade_cut}[home.shading]
    if home.solar_film:
        glass_shading *= 1 - catalogue()["solar_film"]["effect_value"]
    f *= glass * glass_shading
    return f


def setpoint_factor(setpoint_c: float) -> float:
    """BEE: about 6% saving per degree above 24 C (and 6% penalty per degree below)."""
    return max(0.5, 1 - 0.06 * (setpoint_c - 24.0))


def modeled_energy(home: Home) -> EnergyBreakdown:
    c = city(home.city)
    zone = c.zone
    area = home.carpet_area_m2 or 90.0
    iseer = ac_iseer(home) if home.n_ac else 1.0
    env = envelope_cooling_factor(home)
    sp = setpoint_factor(home.ac_setpoint_c)
    smart = 0.95 if home.smart_plugs else 1.0
    cap_kw = home.ac_tonnage * KW_PER_TON

    cooling = fans = fridge = lighting = water = plug = cook_el = losses = 0.0
    monthly_demand = []
    enduse = {k: [] for k in ("cooling", "fans_coolers", "fridge", "lighting", "water_heating", "plug_other", "cooking_electric", "backup_losses")}
    fridge_annual = appl("fridge", f"{home.fridge_star}star") * (1 + 0.02 * home.fridge_age_years)
    fan_w = home.n_fans * (home.bldc_fan_share * appl("fan", "bldc") + (1 - home.bldc_fan_share) * appl("fan", "induction"))
    light_w = home.light_points * (home.led_share * appl("lighting", "led") + (1 - home.led_share) * appl("lighting", "cfl_incandescent_mix"))
    water_annual = 0.0
    if home.water_heating == "electric_geyser":
        water_annual = appl("geyser", "electric_storage") * home.occupants * WATER_ZONE_FACTOR[zone]
    elif home.water_heating == "heat_pump":
        water_annual = appl("geyser", "electric_storage") * home.occupants * WATER_ZONE_FACTOR[zone] * (1 - catalogue()["heat_pump_geyser"]["effect_value"])
    elif home.water_heating == "solar":
        water_annual = appl("geyser", "electric_storage") * home.occupants * WATER_ZONE_FACTOR[zone] * (1 - catalogue()["solar_water_heater"]["effect_value"])  # backup element
    water_weights = [max(0.5, 26 - t) for t in c.temps]
    ww = sum(water_weights)
    plug_annual = 250 + 80 * home.occupants + 1.0 * area
    lpg_kwh = 0.0
    if home.cooking == "lpg":
        cyl = home.lpg_cylinders_per_year if home.lpg_cylinders_per_year is not None else 2.0 + 1.75 * home.occupants
        lpg_kwh = cyl * LPG_KWH_PER_CYLINDER
    elif home.cooking == "induction":
        base_cyl = 2.0 + 1.75 * home.occupants
        cook_el = base_cyl * LPG_KWH_PER_CYLINDER * appl("cooking", "lpg_stove") / appl("cooking", "induction")
    outage_kwh_month = home.outage_hours_month * OUTAGE_LOAD_KW
    loss_rate = {"none": 0.0, "lead_acid": 1 / appl("battery", "lead_acid") - 1,
                 "lithium": 1 / appl("battery", "lithium") - 1, "dg_set": 0.0}[home.backup]
    dg_kwh = outage_kwh_month * 12 if home.backup == "dg_set" else 0.0

    for m in range(12):
        t = c.temps[m]
        d = DAYS_IN_MONTH[m]
        cdd = max(0.0, t - AC_COOLING_BASE_C) * d
        ac_hours = min(AC_MAX_HOURS_DAY * d, AC_HOURS_PER_DEGREE * cdd * env * sp)
        cool_m = home.n_ac * ac_hours * cap_kw * AC_PART_LOAD / iseer * smart
        fan_hours = FAN_USE_SHARE * min(14.0, max(0.0, 3.0 + 0.8 * (t - FAN_BASE_C))) * d
        cooler_hours = min(12.0, max(0.0, 1.0 * (t - 26.0))) * d if zone in ("hot_dry", "composite") else 0.0
        fans_m = fan_w * fan_hours / 1000 + home.n_coolers * COOLER_W * cooler_hours / 1000
        fridge_m = fridge_annual / 12 * (1 + 0.012 * (t - 25))
        light_m = light_w * LIGHT_HOURS_DAY * d / 1000
        water_m = water_annual * water_weights[m] / ww
        plug_m = plug_annual / 12
        cook_m = cook_el / 12
        loss_m = (outage_kwh_month * loss_rate + BATTERY_STANDBY_KWH_YR[home.backup] / 12) if home.backup in ("lead_acid", "lithium") else 0.0
        cooling += cool_m; fans += fans_m; fridge += fridge_m; lighting += light_m
        water += water_m; plug += plug_m; losses += loss_m
        monthly_demand.append(cool_m + fans_m + fridge_m + light_m + water_m + plug_m + cook_m + loss_m)
        for k, v in zip(enduse, (cool_m, fans_m, fridge_m, light_m, water_m, plug_m, cook_m, loss_m)):
            enduse[k].append(v)

    total = sum(monthly_demand)
    pv_gen = pv_self = 0.0
    monthly_import, monthly_gen = [], []
    daytime = DAYTIME_LOAD_SHARE + (0.15 if home.wfh else 0.0)
    for m in range(12):
        gen_m = home.pv_kw * c.pv_yield * PV_MONTH_SHAPE[m]
        self_m = min(gen_m, monthly_demand[m] * daytime)  # physical self-consumption; rest is exported
        pv_gen += gen_m
        monthly_gen.append(gen_m)
        pv_self += self_m
        monthly_import.append(max(0.0, monthly_demand[m] - self_m))
    return EnergyBreakdown(
        cooling=cooling, fans_coolers=fans, fridge=fridge, lighting=lighting, water_heating=water,
        plug_other=plug, cooking_electric=cook_el, backup_losses=losses, total_electric_demand=total,
        pv_generation=pv_gen, pv_self_consumed=pv_self, pv_exported=max(0.0, pv_gen - pv_self),
        grid_import=sum(monthly_import), lpg_kwh=lpg_kwh, dg_kwh=dg_kwh,
        monthly_grid_import=monthly_import, monthly_pv_generation=monthly_gen, monthly_enduse=enduse,
    )
