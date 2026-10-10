"""Backend pieces the web app relies on: my-homes listing, public config, signed Telegram deep links, SPA hosting."""
import time

import jwt

from greenghar.api.linking import make_token, read_token

SECRET = "test-secret-for-hs256-only-0123456789abcdef"


def bearer(sub):
    t = jwt.encode({"sub": sub, "aud": "authenticated", "exp": int(time.time()) + 600}, SECRET, algorithm="HS256")
    return {"Authorization": f"Bearer {t}"}


def test_my_homes_lists_only_owned(client, monkeypatch):
    monkeypatch.setenv("SUPABASE_JWT_SECRET", SECRET)
    body = {"city": "Pune", "carpet_area_m2": 80, "monthly_kwh": [200] * 12}
    hid = client.post("/homes", json=body, headers=bearer("owner-x")).json()["home"]["home_id"]
    mine = client.get("/homes", headers=bearer("owner-x")).json()
    assert [h["home_id"] for h in mine] == [hid] and mine[0]["city"] == "Pune"
    assert client.get("/homes", headers=bearer("someone-else")).json() == []
    assert client.get("/homes").json() == []


def test_public_config_has_no_secrets(client):
    c = client.get("/config").json()
    assert set(c) >= {"env", "auth", "telegram_bot_username", "demo_home_id"}
    assert "service" not in str(c).lower()


def test_link_token_roundtrip_and_tamper():
    t = make_token("H000011")["token"]
    assert len(t) <= 64 and read_token(t) == "H000011"
    assert read_token(t.replace("H000011", "H000012")) is None
    assert read_token(make_token("H000011", now=time.time() - 3600)["token"]) is None  # expired


def test_telegram_deeplink_links_chat(client, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_USERNAME", "GreenGharBot")
    r = client.post("/homes/H000011/telegram-link").json()
    assert r["deep_link"].startswith("https://t.me/GreenGharBot?start=")
    from greenghar.bot.telegram import TelegramBot
    from greenghar.data_access import LocalRepo
    from greenghar.llm.orchestrator import Advisor
    import tempfile
    bot = TelegramBot(LocalRepo(tempfile.mkdtemp()), Advisor(), send=lambda m, p: {"ok": True})
    out = bot.handle({"message": {"chat": {"id": 99}, "text": f"/start {r['token']}"}})
    assert out["home_id"] == "H000011"
    assert bot.handle({"message": {"chat": {"id": 98}, "text": "/start H000011_ffffffff_AAAAAAAAAAAAAAAA"}})["handled"] == "bad_link"


def test_spa_route_without_build(client):
    r = client.get("/app/plan")
    assert r.status_code in (200, 404)  # 200 once frontend/dist exists


def test_memory_constraints_can_be_undone():
    from greenghar.memory.store import constraints
    items = [{"kind": "constraint", "key": "exclude", "value": '"rooftop_solar"'}, {"kind": "constraint", "key": "budget_inr", "value": "50000"}]
    assert constraints(items) == {"exclude": ["rooftop_solar"], "budget_inr": 50000}
    items += [{"kind": "constraint", "key": "include", "value": '"rooftop_solar"'}, {"kind": "constraint", "key": "budget_inr", "value": "0"}]
    assert constraints(items) == {"exclude": []}
