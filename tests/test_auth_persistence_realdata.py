"""Auth (Supabase JWT ownership rules), durable runtime writes, rate limiting and the real-data layer."""
import json
import time

import jwt
import pytest

SECRET = "test-secret-for-hs256-only-0123456789abcdef"
HOME = {"city": "Hyderabad", "dwelling_type": "apartment", "carpet_area_m2": 90, "occupants": 4, "n_ac": 1, "ac_star": 3,
        "monthly_kwh": [210, 230, 320, 420, 480, 400, 330, 300, 290, 280, 240, 220]}


def token(sub: str, role: str | None = None, exp: int = 3600) -> str:
    claims = {"sub": sub, "aud": "authenticated", "exp": int(time.time()) + exp, "email": f"{sub}@example.com"}
    if role:
        claims["app_metadata"] = {"app_role": role}
    return jwt.encode(claims, SECRET, algorithm="HS256")


def bearer(t: str) -> dict:
    return {"Authorization": f"Bearer {t}"}


@pytest.fixture
def jwt_env(monkeypatch):
    monkeypatch.setenv("SUPABASE_JWT_SECRET", SECRET)


def test_owner_can_read_other_customer_cannot(client, jwt_env):
    r = client.post("/homes", json=HOME, headers=bearer(token("user-a")))
    assert r.status_code == 201
    hid = r.json()["home"]["home_id"]
    assert client.get(f"/homes/{hid}/score", headers=bearer(token("user-a"))).status_code == 200
    r = client.get(f"/homes/{hid}/score", headers=bearer(token("user-b")))
    assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden"
    assert client.get(f"/homes/{hid}/score", headers=bearer(token("analyst-1", "analyst"))).status_code == 200
    # cannot overwrite someone else's home by re-posting its id
    assert client.post("/homes", json={**HOME, "home_id": hid}, headers=bearer(token("user-b"))).status_code == 403


def test_bad_and_expired_tokens_rejected(client, jwt_env):
    assert client.get("/homes/H000011/score", headers=bearer("not-a-jwt")).status_code == 401
    r = client.get("/homes/H000011/score", headers=bearer(token("user-a", exp=-60)))
    assert r.status_code == 401 and r.json()["error"]["code"] == "invalid_token"


def test_prod_requires_token_and_linked_home(client, jwt_env, monkeypatch):
    monkeypatch.setenv("GG_ENV", "prod")
    assert client.get("/homes/H000011/score").status_code == 401
    assert client.get("/homes/H000011/score", headers=bearer(token("user-z"))).status_code == 403  # not linked to this user


def test_portfolio_accepts_analyst_jwt_only(client, jwt_env):
    assert client.get("/portfolio/summary", headers=bearer(token("analyst-1", "analyst"))).status_code == 200
    assert client.get("/portfolio/summary", headers=bearer(token("user-a"))).status_code == 403


def test_advisor_turns_are_logged(client):
    from greenghar.api.deps import get_repo
    repo = get_repo()
    before = len(repo._read("advisor_logs"))
    r = client.post("/advisor/chat", json={"home_id": "H000011", "message": "why is my score low?", "use_llm": False})
    assert r.status_code == 200
    rows = repo._read("advisor_logs")
    assert len(rows) == before + 1 and rows[-1]["channel"] == "api" and rows[-1]["grounded"] is True
    assert rows[-1]["figures_verified"] == rows[-1]["figures_total"]


def test_rate_limit(client, monkeypatch):
    from greenghar.api import deps
    monkeypatch.setattr(deps.settings, "rate_limit_per_min", 2)
    deps._hits.clear()
    body = {"home_id": "H000011", "message": "tips?", "use_llm": False}
    codes = [client.post("/advisor/chat", json=body).status_code for _ in range(3)]
    assert codes == [200, 200, 429]
    deps._hits.clear()


