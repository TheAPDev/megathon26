"""Advisor (screen 5), channels (bill OCR, speech, Telegram), portfolio (screen 7), model lab (screen 8), reference."""
from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Depends, File, Header, Query, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field


from ...engine import portfolio as P
from ...lab import run_all
from ...llm.audit import log_answer
from ...ml import predict
from ...reference import catalogue, cities, emission_factors, tariff_slabs, tariff_states
from ..auth import User, current_user
from ..deps import APIError, admin, analyst, get_advisor, get_repo, load_home, rate_limit, settings

advisor_router = APIRouter(prefix="/advisor", tags=["advisor"])
channels = APIRouter(tags=["channels"])
portfolio = APIRouter(prefix="/portfolio", tags=["portfolio"], dependencies=[Depends(analyst)])
lab = APIRouter(prefix="/lab", tags=["model lab"])
reference = APIRouter(prefix="/reference", tags=["reference"])


class ChatIn(BaseModel):
    home_id: str
    message: str = Field(..., min_length=1, max_length=2000)
    language: Optional[str] = Field(None, examples=["hi", "en", "ta"])
    use_llm: bool = True


@advisor_router.post("/chat", summary="Screen 5: grounded AI advisor (every figure verified)", dependencies=[Depends(rate_limit)])
def chat(body: ChatIn, repo=Depends(get_repo), advisor=Depends(get_advisor), user: Optional[User] = Depends(current_user)) -> dict:
    home = load_home(body.home_id, repo, user)
    out = advisor.answer(home, body.message, body.language, body.use_llm)
    log_answer(repo, home.home_id, body.message, out, "api")
    return out


# ---- channels ------------------------------------------------------------------------------------

BILL_MIME = {"image/jpeg", "image/png", "image/webp", "application/pdf"}


@channels.post("/bills/parse", summary="Bill photo -> monthly units (Gemini Flash, Tesseract fallback)", dependencies=[Depends(rate_limit)])
async def parse_bill_ep(file: UploadFile = File(...), home_id: Optional[str] = Query(None, description="Link and store the bill against this home"),
                        repo=Depends(get_repo), user: Optional[User] = Depends(current_user)) -> dict:
    from ...ocr.bill import OCRError, parse_bill
    data = await file.read()
    mime = file.content_type or "image/jpeg"
    if len(data) > 8 * 1024 * 1024:
        raise APIError(413, "file_too_large", "Bill image must be under 8 MB")
    if mime not in BILL_MIME:
        raise APIError(415, "unsupported_media_type", f"Use one of {sorted(BILL_MIME)}")
    if home_id:
        load_home(home_id, repo, user)  # exists and caller may attach bills to it
    try:
        parsed = parse_bill(data, mime)
    except OCRError as e:
        raise APIError(503, "ocr_unavailable", str(e))
    if home_id:  # the image is kept only when the customer links it to a home (DPDP: purpose-bound storage)
        parsed["stored"] = repo.save_bill_upload(home_id, data, mime, parsed)
    return parsed


@channels.post("/speech/transcribe", summary="Voice note -> text (Whisper on Groq, NVIDIA fallback)", dependencies=[Depends(rate_limit)])
async def transcribe_ep(file: UploadFile = File(...), language: Optional[str] = Query(None)) -> dict:
    from ...speech.stt import STTError, transcribe
    try:
        return transcribe(await file.read(), file.filename or "voice.ogg", language)
    except STTError as e:
        raise APIError(503, "stt_unavailable", str(e))


class TTSIn(BaseModel):
    text: str = Field(..., max_length=1500)
    language: str = "en"


@channels.post("/speech/tts", summary="Text -> speech (NVIDIA Magpie TTS, edge-tts fallback)", dependencies=[Depends(rate_limit)])
def tts_ep(body: TTSIn) -> Response:
    from ...speech.tts import TTSError, synthesize
    try:
        out = synthesize(body.text, body.language)
    except TTSError as e:
        raise APIError(503, "tts_unavailable", str(e))
    return Response(content=out["audio"], media_type=out["mime"], headers={"X-TTS-Provider": out["provider"]})


_bot = None


def get_bot(repo=Depends(get_repo), advisor=Depends(get_advisor)):
    global _bot
    if _bot is None:
        from ...bot.telegram import TelegramBot
        _bot = TelegramBot(repo, advisor)
    return _bot


@channels.post("/telegram/webhook", summary="Telegram Bot API webhook")
async def telegram_webhook(request: Request, bot=Depends(get_bot),
                           x_telegram_bot_api_secret_token: Optional[str] = Header(default=None)) -> dict:
    if settings.telegram_secret and x_telegram_bot_api_secret_token != settings.telegram_secret:
        raise APIError(401, "bad_secret", "Invalid Telegram webhook secret")
    update = await request.json()
    return bot.handle(update)


# ---- portfolio (screen 7) ------------------------------------------------------------------------

@portfolio.get("/summary")
def p_summary(city: Optional[str] = None, state: Optional[str] = None, repo=Depends(get_repo)) -> dict:
    return repo.portfolio("summary", city=city, state=state)


