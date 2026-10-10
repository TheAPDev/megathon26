"""Homeowner screens 1-4 and 6: score, plan, what-if, value & finance, memory & journey, heatwave."""
from __future__ import annotations

import uuid
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from ...engine.finance import finance_plan, subsidy_navigator
from ...engine.heatwave import heatwave_report
from ...engine.plan import run_scenario
from ...engine.roadmap import roadmap
from ...engine.score import score_home
from ...engine.solar import recommend_kw, solar_quote
from ...memory.store import memory_item, personalised_plan, what_changed
from ...ml import predict
from ...reference import catalogue, cities
from ...schemas import Home, ScenarioRequest, ScoreResult
from ..auth import User, current_user
from ..deps import APIError, get_repo, home_or_404

router = APIRouter(prefix="/homes", tags=["homes"])


def _ranker():
    return predict.rank_score if predict._load("ranker")[0] is not None else None


class HomeCreate(Home):
    home_id: Optional[str] = None  # type: ignore[assignment]


@router.get("", summary="Homes linked to the signed-in customer (empty when anonymous)")
def list_my_homes(repo=Depends(get_repo), user: Optional[User] = Depends(current_user)) -> list[dict]:
    return repo.homes_of(user.sub) if user else []


@router.post("", status_code=201, summary="Create a home from a survey or parsed bill")
def create_home(body: HomeCreate, repo=Depends(get_repo), user: Optional[User] = Depends(current_user)) -> dict:
    if body.city not in cities():
        raise APIError(422, "unknown_city", f"No climate/tariff data for '{body.city}'", {"known_cities": sorted(cities())})
    home = Home(**{**body.model_dump(), "home_id": body.home_id or f"U-{uuid.uuid4().hex[:10]}"})
    if body.home_id:
        try:
            repo.get_home(body.home_id)
            existing = True
        except KeyError:
            existing = False
        if existing:
            from ..auth import check_home_access
            check_home_access(user, body.home_id, repo)  # overwriting someone else's home is not allowed
    repo.put_home(home, owner=user.sub if user else None)
    return {"home": home.model_dump(), "score": score_home(home).model_dump()}


@router.get("/{home_id}", summary="Home attributes as the engine sees them")
def get_home(home: Home = Depends(home_or_404)) -> dict:
    return home.model_dump()


@router.get("/{home_id}/score", response_model=ScoreResult, summary="Screen 1: Green Ghar Score with waterfall and confidence")
def get_score(home: Home = Depends(home_or_404)) -> ScoreResult:
    return score_home(home)


@router.get("/{home_id}/plan", summary="Screen 2: retrofit plan in interaction order (memory-aware)")
def get_plan(home: Home = Depends(home_or_404), repo=Depends(get_repo)) -> dict:
    cust = repo.customer_for_home(home.home_id)
    items = repo.memory_for(cust["customer_id"]) if cust else []
    return personalised_plan(home, items, ranker=_ranker()) | {"estimated": True}


@router.post("/{home_id}/scenario", summary="Screen 3: what-if; reruns the engine (target < 300 ms)")
def post_scenario(req: ScenarioRequest, home: Home = Depends(home_or_404)) -> dict:
    unknown = [r for r in req.retrofits if r not in catalogue()]
    if unknown:
        raise APIError(422, "unknown_retrofit", f"Unknown retrofit ids: {unknown}", {"valid": sorted(catalogue())})
    sc = run_scenario(home, req.retrofits, req.params)
    sc["value"] = predict.value_range(home, sc["score_before"], sc["score_after"])
    return sc


@router.get("/{home_id}/value", summary="Screen 4: current value and post-retrofit uplift range (indicative)")
def get_value(retrofits: list[str] = Query(default=[]), home: Home = Depends(home_or_404)) -> dict:
    before = score_home(home).raw_score
    after = run_scenario(home, retrofits)["score_after"] if retrofits else None
    return predict.value_range(home, before, after)


class FinanceRequest(BaseModel):
    retrofits: list[str]
    params: dict[str, float] = Field(default_factory=dict)
    down_payment_inr: float = Field(0, ge=0)


@router.post("/{home_id}/finance", summary="Screen 4: subsidy, EMI vs bill saving, payback, 25-year savings")
def post_finance(req: FinanceRequest, home: Home = Depends(home_or_404)) -> dict:
    return finance_plan(home, req.retrofits, req.params, req.down_payment_inr)


@router.get("/{home_id}/solar", summary="Rooftop solar size, quote and PM Surya Ghar navigator")
def get_solar(kw: Optional[float] = Query(default=None, gt=0, le=10), home: Home = Depends(home_or_404)) -> dict:
    kw = kw or recommend_kw(home)
    return {"quote": solar_quote(home, kw), "subsidy": subsidy_navigator(home, kw)}


