"""Username + password accounts on top of Supabase Auth.

Supabase Auth identifies users by email, so a username maps to a private, never-mailed address
`<username>@<GG_USERNAME_DOMAIN>`. Sign-in happens in the browser (supabase-js `signInWithPassword`, anon key);
sign-up goes through this route so the account is created already confirmed (service-role key stays on the server).
Without the service-role key it falls back to the public sign-up endpoint, which only works when the project has
"Confirm email" switched off."""
from __future__ import annotations

import os
import re

import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ...db.supabase_repo import service_headers
from ..deps import APIError, rate_limit

router = APIRouter(prefix="/auth", tags=["auth"])

USERNAME = re.compile(r"^[a-z0-9][a-z0-9_.]{2,29}$")
DEFAULT_DOMAIN = "gg-users.example.com"  # example.com subdomains are reserved by IANA: valid syntax, can never receive mail


def username_domain() -> str:
    return os.environ.get("GG_USERNAME_DOMAIN", DEFAULT_DOMAIN).strip().lstrip("@")


def normalize_username(raw: str) -> str:
    u = (raw or "").strip().lower()
    if not USERNAME.match(u) or ".." in u or u.endswith("."):
        raise APIError(422, "invalid_username", "Username must be 3-30 characters: letters, numbers, dot or underscore, starting with a letter or number.")
    return u


def check_password(pw: str, username: str) -> None:
    if not (8 <= len(pw) <= 72):
        raise APIError(422, "weak_password", "Password must be 8 to 72 characters.")
    if pw.lower() == username or pw.isdigit() or pw.isalpha():
        raise APIError(422, "weak_password", "Use a mix of letters and numbers, and not your username.")


class SignupIn(BaseModel):
    username: str
    password: str


@router.post("/signup", summary="Create a username + password account", dependencies=[Depends(rate_limit)])
def signup(body: SignupIn) -> dict:
    username = normalize_username(body.username)
    check_password(body.password, username)
    url = (os.environ.get("SUPABASE_URL") or "").rstrip("/")
    service, anon = os.environ.get("SUPABASE_SERVICE_ROLE_KEY"), os.environ.get("SUPABASE_ANON_KEY")
    if not url or not (service or anon):
        raise APIError(503, "signup_unavailable", "Accounts are not configured on this server.")
    email = f"{username}@{username_domain()}"
    try:
        if service:
            r = httpx.post(f"{url}/auth/v1/admin/users", timeout=15,
                           headers=service_headers(service),
                           json={"email": email, "password": body.password, "email_confirm": True,
                                 "user_metadata": {"username": username}})
        else:
            r = httpx.post(f"{url}/auth/v1/signup", timeout=15, headers={"apikey": anon},
                           json={"email": email, "password": body.password, "data": {"username": username}})
    except httpx.HTTPError as e:
        raise APIError(502, "auth_unreachable", "Could not reach the sign-in service. Try again.") from e
    data = r.json() if r.content else {}
    code = str(data.get("error_code") or data.get("code") or "")
    if r.status_code in (400, 409, 422):
        if code in ("email_exists", "user_already_exists") or "already" in str(data.get("msg") or data.get("message") or "").lower():
            raise APIError(409, "username_taken", "That username is taken. Pick another.")
        if code == "weak_password":
            raise APIError(422, "weak_password", "That password is too easy to guess. Try a longer one.")
        raise APIError(422, "signup_rejected", "Could not create the account with those details.")
    if r.status_code == 429:
        raise APIError(429, "rate_limited", "Too many sign-ups. Try again in a few minutes.")
    if r.status_code >= 400:
        raise APIError(502, "auth_error", "The sign-in service returned an error. Try again.")
    if not service and not data.get("access_token"):
        raise APIError(503, "confirmation_required",
                       "This project still requires email confirmation. Turn off 'Confirm email' in Supabase "
                       "(Authentication > Providers > Email) or set SUPABASE_SERVICE_ROLE_KEY.")
    return {"username": username, "created": True}