@portfolio.get("/poor-homes")
def p_poor(limit: int = Query(50, le=500), city: Optional[str] = None, state: Optional[str] = None, repo=Depends(get_repo)) -> list[dict]:
    return repo.portfolio("poor_homes", limit=limit, city=city, state=state)


@portfolio.get("/ranking", summary="Homes ranked by improvement potential")
def p_rank(limit: int = Query(50, le=500), city: Optional[str] = None, state: Optional[str] = None, repo=Depends(get_repo)) -> list[dict]:
    return repo.portfolio("ranking", limit=limit, city=city, state=state)


@portfolio.get("/map")
def p_map(repo=Depends(get_repo)) -> list[dict]:
    return repo.portfolio("map")


@portfolio.get("/targets", summary="Green-finance targeting list (consented customers only)")
def p_targets(limit: int = Query(100, le=1000), city: Optional[str] = None, repo=Depends(get_repo)) -> list[dict]:
    return repo.portfolio("targets", limit=limit, city=city)


@portfolio.get("/rwa-leads", summary="Housing societies for pooled common-area solar")
def p_rwa(min_homes: int = Query(4, ge=2), limit: int = Query(50, le=500), repo=Depends(get_repo)) -> list[dict]:
    return repo.portfolio("rwa_leads", min_homes=min_homes, limit=limit)


@portfolio.post("/rescore", dependencies=[Depends(admin)], summary="Recompute cached scores (batch job trigger)")
def p_rescore() -> dict:
    P.frame.cache_clear()
    return {"status": "cache cleared; run scripts/generate_data.py or the rescore worker to rebuild home_scores"}


# ---- model lab (screen 8) ------------------------------------------------------------------------

@lab.get("/metrics", summary="Held-out metrics vs baselines")
def lab_metrics() -> dict:
    from ...data_access import DATA_DIR
    root = DATA_DIR.parent.parent
    out = {"models": predict.model_versions()}
    for name in ("eval_report", "llm_eval"):
        p = root / "reports" / f"{name}.json"
        out[name] = json.loads(p.read_text()) if p.exists() else None
    return out


@lab.get("/scenarios", summary="Run the hidden-scenario suite, monotonicity and worked-example checks live")
def lab_scenarios(monotonicity_homes: int = Query(60, ge=10, le=1000)) -> dict:
    return run_all(predict.value_range, monotonicity_homes)


@lab.get("/factors")
def lab_factors() -> list[dict]:
    return list(emission_factors().values())


@lab.get("/data-card")
def lab_data_card() -> dict:
    from ...data_access import DATA_DIR
    root = DATA_DIR.parent.parent
    manifest = DATA_DIR / "manifest.json"
    card = root / "docs" / "data_card.md"
    return {"manifest": json.loads(manifest.read_text()) if manifest.exists() else None,
            "data_card_markdown": card.read_text() if card.exists() else None}


# ---- reference -----------------------------------------------------------------------------------

@reference.get("/cities")
def ref_cities() -> list[dict]:
    return [{"city": c.city, "state": c.state, "zone": c.zone, "lat": c.lat, "lon": c.lon, "tier": c.tier} for c in cities().values()]


@reference.get("/retrofits")
def ref_retrofits() -> list[dict]:
    return list(catalogue().values())


@reference.get("/tariffs/{state}")
def ref_tariff(state: str) -> dict:
    if state not in tariff_states():
        raise APIError(404, "unknown_state", f"No tariff for {state}", {"known": sorted(tariff_states())})
    return {"state": tariff_states()[state], "slabs": tariff_slabs()[state]}


# ---- real public data layer -----------------------------------------------------------------------

@reference.get("/real/sources", summary="Real public datasets loaded (Census 2011, NFHS-5, OWID, WRI, Open-Meteo, NASA POWER, World Bank)")
def real_sources(repo=Depends(get_repo)) -> list[dict]:
    return repo.real("sources")


@reference.get("/real/state/{state}", summary="Real state profile: Census 2011 housing and assets, NFHS-5 energy access, power fleet")
def real_state(state: str, repo=Depends(get_repo)) -> dict:
    out = repo.real("state_profile", state=state)
    if not out:
        raise APIError(404, "unknown_state", f"No real-data profile for {state}")
    return out


@reference.get("/real/city/{city}", summary="Real weather 2024-26 (Open-Meteo/ERA5) and NASA POWER climatology for a city")
def real_city(city: str, repo=Depends(get_repo)) -> dict:
    out = repo.real("city_climate", city=city)
    if not out or not (out.get("check") or out.get("monthly")):
        raise APIError(404, "no_real_weather", f"No real weather for {city} (available with GG_REPO=supabase)")
    return out


@reference.get("/real/calibration", summary="Synthetic population vs real statistics, per state", dependencies=[Depends(analyst)])
def real_calibration(repo=Depends(get_repo)) -> list[dict]:
    return repo.real("synth_vs_real")
