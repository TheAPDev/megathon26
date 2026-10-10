"""Connect the API to the green-ghar Supabase project and verify the connection.

    python scripts/connect_supabase.py           # asks for the service-role key once, tests, saves to .env
    python scripts/connect_supabase.py --check   # only tests the current .env

The service-role key is in Supabase Dashboard -> Project Settings -> API Keys (secret / service_role).
It stays in .env on this machine only (server-side; never put it in the web app).
"""
from __future__ import annotations

import getpass
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import os  # noqa: E402

import httpx  # noqa: E402

import greenghar  # noqa: E402,F401  (loads .env)

ENV = ROOT / ".env" if (ROOT / ".env").exists() or not (ROOT / "local.env").exists() else ROOT / "local.env"


def set_env(key: str, value: str) -> None:
    lines = ENV.read_text(encoding="utf-8").splitlines() if ENV.exists() else []
    out, done = [], False
    for ln in lines:
        if ln.split("=", 1)[0].strip() == key:
            out.append(f"{key}={value}")
            done = True
        else:
            out.append(ln)
    if not done:
        out.append(f"{key}={value}")
    ENV.write_text("\n".join(out) + "\n", encoding="utf-8")


def check(url: str, service: str, anon: str | None) -> bool:
    ok = True
    from greenghar.db.supabase_repo import service_headers
    h = service_headers(service)
    tests = [
        ("homes table", "GET", f"{url}/rest/v1/homes?select=home_id&limit=1", None),
        ("home scores", "GET", f"{url}/rest/v1/home_scores?select=home_id,score&limit=1", None),
        ("portfolio RPC", "POST", f"{url}/rest/v1/rpc/portfolio_summary", {}),
        ("real-data RPC", "POST", f"{url}/rest/v1/rpc/real_sources", {}),
        ("bills storage bucket", "GET", f"{url}/storage/v1/bucket/bills", None),
    ]
    with httpx.Client(timeout=20, headers=h) as c:
        for name, m, u, body in tests:
            try:
                r = c.request(m, u, json=body)
                good = r.status_code == 200
                detail = f"{r.status_code}" + ("" if good else f" {r.text[:120]}")
            except httpx.HTTPError as e:
                good, detail = False, str(e)
            ok &= good
            print(f"  {'OK ' if good else 'FAIL'} {name}: {detail}")
    if anon:
        try:
            r = httpx.get(f"{url}/auth/v1/settings", headers={"apikey": anon}, timeout=20)
            print(f"  {'OK ' if r.status_code == 200 else 'FAIL'} auth (anon key): {r.status_code}")
        except httpx.HTTPError as e:
            print(f"  FAIL auth (anon key): {e}")
    return ok


def main() -> int:
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    if not url:
        print("SUPABASE_URL is missing from .env")
        return 1
    service = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not service and "--check" not in sys.argv:
        service = getpass.getpass("Paste the Supabase service-role (secret) key: ").strip()
    if not service:
        print("No service-role key: the API will keep serving the local dataset (GG_REPO=local).")
        return 1
    print(f"Testing {url} ...")
    if not check(url, service, os.environ.get("SUPABASE_ANON_KEY")):
        print("Connection test failed; .env not changed. Check the key, and that the project is not paused "
              "(free projects pause after 7 days without activity: Dashboard -> Restore project).")
        return 1
    if "--check" not in sys.argv:
        set_env("SUPABASE_SERVICE_ROLE_KEY", service)
        set_env("GG_REPO", "supabase")
        set_env("GG_DEMO_HOME", "HD000015")  # the live database numbers its homes HD......
        set_env("GG_LOGIN", "on")  # username + password sign-up works because the server can create confirmed accounts
        print("Saved. GG_REPO=supabase: the API now reads and writes the Supabase project, and the username/password login screen is on. Restart the server.")
    else:
        print("Supabase connection OK.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