@router.get("/{home_id}/subsidy-application", summary="Pre-filled PM Surya Ghar application draft")
def subsidy_application(home: Home = Depends(home_or_404), repo=Depends(get_repo)) -> dict:
    kw = recommend_kw(home)
    nav = subsidy_navigator(home, kw)
    if not nav["eligible"]:
        raise APIError(409, "not_eligible", nav["why_not"])
    c = cities()[home.city]
    return {"portal": "https://pmsuryaghar.gov.in", "prefilled": {"state": c.state, "district_city": home.city,
            "sanctioned_load_kw": home.sanctioned_load_kw, "proposed_capacity_kw": kw, "roof_area_m2": home.roof_area_m2,
            "net_metering": True}, "to_complete_by_user": ["Consumer number", "Mobile number (OTP)", "Aadhaar", "Bank details"],
            "steps": nav["steps"], "status_tracker": [{"step": s, "done": False} for s in nav["steps"]]}


@router.get("/{home_id}/roadmap", summary="Budget-constrained year-by-year plan")
def get_roadmap(budget_inr: float = Query(..., ge=1000), years: int = Query(3, ge=1, le=5),
                objective: Literal["inr", "co2", "kwh"] = "inr", home: Home = Depends(home_or_404)) -> dict:
    return roadmap(home, budget_inr, years, objective)


@router.get("/{home_id}/weather-signature", summary="Real-weather check: kWh per real cooling degree-day and weather-normalised use")
def get_weather_signature(home: Home = Depends(home_or_404), repo=Depends(get_repo)) -> dict:
    out = repo.real("home_weather", home_id=home.home_id)
    if not out:
        raise APIError(404, "no_weather_signature", "Needs 6+ metered months and the real-weather layer (GG_REPO=supabase)")
    return out


@router.get("/{home_id}/heatwave", summary="Heatwave mode: indoor temperature drop and AC hours avoided")
def get_heatwave(home: Home = Depends(home_or_404)) -> dict:
    return heatwave_report(home)


@router.post("/{home_id}/telegram-link", summary="Signed 15-minute deep link that connects a Telegram chat to this home")
def telegram_link(home: Home = Depends(home_or_404)) -> dict:

    from ..linking import make_token
    t = make_token(home.home_id)
    if t is None:
        raise APIError(503, "linking_unavailable", "Set GG_LINK_SECRET to enable Telegram linking")
    from ...bot.telegram import bot_username
    bot = bot_username() or ""
    return {**t, "bot_username": bot or None, "deep_link": f"https://t.me/{bot}?start={t['token']}" if bot else None}


# ---- Screen 6: memory & journey --------------------------------------------------------------

class MemoryIn(BaseModel):
    kind: Literal["constraint", "preference", "feedback"]
    key: str = Field(..., examples=["budget_inr", "exclude", "tenure", "language", "rejected", "accepted"])
    value: str | int | float | bool


@router.get("/{home_id}/journey", summary="Screen 6: completed retrofits, memory and current advice")
def get_journey(home: Home = Depends(home_or_404), repo=Depends(get_repo)) -> dict:
    cust = repo.customer_for_home(home.home_id)
    items = repo.memory_for(cust["customer_id"]) if cust else []
    events = []
    try:
        import pandas as pd

        from ...data_access import DATA_DIR
        ev = pd.read_parquet(DATA_DIR / "retrofit_events.parquet")
        events = ev[ev["home_id"] == home.home_id].sort_values("month_index").to_dict("records")
    except Exception:  # no local events table (e.g. Supabase-only deployment)
        pass
    return {"home_id": home.home_id, "customer_id": cust["customer_id"] if cust else None, "completed_retrofits": events,
            "memory": items, "plan": personalised_plan(home, items, ranker=_ranker())}


@router.post("/{home_id}/memory", status_code=201, summary="Add a memory item and see what changed")
def post_memory(item: MemoryIn, home: Home = Depends(home_or_404), repo=Depends(get_repo)) -> dict:
    cust = repo.customer_for_home(home.home_id)
    cid = cust["customer_id"] if cust else f"ANON-{home.home_id}"
    before_items = repo.memory_for(cid)
    before = personalised_plan(home, before_items)
    new = memory_item(item.kind, item.key, item.value, home.home_id, cid)
    repo.add_memory(cid, new)
    after = personalised_plan(home, before_items + [new])
    return {"memory_item": new, "what_changed": what_changed(before, after)}