def test_runtime_writes_survive_restart(tmp_path):
    from greenghar.data_access import LocalRepo
    from greenghar.schemas import Home
    r1 = LocalRepo(tmp_path)
    r1.put_home(Home(home_id="U-persist", **HOME), owner="user-a")
    r1.save_telegram_link(42, "U-persist", "hi")
    stored = r1.save_bill_upload("U-persist", b"\xff\xd8fakejpeg", "image/jpeg", {"provider": "test", "warnings": [], "months_found": 3})
    r2 = LocalRepo(tmp_path)  # "restart"
    assert r2.get_home("U-persist").city == "Hyderabad" and r2.owner_of("U-persist") == "user-a"
    assert r2.get_telegram_link(42)["language"] == "hi"
    assert (tmp_path / stored["storage_path"]).read_bytes() == b"\xff\xd8fakejpeg"
    assert json.loads((tmp_path / "bill_uploads.jsonl").read_text().splitlines()[-1])["provider"] == "test"


def test_telegram_session_restored_from_repo(tmp_path):
    from greenghar.bot.telegram import TelegramBot
    from greenghar.data_access import LocalRepo
    from greenghar.llm.orchestrator import Advisor
    repo = LocalRepo(tmp_path)
    sent = []
    bot = TelegramBot(repo, Advisor(), send=lambda m, p: sent.append((m, p)) or {"ok": True})
    bot.handle({"message": {"chat": {"id": 7}, "text": "demo"}})
    home_id = bot.session(7)["home_id"]
    bot2 = TelegramBot(LocalRepo(tmp_path), Advisor(), send=lambda m, p: {"ok": True})  # new process
    assert bot2.session(7)["home_id"] == home_id
    out = bot2.handle({"message": {"chat": {"id": 7}, "text": "how can I save money?"}})
    assert out["handled"] != "no_home"
    assert LocalRepo(tmp_path)._read("advisor_logs")[-1]["channel"] == "telegram"


def test_portfolio_routes_go_through_repo(client, monkeypatch):
    from greenghar.api.deps import get_repo
    calls = []
    repo = get_repo()
    orig = repo.portfolio
    monkeypatch.setattr(repo, "portfolio", lambda name, **kw: calls.append(name) or orig(name, **kw))
    assert client.get("/portfolio/ranking?limit=3").status_code == 200
    assert client.get("/portfolio/rwa-leads?limit=3").status_code == 200
    assert calls == ["ranking", "rwa_leads"]


def test_real_data_state_profile_and_calibration(client):
    from greenghar import realdata
    if not realdata.available():
        pytest.skip("run scripts/fetch_real_data.py")
    r = client.get("/reference/real/state/Telangana")
    assert r.status_code == 200
    p = r.json()
    assert 95 <= p["clean_cooking_urban_pct"] <= 100 and 3 < p["mean_hh_size_2011"] < 6
    assert client.get("/reference/real/state/Atlantis").status_code == 404
    cal = client.get("/reference/real/calibration").json()
    assert {"state", "synth_owned_pct", "real_owned_pct_2011"} <= set(cal[0])
    assert any(s["source_id"] == "open_meteo_archive" for s in client.get("/reference/real/sources").json())


def test_real_weather_needs_database_locally(client):
    assert client.get("/reference/real/city/Delhi").status_code == 404
    assert client.get("/homes/H000011/weather-signature").status_code == 404


def test_service_headers_for_legacy_and_new_secret_keys():
    from greenghar.db.supabase_repo import service_headers
    assert service_headers("eyJhbGciOi.x.y") == {"apikey": "eyJhbGciOi.x.y", "Authorization": "Bearer eyJhbGciOi.x.y"}
    assert service_headers("sb_secret_abc") == {"apikey": "sb_secret_abc"}  # opaque keys are never sent as Bearer


def test_env_template_comments_do_not_become_values(tmp_path, monkeypatch):
    import os

    from greenghar import _load_dotenv
    f = tmp_path / "x.env"
    f.write_text("GGT_A=            # paste key here\nGGT_B=abc   # note\nGGT_C=\"q # r\"\nGGT_D=plain\n")
    for k in "ABCD":
        monkeypatch.delenv(f"GGT_{k}", raising=False)
    _load_dotenv(f)
    assert [os.environ[f"GGT_{k}"] for k in "ABCD"] == ["", "abc", "q # r", "plain"]
    for k in "ABCD":
        os.environ.pop(f"GGT_{k}", None)
