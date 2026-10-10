"""The five scenarios the judges said they would throw, plus the worked example."""
from greenghar import lab


def test_missing_data():
    assert lab.scenario_missing_data()["passed"]


def test_conflicting_data():
    assert lab.scenario_conflict()["passed"]


def test_infeasible_retrofit_refused_with_reason():
    assert lab.scenario_infeasible()["passed"]


def test_fuel_switch_negative_electricity_saving():
    r = lab.scenario_fuel_switch()
    assert r["passed"], r
    assert r["observed"]["electricity_saving_kwh"] < 0


def test_value_unavailable_when_info_missing(value_fn):
    assert lab.scenario_value_unavailable(value_fn)["passed"]


def test_worked_example_reproduces():
    assert lab.worked_example()["passed"]


def test_package_savings_are_not_summed():
    from greenghar.engine.plan import run_scenario
    from greenghar.schemas import Home
    h = Home(home_id="P", **{**lab.BASE, "dwelling_type": "independent_house"})
    pkg = run_scenario(h, ["cool_roof", "roof_insulation", "ac_5star_inverter"])
    alone = sum(run_scenario(h, [r])["per_fuel_saving_kwh"]["electricity"] for r in ["cool_roof", "roof_insulation", "ac_5star_inverter"])
    assert pkg["per_fuel_saving_kwh"]["electricity"] < alone  # interactions shrink the package total
    assert abs(sum(s["saving_kwh_electricity"] for s in pkg["steps"]) - pkg["per_fuel_saving_kwh"]["electricity"]) < 1.0


def test_solar_cuts_imports_not_demand():
    from greenghar.engine.physics import modeled_energy
    from greenghar.schemas import Home
    h = Home(home_id="P", **lab.BASE)
    e0, e1 = modeled_energy(h), modeled_energy(h.model_copy(update={"pv_kw": 3}))
    assert abs(e0.total_electric_demand - e1.total_electric_demand) < 1e-6
    assert e1.grid_import < e0.grid_import
    assert abs(e1.pv_generation - e1.pv_self_consumed - e1.pv_exported) < 1e-6
