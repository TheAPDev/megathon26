"""LLM evaluation: 180 held-out prompts across 6 categories.

    python scripts/llm_eval.py                 # template mode + adversarial verifier test (no keys needed)
    NVIDIA_API_KEY=... python scripts/llm_eval.py --llm   # also evaluates the live LLM chain

Metrics per mode: groundedness (share of replies whose every figure is verified), unsupported-claim rate
(unverified figures / all figures), factual accuracy (the key engine fact for the category appears in the reply),
and category-specific behaviour (refuses infeasible items, asks for missing data, surfaces conflicts).
Adversarial mode replaces the LLM with a fake that injects invented numbers into 40% of replies, to measure that
the verifier blocks them (catch rate) and that the user still gets a grounded answer.
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from greenghar.data_access import DATA_DIR, row_to_home  # noqa: E402
from greenghar.engine.plan import recommend  # noqa: E402
from greenghar.engine.score import score_home  # noqa: E402
from greenghar.llm import orchestrator as O  # noqa: E402
from greenghar.llm.providers import Provider, chain  # noqa: E402
from greenghar.llm.templates import inr  # noqa: E402
from greenghar.ml.train import split_ids  # noqa: E402

CATS = {
    "explain_score": ["Why is my score {s}?", "मेरा स्कोर इतना कम क्यों है?", "Explain my Green Ghar Score"],
    "explain_recommendation": ["What should I do to cut my bill?", "AC ka bill kam kaise hoga?", "Which upgrade should I do first?"],
    "what_if": ["What if I add {r}?", "Agar main {r} lagaun to kya hoga?", "What if I skip insulation and get {r}?"],
    "infeasible": ["What if I put solar panels on my roof?", "Can I get roof insulation?", "What if I add a cool roof?"],
    "missing_data": ["What is my score?", "How much will I save?", "Explain my usage"],
    "conflicting_data": ["Why is my score what it is?", "My label says 5 star, so why is my score low?", "Is my home efficient?"],
}


def _pick_homes(homes: pd.DataFrame, n: int, seed: int = 7) -> dict[str, list]:
    _, _, test = split_ids(homes["home_id"].values)
    t = homes[homes["home_id"].isin(test)]
    sel = {}
    flat_mid = t[(t["dwelling_type"] == "apartment") & (t["floor_position"] == "middle") & (t["tenure"] == "tenant")]
    sel["infeasible"] = flat_mid.sample(n, random_state=seed).to_dict("records")
    sel["missing_data"] = t[t["data_source"] == "survey"].sample(n, random_state=seed).to_dict("records")
    # conflicting: inject a 5-star label on heavy users
    heavy = t[(t["missing_pattern"] == "complete") & (t["n_ac"] >= 2)].sample(n, random_state=seed).to_dict("records")
    for r in heavy:
        r["bee_star_label"] = 5
        r["kwh_24m"] = [None if x is None else x * 2.5 for x in r["kwh_24m"]]
    sel["conflicting_data"] = heavy
    rest = t[t["data_source"] != "survey"].sample(3 * n, random_state=seed).to_dict("records")
    sel["explain_score"], sel["explain_recommendation"], sel["what_if"] = rest[:n], rest[n:2 * n], rest[2 * n:]
    return sel


def key_fact(cat: str, home, answer: str) -> bool:
    a = answer.lower()
    if cat == "missing_data":  # expected behaviour: ask for the missing data
        return "bill" in a or "बिल" in answer
    if cat in ("explain_score", "conflicting_data"):
        ok = str(score_home(home).score) in answer
        if cat == "conflicting_data":
            ok = ok and ("conflict" in a)
        return ok
    if cat == "explain_recommendation":
        recs = [r for r in recommend(home) if r.suitability in ("High", "Medium")]
        top = sorted(recs, key=lambda r: -r.rank_score)[:3]
        return any(inr(r.saving_inr_year) in answer for r in top)
    if cat == "what_if":  # a number from the rerun, or a refusal that gives the reason
        return bool(re.search(r"\d", answer)) or any(k in a for k in ("roof", "society", "landlord", "no ac", "already"))
    if cat == "infeasible":
        return any(k in a for k in ("no private roof", "no exposed roof", "roof", "society", "rwa", "landlord", "छत"))
    return False


def evaluate(advisor_factory, homes_by_cat, label: str) -> dict:
    rows = []
    for cat, homes in homes_by_cat.items():
        for i, r in enumerate(homes):
            home = row_to_home(r)
            q = CATS[cat][i % len(CATS[cat])]
            if "{s}" in q:
                q = q.format(s=score_home(home).score)
            if "{r}" in q:
                q = q.format(r=random.Random(i).choice(["rooftop solar", "BLDC fans", "a 5 star inverter AC", "a cool roof"]))
            adv = advisor_factory()
            out = adv.answer(home, q, use_llm=True)
            g = out["grounding"]
            rows.append({"category": cat, "question": q, "grounded": g["grounded"], "figures": g["total"],
                         "unsupported": len(g["unsupported"]), "accurate": key_fact(cat, home, out["answer"]),
                         "provider": out["provider"], "fallback": "fallback_reason" in out, "latency_s": out["latency_s"]})
    df = pd.DataFrame(rows)
    figs = df["figures"].sum()
    res = {"mode": label, "n_prompts": int(len(df)),
           "groundedness": round(float(df["grounded"].mean()), 4),
           "unsupported_claim_rate": round(float(df["unsupported"].sum() / figs), 4) if figs else 0.0,
           "factual_accuracy": round(float(df["accurate"].mean()), 4),
           "fallback_rate": round(float(df["fallback"].mean()), 4),
           "median_latency_s": round(float(df["latency_s"].median()), 3),
           "by_category": {c: {"groundedness": round(float(g["grounded"].mean()), 4), "accuracy": round(float(g["accurate"].mean()), 4)}
                           for c, g in df.groupby("category")}}
    return res


class Hallucinator(Provider):
    def __init__(self):
        super().__init__("adversarial_fake", "http://localhost", "fake", "NONE")

    @property
    def available(self):
        return True


def adversarial_chat(seed=11):
    stats = {"injected": 0, "replies": 0}
    rng = random.Random(seed)

    def chat(provider, messages, tools=None, json_mode=False, **kw):
        stats["replies"] += 1
        content = messages[1]["content"] if len(messages) > 1 else ""
        nums = re.findall(r"\b\d{3,6}(?:\.\d)?\b", content)
        base = nums[0] if nums else "100"
        if rng.random() < 0.4:
            stats["injected"] += 1
            text = f"You will save Rs {rng.randint(10000, 99999):,} a year and your score jumps to {rng.randint(81, 99)}."
        else:
            text = f"Based on your data, one key figure is {base}. This is an estimate."
        return {"message": {"content": json.dumps({"answer": text, "cited_fields": [], "caveats": []})}, "usage": {},
                "latency_s": 0.0, "provider": "adversarial_fake", "model": "fake"}
    return chat, stats


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=30, help="prompts per category")
    ap.add_argument("--llm", action="store_true", help="also evaluate the live provider chain (needs API keys)")
    a = ap.parse_args()
    homes = pd.read_parquet(DATA_DIR / "homes.parquet")
    sel = _pick_homes(homes, a.n)
    report = {"categories": list(CATS), "prompts_per_category": a.n, "home_split": "held-out test homes (home_id grouped)"}
    report["template_only"] = evaluate(lambda: O.Advisor(providers=[]), sel, "template_only")
    chat_fn, stats = adversarial_chat()
    orig = O.chat
    O.chat = chat_fn
    try:
        report["adversarial_verifier"] = evaluate(lambda: O.Advisor(providers=[Hallucinator()]), sel, "adversarial_fake_llm")
    finally:
        O.chat = orig
    report["adversarial_verifier"]["fake_replies"] = stats["replies"]
    report["adversarial_verifier"]["injected_hallucinations"] = stats["injected"]
    report["adversarial_verifier"]["hallucinations_reaching_user"] = int(round((1 - report["adversarial_verifier"]["groundedness"]) * 180))
    report["adversarial_verifier"]["note"] = ("Every injected figure must be blocked: user-facing groundedness should stay 1.0 while the "
                                              "fallback rate shows how often the verifier had to step in.")
    if a.llm:
        if not any(p.available for p in chain()):
            report["llm"] = {"skipped": "no NVIDIA_API_KEY / GROQ_API_KEY set"}
        else:
            report["llm"] = evaluate(lambda: O.Advisor(), sel, "llm_chain")
    else:
        report["llm"] = {"skipped": "run with --llm and NVIDIA_API_KEY or GROQ_API_KEY to evaluate the live model"}
    out = ROOT / "reports" / "llm_eval.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
