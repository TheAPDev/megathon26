import time

import pytest


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


@pytest.mark.parametrize("path", ["/homes/H000011/score", "/homes/H000011/plan", "/homes/H000011/value", "/homes/H000011/solar",
                                  "/homes/H000011/roadmap?budget_inr=50000", "/homes/H000011/heatwave", "/homes/H000011/journey",
                                  "/portfolio/summary", "/portfolio/ranking?limit=5", "/portfolio/targets?limit=5", "/portfolio/map",
                                  "/lab/metrics", "/lab/factors", "/reference/cities", "/reference/tariffs/Delhi"])
def test_get_routes(client, path):
    assert client.get(path).status_code == 200


def test_scenario_under_300ms(client):
    body = {"retrofits": ["cool_roof", "ac_5star_inverter", "rooftop_solar"]}
    client.post("/homes/H000011/scenario", json=body)
    times = []
    for _ in range(5):
        t = time.perf_counter()
        r = client.post("/homes/H000011/scenario", json=body)
        times.append(time.perf_counter() - t)
        assert r.status_code == 200
    assert sorted(times)[2] < 0.3


def test_error_format(client):
    r = client.get("/homes/NOPE/score")
    assert r.status_code == 404 and r.json()["error"]["code"] == "home_not_found" and r.json()["error"]["request_id"]
    r = client.post("/homes/H000011/scenario", json={"retrofits": ["teleporter"]})
    assert r.status_code == 422 and r.json()["error"]["code"] == "unknown_retrofit"
    r = client.post("/homes", json={"city": "Atlantis"})
    assert r.status_code == 422


def test_advisor_chat_grounded(client):
    r = client.post("/advisor/chat", json={"home_id": "H000011", "message": "AC ka bill kam kaise hoga?", "use_llm": False})
    assert r.status_code == 200 and r.json()["grounding"]["grounded"]


def test_memory_changes_plan(client):
    r = client.post("/homes/H000020/memory", json={"kind": "constraint", "key": "exclude", "value": "led_lighting"})
    assert r.status_code == 201
    ch = r.json()["what_changed"]["changes"]
    assert any(c["retrofit_id"] == "led_lighting" for c in ch) or ch == []


def test_lab_scenarios_all_pass(client):
    r = client.get("/lab/scenarios?monotonicity_homes=30").json()
    assert r["passed"] == r["total"]


def test_telegram_demo_flow(client):
    r = client.post("/telegram/webhook", json={"update_id": 1, "message": {"chat": {"id": 42}, "text": "/start"}})
    assert r.json()["handled"] == "start"
    r = client.post("/telegram/webhook", json={"update_id": 2, "callback_query": {"id": "c", "data": "demo", "message": {"chat": {"id": 42}}}})
    assert r.json()["handled"] == "score"
    r = client.post("/telegram/webhook", json={"update_id": 3, "message": {"chat": {"id": 42}, "text": "What if I add BLDC fans?"}})
    assert r.json()["grounded"] is True
