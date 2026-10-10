"""Property-based: a better state never scores lower (hypothesis)."""
from hypothesis import given, settings
from hypothesis import strategies as st

from greenghar.engine import retrofits as R
from greenghar.engine.score import score_home
from greenghar.lab import monotonicity_sample
from greenghar.reference import cities
from greenghar.schemas import Home

COMPONENTS = ("energy_efficiency", "envelope", "cooling_system", "windows_shading", "renewables", "smart_use")
IMPROVEMENTS = ["cool_roof", "roof_insulation", "external_shading", "solar_film", "ac_5star_inverter", "bldc_fans",
                "led_lighting", "fridge_5star", "rooftop_solar", "smart_plug_tod", "ac_setpoint", "solar_water_heater"]

homes = st.builds(
    Home, home_id=st.just("P"), monthly_kwh=st.just([300.0] * 12), city=st.sampled_from(sorted(cities())),
    dwelling_type=st.sampled_from(["apartment", "independent_house", "row_house"]),
    floor_position=st.sampled_from(["ground", "middle", "top"]), carpet_area_m2=st.floats(30, 300),
    n_ac=st.integers(0, 4), ac_star=st.integers(1, 5), ac_tech=st.sampled_from(["fixed", "inverter"]),
    ac_age_years=st.floats(0, 15), ac_setpoint_c=st.sampled_from([18, 20, 22, 23, 24, 25, 26]),
    roof_access=st.booleans(), roof_area_m2=st.floats(0, 150), bldc_fan_share=st.floats(0, 1), led_share=st.floats(0, 1),
    fridge_star=st.integers(1, 5), shading=st.sampled_from(["none", "partial"]), west_glass=st.booleans(),
    window_to_wall=st.floats(0.05, 0.6), wall_type=st.sampled_from(["solid_brick", "hollow_block", "aac"]),
    water_heating=st.sampled_from(["electric_geyser", "none", "gas"]), n_fans=st.integers(0, 10),
    tenure=st.sampled_from(["owner", "tenant"]))


@settings(max_examples=150, deadline=None)
@given(h=homes, rid=st.sampled_from(IMPROVEMENTS))
def test_improvement_never_lowers_a_subscore(h, rid):
    if R.feasibility(h, rid)[0] == "Infeasible" or R.already_done(h, rid):
        return
    before = {c.component: c.score for c in score_home(h).components}
    after = {c.component: c.score for c in score_home(R.apply(h, rid)).components}
    for comp in COMPONENTS:
        assert after[comp] >= before[comp] - 1e-9, (rid, comp, before[comp], after[comp])


@settings(max_examples=100, deadline=None)
@given(h=homes, factor=st.floats(0.3, 0.95))
def test_lower_metered_use_never_lowers_intensity_score(h, factor):
    lower = h.model_copy(update={"monthly_kwh": [x * factor for x in h.monthly_kwh]})
    s = {c.component: c.score for c in score_home(h).components}["consumption_intensity"]
    s2 = {c.component: c.score for c in score_home(lower).components}["consumption_intensity"]
    assert s2 >= s - 1e-9


def test_random_population_sweep():
    r = monotonicity_sample(200)
    assert r["failures"] == 0 and r["checks"] > 5000
