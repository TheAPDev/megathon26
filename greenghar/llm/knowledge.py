"""Project knowledge for the advisor prompt, built from the same reference tables the engine uses, so the prompt can
never drift from the backend. It teaches the model *what the terms mean*; every figure in a reply still has to come
from TOOL_RESULT (the numeric verifier enforces that)."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from ..engine.score import BANDS, WEIGHTS
from ..reference import catalogue

FEWSHOT_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "llm" / "fewshot.json"

COMPONENT_MEANING = {
    "energy_efficiency": "how efficient the appliances are (AC star/age/inverter, fans, lighting, fridge, water heating, cooking fuel)",
    "consumption_intensity": "yearly grid units per square metre against the benchmark for the climate zone",
    "envelope": "roof and walls: cool roof, insulation, wall type, building age, floor position",
    "cooling_system": "cooling hardware and habits: AC tech, setpoint, coolers, fans",
    "windows_shading": "window-to-wall ratio, west-facing glass, shading, solar film",
    "renewables": "rooftop solar and net metering",
    "smart_use": "smart meter, time-of-day tariff use, smart plugs",
}


@lru_cache
def project_card() -> str:
    comps = "\n".join(f"- {k} (weight {w:g}): {COMPONENT_MEANING.get(k, '')}" for k, w in WEIGHTS.items())
    bands = ", ".join(
        f"{lo}+ {name}" if i == 0 else f"{lo}-{BANDS[i - 1][0] - 1} {name}" if lo else f"below {BANDS[i - 1][0]} {name}"
        for i, (lo, name) in enumerate(BANDS))
    cat = catalogue()
    rets = "\n".join(f"- {rid}: {r['name'] if isinstance(r, dict) else getattr(r, 'name', rid)}" for rid, r in cat.items())
    return f"""PROJECT FACTS (for understanding terms only; quote numbers only from TOOL_RESULT)
Green Ghar Score, 0-100, is the weighted sum of seven sub-scores:
{comps}
Bands: {bands}.
How the numbers are made: a physics model of the home's energy use, corrected by a LightGBM residual model; retrofits are
applied one after another in a fixed order so savings never double count; a separate ranker orders the options; property
value uplift is a hedonic model with a conformal interval. Confidence drops when usage is estimated rather than metered.
Money: Indian electricity slab tariffs by state, rupees (Rs / ₹); subsidy = PM Surya Ghar for rooftop solar plus state top-ups.
CO2: grid factor from the CEA baseline; LPG and other fuels use IPCC defaults. CO2 is an estimate, never an offset claim.
Retrofit ids you may see in tools:
{rets}
Indian context: ACs run roughly April-October; heatwave days drive AC hours; tenants and flat owners often cannot use the roof,
so rooftop items can be infeasible and must be refused with the reason, not worked around."""


@lru_cache
def fewshot_messages(max_examples: int = 3) -> list[dict]:
    """Curated (question -> grounded answer) turns built from the backend dataset by scripts/build_llm_dataset.py.
    Missing file is fine: the prompt then runs zero-shot."""
    try:
        data = json.loads(FEWSHOT_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    msgs: list[dict] = []
    for ex in data[:max_examples]:
        msgs += [{"role": "user", "content": ex["user"]}, {"role": "assistant", "content": ex["assistant"]}]
    return msgs
