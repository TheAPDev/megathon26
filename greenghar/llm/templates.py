"""Deterministic, template-only explanations (English and Hindi).

Used as (1) the fallback whenever no LLM is available or the verifier rejects an LLM reply, and
(2) the 'template-only' baseline in the LLM evaluation. Every number is copied from tool facts."""
from __future__ import annotations

from ..reference import catalogue


def inr(x: float | None) -> str:
    """Indian grouping: 123456.0 -> '1,23,456'."""
    if x is None:
        return "n/a"
    neg = x < 0
    s = str(int(round(abs(x))))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        s = ",".join(groups + [tail])
    return ("-" if neg else "") + s


def kwh(x: float) -> str:
    return inr(x)


NAMES_HI = {"cool_roof": "कूल रूफ पेंट", "roof_insulation": "छत इन्सुलेशन", "external_shading": "बाहरी छज्जा/शेड",
            "solar_film": "सोलर फिल्म", "ac_setpoint": "AC 24°C पर", "smart_plug_tod": "स्मार्ट प्लग/टाइमर",
            "ac_5star_inverter": "5-स्टार इन्वर्टर AC", "bldc_fans": "BLDC पंखे", "led_lighting": "LED लाइट",
            "fridge_5star": "5-स्टार फ्रिज", "solar_water_heater": "सोलर वॉटर हीटर", "heat_pump_geyser": "हीट-पंप गीज़र",
            "induction_cooking": "इंडक्शन कुकिंग", "lithium_battery": "लिथियम इन्वर्टर बैटरी", "rooftop_solar": "रूफटॉप सोलर"}
BAND_HI = {"Highly efficient": "बहुत कुशल", "Good": "अच्छा", "Moderate": "मध्यम", "Poor": "कमज़ोर", "Very poor": "बहुत कमज़ोर"}


def name(rid: str, lang: str) -> str:
    return NAMES_HI.get(rid, catalogue()[rid]["name"]) if lang == "hi" else catalogue()[rid]["name"]


def score_text(f: dict, lang: str = "en") -> str:
    comps = sorted(f["components"], key=lambda c: c["score"])
    weakest = comps[0]
    if lang == "hi":
        t = (f"आपका ग्रीन घर स्कोर {f['score']}/100 है ({BAND_HI.get(f['band'], f['band'])}). "
             f"सबसे कमज़ोर हिस्सा: {weakest['component'].replace('_', ' ')} ({weakest['score']:.0f}/100) — {weakest['why']}. ")
        if f["warnings"]:
            t += "ध्यान दें: " + " ".join(f["warnings"]) + " "
        t += "यह एक अनुमान है।"
        return t
    t = (f"Your Green Ghar Score is {f['score']}/100 ({f['band']}). The weakest part is "
         f"{weakest['component'].replace('_', ' ')} at {weakest['score']:.0f}/100: {weakest['why']}. ")
    if f.get("annual_grid_kwh") is not None:
        t += f"You use about {kwh(f['annual_grid_kwh'])} units a year{' (estimated)' if f['annual_grid_kwh_estimated'] else ''}. "
    if f["warnings"]:
        t += " ".join(f["warnings"]) + " "
    if f["confidence"] != "high":
        t += f"Confidence is {f['confidence']}: {'; '.join(f['confidence_reasons'])}. "
    return t + "This is an estimate."


def recs_text(f: dict, lang: str = "en", top: int = 3) -> str:
    recs = [r for r in f["recommendations"] if r["suitability"] in ("High", "Medium")]
    recs = sorted(recs, key=lambda r: -r["rank_score"])[:top]
    if not recs:
        return "कोई उपयुक्त सुधार नहीं मिला।" if lang == "hi" else "No suitable upgrades found for this home."
    lines = []
    for r in recs:
        if lang == "hi":
            lines.append(f"{name(r['retrofit_id'], 'hi')}: लगभग ₹{inr(r['saving_inr_year'])}/साल बचत, लागत ₹{inr(r['cost_inr_min'])}–₹{inr(r['cost_inr_max'])}")
        else:
            pb = f", payback about {r['payback_years']} years" if r.get("payback_years") else ""
            lines.append(f"{r['name']}: saves about Rs {inr(r['saving_inr_year'])} a year, costs Rs {inr(r['cost_inr_min'])}-{inr(r['cost_inr_max'])}{pb}")
    head = "आपके लिए सबसे अच्छे कदम: " if lang == "hi" else "Your best next steps: "
    tail = " (अनुमान)" if lang == "hi" else " These are estimates."
    return head + "; ".join(lines) + "." + tail


def scenario_text(f: dict, lang: str = "en") -> str:
    parts = []
    for r in f.get("refused", []):
        parts.append((f"{name(r['retrofit_id'], lang)}: " + r["reason"]))
    if not f.get("steps"):
        return " ".join(parts) or ("कोई बदलाव लागू नहीं हुआ।" if lang == "hi" else "No change could be applied.")
    el, lpg = f["per_fuel_saving_kwh"]["electricity"], f["per_fuel_saving_kwh"]["lpg"]
    if lang == "hi":
        t = f"अनुमान: बिजली {'बचत' if el >= 0 else 'बढ़ोतरी'} {kwh(abs(el))} यूनिट/साल"
        if lpg:
            t += f", LPG बचत {kwh(lpg)} kWh"
        co2 = f["co2_saving_kg_year"]
        t += (f", कुल बचत ₹{inr(f['saving_inr_year'])}/साल, CO2 में {inr(abs(co2))} kg {'कमी' if co2 >= 0 else 'बढ़ोतरी'}। "
              f"स्कोर {f['score_before']} से {f['score_after']}।")
    else:
        t = f"Estimated: electricity {'falls' if el >= 0 else 'rises'} by {kwh(abs(el))} units a year"
        if lpg:
            t += f" and LPG falls by {kwh(lpg)} kWh"
        co2 = f["co2_saving_kg_year"]
        t += (f"; you save about Rs {inr(f['saving_inr_year'])} a year and CO2 {'falls' if co2 >= 0 else 'rises'} by {inr(abs(co2))} kg. "
              f"Your score moves from {f['score_before']} to {f['score_after']}.")
        if el < 0:
            t += " Electricity goes up because cooking moves from LPG to the grid."
            if co2 < 0:
                t += " On today's grid that adds CO2; pairing it with rooftop solar turns it into a cut."
    if parts:
        t += " " + " ".join(parts)
    return t


