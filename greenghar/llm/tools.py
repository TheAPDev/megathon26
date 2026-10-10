"""Tools the LLM may call. Every tool returns typed JSON: {"facts": {...}, "data_quality": [...]}.
The LLM never computes; every number in a reply must come from a tool result."""
from __future__ import annotations

from typing import Any, Callable

from ..engine.finance import finance_plan, subsidy_navigator
from ..engine.heatwave import heatwave_report
from ..engine.plan import recommend, run_scenario
from ..engine.roadmap import roadmap
from ..engine.score import score_home
from ..engine.solar import recommend_kw, solar_quote
from ..reference import catalogue, emission_factors
from ..schemas import Home

TOOL_SPECS: list[dict] = [
    {"type": "function", "function": {"name": "get_score", "description": "Green Ghar Score, band, sub-scores with reasons, confidence and warnings for the home.",
                                      "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "get_recommendations", "description": "Feasible retrofits in interaction order with suitability, reason, cost, savings, CO2 and payback; infeasible ones with the reason.",
                                      "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "run_scenario", "description": "Re-run the engine for a what-if: apply retrofits (ids from the catalogue) and parameters; returns per-fuel before/after, rupees, CO2 and new score. Infeasible items are refused with a reason.",
                                      "parameters": {"type": "object", "properties": {
                                          "retrofits": {"type": "array", "items": {"type": "string", "enum": sorted(catalogue())}},
                                          "pv_kw": {"type": "number", "minimum": 0.5, "maximum": 10},
                                          "ac_setpoint_c": {"type": "number", "minimum": 18, "maximum": 30}},
                                          "required": ["retrofits"]}}},
    {"type": "function", "function": {"name": "get_finance_plan", "description": "Subsidy, loan EMI vs monthly bill saving, payback and 25-year savings for a set of retrofits.",
                                      "parameters": {"type": "object", "properties": {"retrofits": {"type": "array", "items": {"type": "string", "enum": sorted(catalogue())}}},
                                                     "required": ["retrofits"]}}},
    {"type": "function", "function": {"name": "get_solar_quote", "description": "Recommended rooftop solar size, generation, cost, PM Surya Ghar and state subsidy, and steps to apply.",
                                      "parameters": {"type": "object", "properties": {"kw": {"type": "number"}}, "required": []}}},
    {"type": "function", "function": {"name": "get_roadmap", "description": "Year-by-year plan within a yearly budget in rupees.",
                                      "parameters": {"type": "object", "properties": {"budget_inr": {"type": "number", "minimum": 1000}}, "required": ["budget_inr"]}}},
    {"type": "function", "function": {"name": "get_heatwave", "description": "Indoor temperature drop and AC hours avoided from cool roof, insulation and shading before summer.",
                                      "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "get_factors", "description": "Emission factors with units, versions and sources.",
                                      "parameters": {"type": "object", "properties": {}, "required": []}}},
]


def _quality(home: Home, score=None) -> list[str]:
    q = []
    s = score or score_home(home)
    q += s.confidence_reasons + s.warnings
    return q


def execute(name: str, args: dict, home: Home, value_fn: Callable | None = None) -> dict[str, Any]:
    if name == "get_score":
        s = score_home(home)
        return {"facts": s.model_dump(), "data_quality": _quality(home, s)}
    if name == "get_recommendations":
        recs = recommend(home)
        return {"facts": {"recommendations": [r.model_dump() for r in recs]}, "data_quality": _quality(home)}
    if name == "run_scenario":
        params = {k: v for k, v in args.items() if k in ("pv_kw", "ac_setpoint_c") and v is not None}
        sc = run_scenario(home, list(args.get("retrofits", [])), params)
        if value_fn is not None:
            sc["value"] = value_fn(home, sc["score_before"], sc["score_after"])
        return {"facts": sc, "data_quality": _quality(home)}
    if name == "get_finance_plan":
        return {"facts": finance_plan(home, list(args.get("retrofits", []))), "data_quality": _quality(home)}
    if name == "get_solar_quote":
        kw = args.get("kw") or recommend_kw(home)
        return {"facts": {"quote": solar_quote(home, kw), "subsidy": subsidy_navigator(home, kw)}, "data_quality": _quality(home)}
    if name == "get_roadmap":
        return {"facts": roadmap(home, float(args["budget_inr"])), "data_quality": _quality(home)}
    if name == "get_heatwave":
        return {"facts": heatwave_report(home), "data_quality": _quality(home)}
    if name == "get_factors":
        return {"facts": {"factors": list(emission_factors().values())}, "data_quality": []}
    raise ValueError(f"Unknown tool {name}")
