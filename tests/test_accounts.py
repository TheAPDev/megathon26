"""Username + password sign-up: validation, the Supabase calls it makes, and error mapping (no network)."""
import httpx
import pytest

from greenghar.api.routers import accounts as A


class Resp:
    def __init__(self, status, data):
        self.status_code, self._d, self.content = status, data, b"x"

    def json(self):
        return self._d


@pytest.fixture
def sb(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "svc")

    class Hold:
        reply = Resp(200, {"id": "u1"})
        calls: list = []

    h = Hold()
    h.calls = []

    def post(url, **kw):
        h.calls.append((url, kw))
        return h.reply

    monkeypatch.setattr(A.httpx, "post", post)
    return h


def test_username_rules():
    assert A.normalize_username("  Asha.K_22 ") == "asha.k_22"
    for bad in ("ab", "has space", "a@b.com", "-start", "x" * 31, "dot..dot", "end."):
        with pytest.raises(A.APIError) as e:
            A.normalize_username(bad)
        assert e.value.code == "invalid_username"


def test_password_rules():
    A.check_password("monsoon2026", "asha")
    for bad in ("short1", "12345678", "onlyletters", "ashaasha"):
        with pytest.raises(A.APIError):
            A.check_password(bad, "ashaasha")


def test_signup_uses_admin_api_with_confirmed_email(client, sb):
    r = client.post("/auth/signup", json={"username": "Asha", "password": "monsoon2026"})
    assert r.status_code == 200 and r.json() == {"username": "asha", "created": True}
    url, kw = sb.calls[0]
    assert url.endswith("/auth/v1/admin/users") and kw["json"]["email"] == f"asha@{A.DEFAULT_DOMAIN}"
    assert kw["json"]["email_confirm"] is True and kw["headers"]["Authorization"] == "Bearer svc"


def test_duplicate_username_is_409(client, sb):
    sb.reply = Resp(422, {"error_code": "email_exists"})
    r = client.post("/auth/signup", json={"username": "asha", "password": "monsoon2026"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "username_taken"


def test_public_signup_fallback_needs_confirm_off(client, sb, monkeypatch):
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY")
    sb.reply = Resp(200, {"id": "u1"})  # no access_token => project still requires email confirmation
    r = client.post("/auth/signup", json={"username": "asha", "password": "monsoon2026"})
    assert r.status_code == 503 and r.json()["error"]["code"] == "confirmation_required"
    assert sb.calls[0][0].endswith("/auth/v1/signup") and sb.calls[0][1]["headers"] == {"apikey": "anon"}
    sb.reply = Resp(200, {"access_token": "t"})
    assert client.post("/auth/signup", json={"username": "asha2", "password": "monsoon2026"}).status_code == 200


def test_unconfigured_and_unreachable(client, monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    assert client.post("/auth/signup", json={"username": "asha", "password": "monsoon2026"}).json()["error"]["code"] == "signup_unavailable"
    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "a")
    monkeypatch.setattr(A.httpx, "post", lambda *a, **k: (_ for _ in ()).throw(httpx.ConnectError("down")))
    assert client.post("/auth/signup", json={"username": "asha", "password": "monsoon2026"}).status_code == 502


def test_config_publishes_domain_only_when_login_on(client, monkeypatch):
    assert client.get("/config").json()["auth"]["username_domain"] is None
    monkeypatch.setenv("GG_LOGIN", "on")
    assert client.get("/config").json()["auth"]["username_domain"] == A.DEFAULT_DOMAIN
