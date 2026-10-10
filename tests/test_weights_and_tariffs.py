from greenghar.engine.score import BANDS, WEIGHTS, band
from greenghar.engine.tariff import annual_bill, energy_charge, marginal_rate, monthly_bill


def test_weights_fixed_and_sum_to_one():
    assert WEIGHTS == {"energy_efficiency": 0.25, "consumption_intensity": 0.20, "envelope": 0.15, "cooling_system": 0.15,
                       "windows_shading": 0.10, "renewables": 0.10, "smart_use": 0.05}
    assert abs(sum(WEIGHTS.values()) - 1) < 1e-12


def test_bands():
    assert [band(x) for x in (100, 80, 79, 65, 64, 50, 49, 30, 29, 0)] == [
        "Highly efficient", "Highly efficient", "Good", "Good", "Moderate", "Moderate", "Poor", "Poor", "Very poor", "Very poor"]
    assert [b for _, b in BANDS] == ["Highly efficient", "Good", "Moderate", "Poor", "Very poor"]


def test_telescopic_slabs_delhi():
    # 350 units: 200 x 3.00 + 150 x 4.50
    assert energy_charge("Delhi", 350) == 200 * 3.0 + 150 * 4.5


def test_free_units_scheme_zeroes_bill():
    assert monthly_bill("Delhi", 180) == 0
    assert monthly_bill("Punjab", 290) == 0
    assert monthly_bill("Maharashtra", 180) > 0


def test_telangana_category_switch():
    # below 200 units the cheaper LT-IA structure applies; above, the LT-IB structure (higher first slab)
    assert energy_charge("Telangana", 150) == 50 * 1.95 + 50 * 3.10 + 50 * 4.80
    assert energy_charge("Telangana", 250) == 200 * 5.10 + 50 * 7.70


def test_marginal_rate_rises_with_slab():
    assert marginal_rate("Maharashtra", 50) < marginal_rate("Maharashtra", 350) < marginal_rate("Maharashtra", 600)


def test_net_metering_credits_surplus():
    imp = [300] * 12
    exp = [400] * 12
    b = annual_bill("Gujarat", imp, exp, net_metered=True)
    assert b["export_credit_inr"] > 0 and b["net_annual_cost_inr"] < b["annual_bill_inr"]
