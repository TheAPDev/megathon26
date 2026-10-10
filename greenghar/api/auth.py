"""Supabase Auth JWT verification and home-ownership checks.

- Asymmetric signing keys (default for new projects): verified against the project's JWKS
  (`<SUPABASE_URL>/auth/v1/.well-known/jwks.json`, cached 10 min).
- Legacy HS256 projects: set SUPABASE_JWT_SECRET.
- GG_ENV=dev with no auth configured: requests may be anonymous (the demo works without logins).
- GG_ENV=prod: a valid bearer token is required on customer routes; analysts (app_metadata.app_role =
  'analyst') may read any home, customers only their own.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Optional

import httpx
import jwt
from fastapi import Header, HTTPException

_JWKS: dict = {"keys": None, "at": 0.0}


@dataclass
class User:
    sub: str
    role: str  # 'customer' | 'analyst'
    email: Optional[str] = None
    phone: Optional[str] = None


def _env() -> str:
    return os.environ.get("GG_ENV", "dev")


def auth_configured() -> bool:
    return bool(os.environ.get("SUPABASE_JWT_SECRET") or os.environ.get("SUPABASE_URL"))


def _jwks() -> list[dict]:
    if _JWKS["keys"] is None or time.time() - _JWKS["at"] > 600:
        url = os.environ["SUPABASE_URL"].rstrip("/") + "/auth/v1/.well-known/jwks.json"
        r = httpx.get(url, timeout=10)
        r.raise_for_status()
        _JWKS.update(keys=r.json().get("keys", []), at=time.time())
    return _JWKS["keys"]


def verify_token(token: str) -> User:
    secret = os.environ.get("SUPABASE_JWT_SECRET")
    try:
        if secret:
            claims = jwt.decode(token, secret, algorithms=["HS256"], audience="authenticated")
        else:
            kid = jwt.get_unverified_header(token).get("kid")
            key = next((k for k in _jwks() if k.get("kid") == kid), None)
            if key is None:
                raise jwt.InvalidTokenError("unknown signing key")
            pub = jwt.PyJWK(key)
            claims = jwt.decode(token, pub.key, algorithms=[pub.algorithm_name], audience="authenticated")
    except (jwt.InvalidTokenError, httpx.HTTPError, KeyError) as e:
        raise HTTPException(status_code=401, detail={"code": "invalid_token", "message": f"Invalid or expired token: {e}"})
    role = "analyst" if (claims.get("app_metadata") or {}).get("app_role") == "analyst" else "customer"
    return User(sub=claims["sub"], role=role, email=claims.get("email"), phone=claims.get("phone"))


def current_user(authorization: Optional[str] = Header(default=None)) -> Optional[User]:
    """Optional in dev, required in prod."""
    if authorization and authorization.lower().startswith("bearer "):
        return verify_token(authorization.split(" ", 1)[1].strip())
    if _env() == "prod":
        raise HTTPException(status_code=401, detail={"code": "unauthorized", "message": "Bearer token required"})
    return None


def check_home_access(user: Optional[User], home_id: str, repo) -> None:
    """Customers may only act on their own homes; analysts on any; anonymous only in dev."""
    if user is None:
        if _env() == "prod":
            raise HTTPException(status_code=401, detail={"code": "unauthorized", "message": "Bearer token required"})
        return
    if user.role == "analyst":
        return
    owner = repo.owner_of(home_id)
    if owner is not None and owner != user.sub:
        raise HTTPException(status_code=403, detail={"code": "forbidden", "message": "This home belongs to another customer"})
    if owner is None and _env() == "prod":
        raise HTTPException(status_code=403, detail={"code": "forbidden", "message": "This home is not linked to your account"})
