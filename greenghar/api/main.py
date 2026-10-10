"""Green Ghar Score API.

    uvicorn greenghar.api.main:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

import json
import logging
import os
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from ..ml import predict
from .deps import APIError, api_error_handler, error_body, settings
from .routers.accounts import router as accounts
from ..bot.telegram import bot_username
from .routers.accounts import username_domain
from .routers.homes import router as homes_router
from .routers.other import advisor_router, channels, lab, portfolio, reference

log = logging.getLogger("greenghar")
logging.basicConfig(level=logging.INFO, format="%(message)s")
VERSION = "1.0.0"

app = FastAPI(title="Green Ghar Score API", version=VERSION,
              description="India home-energy score, retrofit plan, what-if, finance, grounded advisor, lender portfolio and model lab.")
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"], allow_headers=["*"],
                   expose_headers=["X-Request-ID", "Server-Timing", "X-TTS-Provider"])
MODEL_VERSIONS: dict = {}


@app.on_event("startup")
def _startup() -> None:
    MODEL_VERSIONS.update(predict.install())
    from .deps import get_repo
    get_repo()  # pick the data source at startup (falls back loudly if Supabase credentials are missing)
    log.info(json.dumps({"event": "startup", "models": MODEL_VERSIONS, "repo": settings.repo, "env": settings.env}))


@app.middleware("http")
async def _request_context(request: Request, call_next):
    rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:16]
    request.state.request_id = rid
    t = time.perf_counter()
    response = await call_next(request)
    ms = round((time.perf_counter() - t) * 1000, 1)
    response.headers["X-Request-ID"] = rid
    response.headers["Server-Timing"] = f"app;dur={ms}"
    log.info(json.dumps({"event": "request", "request_id": rid, "method": request.method, "path": request.url.path,
                         "status": response.status_code, "duration_ms": ms}))
    return response


app.add_exception_handler(APIError, api_error_handler)


@app.exception_handler(RequestValidationError)
async def _validation(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content=error_body("validation_error", "Request body or parameters are invalid",
                                                            {"errors": json.loads(json.dumps(exc.errors(), default=str))},
                                                            getattr(request.state, "request_id", None)))


@app.exception_handler(StarletteHTTPException)
async def _http(request: Request, exc: StarletteHTTPException):
    detail = exc.detail if isinstance(exc.detail, dict) else {"code": "http_error", "message": str(exc.detail)}
    return JSONResponse(status_code=exc.status_code, content=error_body(detail.get("code", "http_error"), detail.get("message", ""),
                                                                        None, getattr(request.state, "request_id", None)))


@app.exception_handler(Exception)
async def _unhandled(request: Request, exc: Exception):
    log.exception("unhandled error")
    return JSONResponse(status_code=500, content=error_body("internal_error", "Something went wrong; the request ID helps us trace it.",
                                                            None, getattr(request.state, "request_id", None)))


@app.get("/health", tags=["ops"])
def health() -> dict:
    from ..reference import cities
    return {"status": "ok", "version": VERSION, "repo": settings.repo, "cities": len(cities()), "models": MODEL_VERSIONS}


for r in (homes_router, advisor_router, channels, portfolio, lab, reference, accounts):
    app.include_router(r)


def _login_on() -> bool:
    """Web sign-in (username + password via Supabase Auth) is published to the app only when GG_LOGIN=on (or in prod)."""
    return os.environ.get("GG_LOGIN", "off").lower() in ("on", "1", "true") or settings.env == "prod"


@app.get("/config", tags=["ops"], summary="Public client configuration (no secrets)")
def public_config() -> dict:
    return {"env": settings.env, "repo": settings.repo, "version": VERSION,
            "auth": {"supabase_url": (os.environ.get("SUPABASE_URL") or None) if _login_on() else None,
                     "supabase_anon_key": (os.environ.get("SUPABASE_ANON_KEY") or None) if _login_on() else None,
                     "username_domain": username_domain() if _login_on() else None,
                     "required": settings.env == "prod"},
            "telegram_bot_username": bot_username(),
            "demo_home_id": os.environ.get("GG_DEMO_HOME", "H000011") if settings.env == "dev" else None}


# ---- web app (frontend/dist, built with `npm run build`) served at /app -------------------------
WEB_DIST = Path(os.environ.get("GG_WEB_DIST", Path(__file__).resolve().parents[2] / "frontend" / "dist"))


@app.get("/", include_in_schema=False)
def _root():
    return RedirectResponse("/app/" if (WEB_DIST / "index.html").exists() else "/docs")


@app.get("/app", include_in_schema=False)
@app.get("/app/{path:path}", include_in_schema=False)
def _web(path: str = ""):
    index = WEB_DIST / "index.html"
    if not index.exists():
        raise APIError(404, "web_not_built", "Frontend not built: run `npm ci && npm run build` in frontend/")
    f = (WEB_DIST / path).resolve()
    if path and f.is_file() and WEB_DIST.resolve() in f.parents:
        cache = "public, max-age=31536000, immutable" if path.startswith("assets/") else "no-cache"
        return FileResponse(f, headers={"Cache-Control": cache})
    return FileResponse(index, headers={"Cache-Control": "no-cache"})  # client-side routes