def finance_text(f: dict, lang: str = "en") -> str:
    if not f.get("retrofits"):
        reasons = " ".join(r["reason"] for r in f.get("refused", []))
        return reasons or ("कोई सुधार लागू नहीं।" if lang == "hi" else "None of these upgrades apply to this home.")
    if lang == "hi":
        t = (f"कुल लागत ₹{inr(f['net_cost_inr'])} (सब्सिडी ₹{inr(f['subsidy_inr'])} के बाद)। मासिक EMI ₹{inr(f['total_emi_inr_month'])}, "
             f"मासिक बिल बचत ₹{inr(f['bill_saving_inr_month'])}। ")
        t += "EMI बचत से कम है।" if f["emi_covered_by_saving"] else "EMI बचत से ज़्यादा है।"
        return t + " (अनुमान)"
    t = (f"Net cost Rs {inr(f['net_cost_inr'])} after Rs {inr(f['subsidy_inr'])} subsidy. Monthly EMI Rs {inr(f['total_emi_inr_month'])} "
         f"vs monthly bill saving Rs {inr(f['bill_saving_inr_month'])}: "
         + ("the saving covers the EMI from month one." if f["emi_covered_by_saving"] else "the EMI is higher than the saving.")
         + (f" Simple payback about {f['simple_payback_years']} years." if f.get("simple_payback_years") else ""))
    if f.get("pivot_note"):
        t += " " + f["pivot_note"]
    return t + " Estimates; lender rates are indicative."


def solar_text(f: dict, lang: str = "en") -> str:
    q, s = f["quote"], f["subsidy"]
    if not s["eligible"]:
        return s["why_not"]
    if lang == "hi":
        return (f"{q['kw']} kW सोलर: सालाना {kwh(q['annual_generation_kwh'])} यूनिट, PM सूर्य घर सब्सिडी ₹{inr(q['central_subsidy_inr'])}"
                f", नेट लागत ₹{inr(q['net_cost_inr'][0])}–₹{inr(q['net_cost_inr'][1])}। (अनुमान)")
    return (f"A {q['kw']} kW system makes about {kwh(q['annual_generation_kwh'])} units a year. PM Surya Ghar subsidy Rs "
            f"{inr(q['central_subsidy_inr'])}" + (f" plus state top-up Rs {inr(q['state_topup_inr'])}" if q["state_topup_inr"] else "")
            + f"; net cost Rs {inr(q['net_cost_inr'][0])}-{inr(q['net_cost_inr'][1])}. Estimate.")


def roadmap_text(f: dict, lang: str = "en") -> str:
    parts = []
    for y in f["years"]:
        items = ", ".join(name(i["retrofit_id"], lang) for i in y["items"]) or ("कुछ नहीं" if lang == "hi" else "nothing")
        parts.append((f"साल {y['year']}: {items} (₹{inr(y['spend_inr'])})" if lang == "hi"
                      else f"Year {y['year']}: {items} (Rs {inr(y['spend_inr'])}, saves Rs {inr(y['saving_inr_year'])}/yr)"))
    return "; ".join(parts) + (" (अनुमान)" if lang == "hi" else ". Estimates.")


def heatwave_text(f: dict, lang: str = "en") -> str:
    good = [m for m in f["measures"] if m.get("suitability") in ("High", "Medium")]
    if not good:
        return "No roof or shading measures apply to this home." if lang == "en" else "इस घर पर छत/शेड के उपाय लागू नहीं होते।"
    m = good[0]
    lo, hi = m["indoor_peak_drop_c"]
    if lang == "hi":
        return f"{name(m['retrofit_id'], 'hi')} से घर का तापमान {lo}–{hi}°C तक कम हो सकता है और अप्रैल–जून में {inr(m['ac_hours_avoided_apr_jun'])} AC घंटे बचेंगे।"
    return (f"Before May: {m['retrofit_id'].replace('_', ' ')} can cut the indoor peak by {lo}-{hi} C and avoid about "
            f"{inr(m['ac_hours_avoided_apr_jun'])} AC hours in April-June. Estimate.")


def missing_data_text(lang: str = "en") -> str:
    return ("बेहतर अनुमान के लिए अपने पिछले बिजली बिल की फोटो भेजें।" if lang == "hi"
            else "Send a photo of your recent electricity bills (ideally 12 months) so the estimate uses your real usage.")


RENDER = {"get_score": score_text, "get_recommendations": recs_text, "run_scenario": scenario_text,
          "get_finance_plan": finance_text, "get_solar_quote": solar_text, "get_roadmap": roadmap_text, "get_heatwave": heatwave_text}
