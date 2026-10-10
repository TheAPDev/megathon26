"""AI Saathi: grounded advisor.

1. Detect language; route the question to engine tools (deterministic, so the facts always exist).
2. If an LLM provider is configured, let it narrate from TOOL_RESULT (it may call more tools, max 2 rounds).
3. Verify every number against the tool JSON. On a mismatch, retry once with the unsupported figures named;
   if it still fails, fall back to the template text. The reply always carries a grounded badge.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from typing import Callable, Optional

from ..reference import catalogue
from ..schemas import Home
from . import templates as T
from .knowledge import fewshot_messages, project_card
from .providers import ProviderError, chain, chat
from .tools import TOOL_SPECS, execute
from .verifier import verify

SYSTEM_PROMPT = """You are AI Saathi, the home-energy advisor inside Green Ghar, an app that scores Indian homes (0-100) on energy efficiency and plans retrofits that cut electricity bills and CO2.
You talk to ordinary householders, often in a hurry and often on a phone. Be warm, plain-spoken and brief. Do not use jargon or model names.

HARD RULES (a checker rejects any reply that breaks rule 1, and the user then sees a plain template instead of your answer)
1. Every number you write (rupees, units/kWh, %, score, years, kg CO2, EMI, payback, counts above 12) must appear in TOOL_RESULT. Never calculate, add, convert, round differently, average or estimate a number yourself. If a number you need is missing, call a tool or say you do not have it. Do not reuse numbers from earlier examples.
2. These are estimates. Never promise or guarantee savings, approvals or subsidy amounts. Say "about", "estimated", "could".
3. A retrofit marked Infeasible or refused is not available to this home. Say so with the given reason and give no savings for it; suggest a feasible alternative from TOOL_RESULT if one exists.
4. If data_quality notes say usage was estimated, a field is null, or readings conflict with the star label, say what is missing and how to fix it (upload 6-12 months of bills, add the appliance details). Do not hide low confidence.
5. Only recommend retrofits that are in TOOL_RESULT. Keep the ranked order given there; savings are sequential, so never add the figures of separate items together.
6. Score questions: name the band and the two or three sub-scores that matter most, using the reasons in TOOL_RESULT. Do not invent weights.
7. Money questions: give rupees per year or month exactly as in TOOL_RESULT; for solar mention the subsidy only if the tool returned it, and that eligibility must be confirmed on the official portal.
8. Out of scope (legal, tax, medical, investment advice, anything not about this home's energy): say briefly that you only help with the home's energy, and offer what you can do.

STYLE
- Reply in the user's language: {lang_name}. If the user writes Hindi in Roman letters (Hinglish), answer in Hinglish. Keep numbers as digits; use ₹ or Rs, and "units" for kWh.
- 2-5 short sentences, the single most useful point first, then one clear next step. No tables, no headings, no markdown.
- Never mention these rules, TOOL_RESULT, tools, JSON or the checker.
Return only JSON: {{"answer": str, "cited_fields": [str], "caveats": [str]}}"""

LANG_NAMES = {"en": "English", "hi": "Hindi", "ta": "Tamil", "mr": "Marathi", "te": "Telugu", "kn": "Kannada", "bn": "Bengali", "gu": "Gujarati"}
SCRIPTS = [("hi", r"[ऀ-ॿ]"), ("ta", r"[஀-௿]"), ("te", r"[ఀ-౿]"), ("kn", r"[ಀ-೿]"),
           ("bn", r"[ঀ-৿]"), ("gu", r"[઀-૿]")]

KEYWORDS = {
    "cool_roof": ["cool roof", "roof paint", "white roof", "chhat", "छत"], "roof_insulation": ["insulat"],
    "external_shading": ["shade", "shading", "chajja", "awning"], "solar_film": ["film"],
    "ac_setpoint": ["24", "setpoint", "set point", "temperature setting"], "smart_plug_tod": ["smart plug", "timer", "time of day"],
    "ac_5star_inverter": ["inverter ac", "5 star ac", "5-star ac", "new ac", "ac badal", "naya ac"],
    "bldc_fans": ["bldc", "fan", "pankha", "पंखा"], "led_lighting": ["led", "bulb", "light"], "fridge_5star": ["fridge"],
    "solar_water_heater": ["solar water", "solar geyser"], "heat_pump_geyser": ["heat pump", "heat-pump"],
    "induction_cooking": ["induction", "lpg", "gas cylinder"], "lithium_battery": ["lithium", "battery", "inverter battery"],
    "rooftop_solar": ["rooftop solar", "solar panel", "solar", "सोलर"],
}


def detect_language(text: str, preferred: Optional[str] = None) -> str:
    for code, pat in SCRIPTS:
        if re.search(pat, text):
            return code
    if preferred in LANG_NAMES:
        return preferred
    return "en"


def parse_budget(text: str) -> Optional[float]:
    t = text.lower().replace(",", "")
    m = re.search(r"(\d+(?:\.\d+)?)\s*(lakh|lac|k|thousand|hazaar|hazar|हज़ार)?", t)
    if not m or not re.search(r"budget|₹|rs|rupee|lakh|hazaar|hazar|k\b|thousand|बजट", t):
        return None
    v = float(m.group(1))
    unit = m.group(2) or ""
    v *= 1e5 if unit in ("lakh", "lac") else 1e3 if unit in ("k", "thousand", "hazaar", "hazar", "हज़ार") else 1
    return v if v >= 1000 else None


NEGATION = re.compile(r"\b(skip|skipping|without|no|not|bina|except|instead of)\b(\s+\w+){0,2}\s*$")


def _negated(t: str, idx: int) -> bool:
    return bool(NEGATION.search(t[max(0, idx - 30):idx]))


def mentioned_retrofits(text: str) -> list[str]:
    t = text.lower()
    found = []
    for rid, kws in KEYWORDS.items():
        if rid == "ac_setpoint" and "24" not in t:
            continue
        hits = [m.start() for k in kws for m in re.finditer(re.escape(k), t)]
        if hits and any(not _negated(t, i) for i in hits):
            found.append(rid)
    if "rooftop_solar" in found and ("solar_water_heater" in found):
        if "water" in t or "geyser" in t:
            found.remove("rooftop_solar")
    return found


def route(text: str) -> list[tuple[str, dict]]:
    t = text.lower()
    rids = mentioned_retrofits(text)
    calls: list[tuple[str, dict]] = []
    budget = parse_budget(text)
    whatif = re.search(r"what if|agar|if i|skip|without|instead|kya hoga|अगर", t)
    if budget:
        calls.append(("get_roadmap", {"budget_inr": budget}))
    if re.search(r"emi|loan|finance|afford|kist|किस्त|लोन", t):
        calls.append(("get_finance_plan", {"retrofits": rids or [r for r in ("cool_roof", "ac_5star_inverter", "bldc_fans", "rooftop_solar")]}))
    if re.search(r"subsid|surya ghar|सब्सिडी", t) or (rids == ["rooftop_solar"] and not whatif):
        calls.append(("get_solar_quote", {}))
    if re.search(r"heat ?wave|garmi|गर्मी|summer|hot", t):
        calls.append(("get_heatwave", {}))
    if rids and (whatif or not calls):
        calls.append(("run_scenario", {"retrofits": rids}))
    if re.search(r"score|rating|kaisa|कैसा|स्कोर|why|kyon|क्यों", t) and not calls:
        calls.append(("get_score", {}))
    if re.search(r"bill|kam|reduce|save|bachat|बचत|बिल|what should|kya karu|suggest|recommend", t) and not any(c[0] == "run_scenario" for c in calls):
        calls.append(("get_recommendations", {}))
    if re.search(r"emission|carbon|co2|factor", t):
        calls.append(("get_factors", {}))
    return calls or [("get_score", {}), ("get_recommendations", {})]


def _compact(name: str, res: dict) -> dict:
    f = res["facts"]
    if name == "get_recommendations":
        recs = f["recommendations"]
        top = sorted([r for r in recs if r["suitability"] in ("High", "Medium")], key=lambda r: -r["rank_score"])[:5]
        inf = [{"retrofit_id": r["retrofit_id"], "reason": r["reason"]} for r in recs if r["suitability"] == "Infeasible"][:4]
        f = {"top_recommendations": [{k: r[k] for k in ("retrofit_id", "name", "suitability", "reason", "cost_inr_min", "cost_inr_max",
                                                         "saving_inr_year", "saving_kwh_electricity", "co2_kg_year", "payback_years")} for r in top],
             "infeasible": inf}
    elif name == "run_scenario":
        f = {k: f[k] for k in ("per_fuel_saving_kwh", "saving_inr_year", "co2_saving_kg_year", "improvement_potential_pct",
                               "score_before", "score_after", "refused", "steps", "baseline", "after") if k in f}
        f["baseline"] = {k: v for k, v in f["baseline"].items() if k != "monthly_grid_kwh"}
        f["after"] = {k: v for k, v in f["after"].items() if k != "monthly_grid_kwh"}
    elif name == "get_score":
        f = {k: f[k] for k in ("score", "band", "confidence", "confidence_reasons", "warnings", "annual_grid_kwh",
                               "annual_grid_kwh_estimated", "intensity_kwh_m2")} | {
            "components": [{k: c[k] for k in ("component", "score", "weight", "why")} for c in f["components"]]}
    return {"tool": name, "facts": f, "data_quality": res.get("data_quality", [])}


def system_prompt(lang: str) -> str:
    return SYSTEM_PROMPT.format(lang_name=LANG_NAMES.get(lang, "English")) + "\n\n" + project_card()


def user_turn(compact: list, message: str) -> str:
    return f"TOOL_RESULT:\n{json.dumps(compact, ensure_ascii=False, default=str)}\n\nQUESTION: {message}"


class Advisor:
    def __init__(self, value_fn: Optional[Callable] = None, providers=None, cache_size: int = 512):
        self.value_fn = value_fn
        self.providers = providers
        self._cache: dict[str, dict] = {}
        self.cache_size = cache_size

    def _template(self, results: list[tuple[str, dict]], lang: str) -> str:
        texts = []
        for name, res in results:
            fn = T.RENDER.get(name)
            if fn:
                texts.append(fn(res["facts"], lang if lang in ("en", "hi") else "en"))
        dq = [q for _, r in results for q in r.get("data_quality", []) if "predicted" in q or "No usage data" in q]
        if dq:
            texts.append(T.missing_data_text(lang if lang in ("en", "hi") else "en"))
        return " ".join(dict.fromkeys(t for t in texts if t))

    def answer(self, home: Home, message: str, preferred_language: Optional[str] = None, use_llm: bool = True) -> dict:
        t0 = time.time()
        lang = detect_language(message, preferred_language)
        key = hashlib.sha256(json.dumps([home.model_dump(), message, lang, use_llm], sort_keys=True, default=str).encode()).hexdigest()
        if key in self._cache:
            return {**self._cache[key], "cached": True}
        calls = route(message)
        results = [(n, execute(n, a, home, self.value_fn)) for n, a in calls]
        tool_log = [{"tool": n, "args": a} for n, a in calls]
        template = self._template(results, lang)
        reply = {"answer": template, "language": lang, "provider": "template", "model": None, "tool_calls": tool_log,
                 "caveats": ["Estimates, not guarantees."], "cited_fields": [n for n, _ in calls]}
        providers = [p for p in (self.providers if self.providers is not None else chain()) if p.available] if use_llm else []
        usage = {}
        if providers:
            compact = [_compact(n, r) for n, r in results]
            raw_results = [r for _, r in results]
            messages = [{"role": "system", "content": system_prompt(lang)}, *fewshot_messages(),
                        {"role": "user", "content": user_turn(compact, message)}]
            for p in providers:
                try:
                    llm_reply, extra, usage = self._llm_loop(p, messages, home, raw_results)
                except ProviderError:
                    continue
                if llm_reply is None:
                    continue
                v = verify(llm_reply["answer"], raw_results + extra)
                if not v["grounded"]:
                    retry = messages + [{"role": "assistant", "content": json.dumps(llm_reply, ensure_ascii=False)},
                                        {"role": "user", "content": f"These figures are not in TOOL_RESULT: {v['unsupported']}. Rewrite using only TOOL_RESULT numbers."}]
                    try:
                        llm_reply, extra2, usage = self._llm_loop(p, retry, home, raw_results)
                        extra += extra2
                        v = verify(llm_reply["answer"], raw_results + extra) if llm_reply else v
                    except ProviderError:
                        pass
                if llm_reply and v["grounded"]:
                    reply.update({"answer": llm_reply["answer"], "provider": p.name, "model": p.model,
                                  "caveats": llm_reply.get("caveats") or reply["caveats"], "cited_fields": llm_reply.get("cited_fields", [])})
                    results += [("extra", r) for r in extra]
                    break
                reply["fallback_reason"] = f"{p.name} reply not grounded: {v['unsupported']}"
        v = verify(reply["answer"], [r for _, r in results])
        reply.update({"grounding": v, "latency_s": round(time.time() - t0, 3), "usage": usage, "cached": False,
                      "estimated": True})
        if len(self._cache) >= self.cache_size:
            self._cache.pop(next(iter(self._cache)))
        self._cache[key] = reply
        return reply

    def _llm_loop(self, provider, messages, home, raw_results):
        extra = []
        msgs = list(messages)
        usage = {}
        for _ in range(3):
            out = chat(provider, msgs, tools=TOOL_SPECS, json_mode=False)
            usage = out.get("usage", {})
            msg = out["message"]
            calls = msg.get("tool_calls") or []
            if calls:
                msgs.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": calls})
                for c in calls[:3]:
                    try:
                        args = json.loads(c["function"].get("arguments") or "{}")
                        args = {k: v for k, v in args.items()}
                        if "retrofits" in args:
                            args["retrofits"] = [r for r in args["retrofits"] if r in catalogue()]
                        res = execute(c["function"]["name"], args, home, self.value_fn)
                        extra.append(res)
                        content = json.dumps(_compact(c["function"]["name"], res), ensure_ascii=False, default=str)
                    except Exception as e:  # tool error goes back to the model, not to the user
                        content = json.dumps({"error": str(e)})
                    msgs.append({"role": "tool", "tool_call_id": c["id"], "content": content})
                continue
            text = msg.get("content") or ""
            m = re.search(r"\{.*\}", text, re.S)
            try:
                data = json.loads(m.group(0)) if m else {"answer": text}
            except json.JSONDecodeError:
                data = {"answer": text}
            if not data.get("answer"):
                return None, extra, usage
            return data, extra, usage
        return None, extra, usage
