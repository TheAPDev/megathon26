"""Shared state, settings, auth and error format."""
from __future__ import annotations

import os
import secrets
import time
from collections import defaultdict, deque
from functools import lru_cache
from typing import Optional

from fastapi import Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from ..data_access import LocalRepo
from ..llm.orchestrator import Advisor
from .auth import User, check_home_access, current_user, verify_token


class Settings:
    repo = os.environ.get("GG_REPO", "local")             # local | supabase
    env = os.environ.get("GG_ENV", "dev")                  # dev | prod
    analyst_keys = {k for k in os.environ.get("GG_ANALYST_KEYS", "").split(",") if k}
    admin_keys = {k for k in os.environ.get("GG_ADMIN_KEYS", "").split(",") if k}
    telegram_secret = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "")
    cors_origins = [o for o in os.environ.get("GG_CORS_ORIGINS", "*").split(",") if o]
    rate_limit_per_min = int(os.environ.get("GG_RATE_LIMIT_PER_MIN", "30"))


settings = Settings()


@lru_cache
def get_repo():
    if settings.repo == "supabase":
        if not (os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_SERVICE_ROLE_KEY")):
            import logging
            logging.getLogger("greenghar").error(
                "GG_REPO=supabase but SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY is missing; serving the local dataset. "
                "Run `python scripts/connect_supabase.py` to connect.")
            settings.repo = "local"
            return LocalRepo()
        from ..db.supabase_repo import SupabaseRepo
        return SupabaseRepo()
    return LocalRepo()


@lru_cache
def get_advisor() -> Advisor:
    from ..ml.predict import value_range
    return Advisor(value_fn=value_range)


def _check(key: str | None, allowed: set[str]) -> None:
    if settings.env == "dev" and not allowed:
        return  # dev mode with no keys configured: open
    if not key or not any(secrets.compare_digest(key, k) for k in allowed):
        raise HTTPException(status_code=401, detail={"code": "unauthorized", "message": "Valid X-API-Key required"})


def analyst(x_api_key: str | None = Header(default=None), authorization: str | None = Header(default=None)) -> None:
    """Analysts authenticate with an X-API-Key or a Supabase JWT whose app_metadata.app_role is 'analyst'."""
    if authorization and authorization.lower().startswith("bearer ") and not x_api_key:
        user = verify_token(authorization.split(" ", 1)[1].strip())
        if user.role != "analyst":
            raise HTTPException(status_code=403, detail={"code": "forbidden", "message": "Analyst role required"})
        return
    _check(x_api_key, settings.analyst_keys | settings.admin_keys)


def admin(x_api_key: str | None = Header(default=None)) -> None:
    _check(x_api_key, settings.admin_keys)


class APIError(Exception):
    def __init__(self, status: int, code: str, message: str, details: dict | None = None):
        self.status, self.code, self.message, self.details = status, code, message, details or {}


def error_body(code: str, message: str, details=None, request_id: str | None = None) -> dict:
    return {"error": {"code": code, "message": message, "details": details or {}, "request_id": request_id}}


async def api_error_handler(request: Request, exc: APIError):
    return JSONResponse(status_code=exc.status, content=error_body(exc.code, exc.message, exc.details, getattr(request.state, "request_id", None)))


def load_home(home_id: str, repo, user: Optional[User]):
    try:
        home = repo.get_home(home_id)
    except KeyError:
        raise APIError(404, "home_not_found", f"Home {home_id} not found")
    check_home_access(user, home_id, repo)
    return home


def home_or_404(home_id: str, repo=Depends(get_repo), user: Optional[User] = Depends(current_user)):
    """Path dependency: the home exists and the caller may act on it (own home, or analyst)."""
    return load_home(home_id, repo, user)


_hits: dict[str, deque] = defaultdict(deque)


def rate_limit(request: Request, authorization: str | None = Header(default=None)) -> None:
    """Sliding one-minute window per caller (token, else client IP) for the costly LLM/OCR/speech routes.
    In-process: fine for one instance; put the API gateway's limiter in front when scaling out."""
    limit = settings.rate_limit_per_min
    if limit <= 0:
        return
    key = (authorization or "")[-24:] or (request.client.host if request.client else "anon")
    now, q = time.monotonic(), _hits[f"{request.url.path}|{key}"]
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= limit:
        raise APIError(429, "rate_limited", f"Too many requests: limit is {limit} per minute", {"retry_after_s": int(60 - (now - q[0])) + 1})
    q.append(now)
