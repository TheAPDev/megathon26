"""Build the AI Saathi training / adaptation set from the backend dataset (data/generated/homes.parquet).

    python scripts/build_llm_dataset.py                  # template-verified gold answers (offline)
    python scripts/build_llm_dataset.py --distill        # also ask the live model (needs NVIDIA_API_KEY + network); keep only verified replies

Each example is a real home from the TRAIN split (the 15% held-out homes used by scripts/llm_eval.py are never touched),
a question in English / Hindi / Hinglish, the engine's actual TOOL_RESULT for that home, and a reply whose every number
passed greenghar.llm.verifier. Outputs (data/llm/):
  sft_train.jsonl, sft_val.jsonl   chat-format SFT data ({"messages": [system, user, assistant]}), usable with NeMo
                                   Customizer / any OpenAI-style fine-tuning service
  fewshot.json                     3 short examples injected into the live prompt (in-context adaptation, no GPU needed)
  manifest.json                    counts, splits, grounding rate, source hash
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from greenghar.data_access import DATA_DIR, row_to_home  # noqa: E402
from greenghar.engine.score import score_home  # noqa: E402
from greenghar.llm import orchestrator as O  # noqa: E402
from greenghar.llm.providers import chain  # noqa: E402
from greenghar.llm.tools import execute  # noqa: E402
from greenghar.llm.verifier import verify  # noqa: E402
from greenghar.ml.train import split_ids  # noqa: E402

OUT = ROOT / "data" / "llm"
RETROFITS = ["rooftop solar", "BLDC fans", "a 5 star inverter AC", "a cool roof", "LED bulbs", "roof insulation", "a solar water heater"]
Q = {
    "explain_score": ["Why is my score {s}?", "Explain my Green Ghar Score", "मेरा स्कोर इतना कम क्यों है?", "Mera score kaisa hai aur kyon?", "What does my score mean?"],
    "recommend": ["What should I do to cut my bill?", "AC ka bill kam kaise hoga?", "Which upgrade should I do first?", "मेरा बिल कैसे कम होगा?", "Bijli bill kam karne ke liye kya karu?", "Suggest the best energy savings for my home"],
    "what_if": ["What if I add {r}?", "Agar main {r} lagaun to kya hoga?", "What if I skip insulation and get {r}?", "How much will I save with {r}?"],
    "budget": ["I have a budget of {b} rupees, what should I do?", "Mera budget {b} hazaar hai, kya karu?", "Plan upgrades for a budget of {b}"],
    "finance": ["Can I afford solar with an EMI?", "Kya loan lekar AC badal sakta hu?", "What would the loan EMI be for a new AC and BLDC fans?"],
    "solar": ["How much subsidy do I get for rooftop solar?", "Surya Ghar subsidy kitni milegi?", "What size solar should I install?"],
    "heatwave": ["How do I prepare for the heatwave?", "Garmi mein AC bill kaise bachaun?", "Will a cool roof keep my home cooler this summer?"],
}


def _fmt(q: str, i: int, rng: random.Random, home) -> str:
    if "{s}" in q:
        q = q.replace("{s}", str(score_home(home).score))
    if "{r}" in q:
        q = q.replace("{r}", rng.choice(RETROFITS))
    if "{b}" in q:
        q = q.replace("{b}", str(rng.choice([30, 50, 75, 100, 150]) if "hazaar" in q else rng.choice([30000, 60000, 100000, 200000])))
    return q


def sample_homes(df: pd.DataFrame, n: int, seed: int) -> list[tuple[str, dict]]:
    """(situation, row): mostly ordinary homes, plus the hard cases the advisor must handle well."""
    rng = random.Random(seed)
    out: list[tuple[str, dict]] = []
    flat = df[(df["dwelling_type"] == "apartment") & (df["floor_position"] == "middle") & (df["tenure"] == "tenant")]
    survey = df[df["data_source"] == "survey"]
    heavy = df[(df["missing_pattern"] == "complete") & (df["n_ac"] >= 2)]
    for sit, pool, share in (("infeasible", flat, 0.15), ("missing_data", survey, 0.15), ("conflict", heavy, 0.10), ("ordinary", df[df["data_source"] != "survey"], 0.60)):
        k = int(n * share)
        for r in pool.sample(min(k, len(pool)), random_state=rng.randrange(10**6)).to_dict("records"):
            if sit == "conflict":
                r["bee_star_label"] = 5
                r["kwh_24m"] = [None if x is None else x * 2.5 for x in r["kwh_24m"]]
            out.append((sit, r))
    rng.shuffle(out)
    return out


def distill(adv, home, q, lang):
    """Ask the live model; return its reply only if the numeric verifier passes (rejection sampling)."""
    out = adv.answer(home, q, preferred_language=lang, use_llm=True)
    return out if out["provider"] != "template" and out["grounding"]["grounded"] else None


def _ex(home, q, tool_args, answer_fn):
    """One hand-styled example: real tool output for a real home, answer built from that output, then verified."""
    results = [(n, execute(n, a, home, None)) for n, a in tool_args]
    compact = [O._compact(n, r) for n, r in results]
    ans = answer_fn(compact)
    if ans is None or not verify(ans["answer"], compact)["grounded"] or len(json.dumps(compact, default=str)) > 6000:
        return None
    return {"user": O.user_turn(compact, q), "assistant": json.dumps(ans, ensure_ascii=False), "home_id": home.home_id}


def curated_fewshot(df: pd.DataFrame, rng: random.Random) -> list[dict]:
    """Three conversational examples (score explanation, Hinglish recommendation, infeasible refusal)."""
    out = []

    def score_ans(c):
        f = c[0]["facts"]
        comps = sorted(f["components"], key=lambda x: x["score"])
        lo = comps[0]
        return {"answer": f"Your Green Ghar Score is {f['score']} out of 100, which is in the {f['band']} band. The biggest drag is {lo['component'].replace('_', ' ')} at {lo['score']:g}/100 ({lo['why'].rstrip('.')}). "
                          f"Fixing that is the quickest way to move your score. These are estimates.",
                "cited_fields": ["score", "band", "components"], "caveats": ["Estimates, not guarantees."]}

    def rec_ans(c):
        top = (c[0]["facts"].get("top_recommendations") or [None])[0]
        if not top:
            return None
        return {"answer": f"Sabse pehle {top['name']} karwaiye. Isse lagbhag ₹{top['saving_inr_year']:,.0f} saal ki bachat ho sakti hai, aur kharcha ₹{top['cost_inr_min']:,.0f} se ₹{top['cost_inr_max']:,.0f} ke beech aayega. "
                          f"Yeh sirf andaza hai, pakka vaada nahi.",
                "cited_fields": ["top_recommendations"], "caveats": ["Estimates, not guarantees."]}

    def infeasible_ans(c):
        ref = (c[0]["facts"].get("refused") or [None])[0]
        if not ref:
            return None
        return {"answer": f"Rooftop solar is not possible for your home right now. {ref['reason']} Your score stays {c[0]['facts']['score_before']} until something else changes, so I have not shown any savings for it.",
                "cited_fields": ["refused", "score_before"], "caveats": ["Estimates, not guarantees."]}

    ok = df[df["data_source"] != "survey"].sample(60, random_state=3)
    flat = df[(df["dwelling_type"] == "apartment") & (df["floor_position"] == "middle") & (df["tenure"] == "tenant") & (df["data_source"] != "survey")].sample(40, random_state=3)
    jobs = [(ok, "Why is my score what it is?", [("get_score", {})], score_ans),
            (ok.iloc[::-1], "Mera bijli bill kam karne ke liye sabse pehle kya karu?", [("get_recommendations", {})], rec_ans),
            (flat, "What if I put solar panels on my roof?", [("run_scenario", {"retrofits": ["rooftop_solar"]})], infeasible_ans)]
    for pool, q, calls, fn in jobs:
        for r in pool.to_dict("records"):
            ex = _ex(row_to_home(r), q, calls, fn)
            if ex:
                out.append(ex)
                break
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=1500)
    ap.add_argument("--seed", type=int, default=21)
    ap.add_argument("--distill", action="store_true")
    a = ap.parse_args()

    path = DATA_DIR / "homes.parquet"
    df = pd.read_parquet(path)
    train_ids, _, _ = split_ids(df["home_id"].values)
    df = df[df["home_id"].isin(train_ids)]  # never the validation/test homes
    live = [p for p in chain() if p.available] if a.distill else []
    if a.distill and not live:
        sys.exit("--distill needs NVIDIA_API_KEY / GROQ_API_KEY in the environment (or .env) and network access")
    adv_tpl, adv_llm = O.Advisor(providers=[]), (O.Advisor(providers=live) if live else None)

    rng = random.Random(a.seed)
    examples, seen, stats = [], set(), Counter()
    for sit, row in sample_homes(df, a.n, a.seed):
        home = row_to_home(row)
        intent = rng.choice(list(Q))
        q = _fmt(rng.choice(Q[intent]), 0, rng, home)
        key = (home.home_id, q)
        if key in seen:
            continue
        seen.add(key)
        lang = O.detect_language(q)
        calls = O.route(q)
        results = [(n, execute(n, args, home, None)) for n, args in calls]
        compact = [O._compact(n, r) for n, r in results]
        base = adv_tpl.answer(home, q, use_llm=False)
        gold, source = base, "template"
        if adv_llm:
            d = distill(adv_llm, home, q, lang)
            if d:
                gold, source = d, "nemotron_verified"
        if not gold["grounding"]["grounded"] or not gold["answer"].strip():
            stats["dropped_ungrounded"] += 1
            continue
        reply = {"answer": gold["answer"], "cited_fields": gold.get("cited_fields") or [n for n, _ in calls],
                 "caveats": gold.get("caveats") or ["Estimates, not guarantees."]}
        examples.append({"home_id": home.home_id, "situation": sit, "intent": intent, "language": lang, "source": source,
                         "tool_calls": [n for n, _ in calls], "chars": len(json.dumps(compact, default=str)),
                         "messages": [{"role": "system", "content": O.system_prompt(lang)},
                                      {"role": "user", "content": O.user_turn(compact, q)},
                                      {"role": "assistant", "content": json.dumps(reply, ensure_ascii=False)}]})
        stats[sit] += 1
        stats[f"lang_{lang}"] += 1
        stats[f"src_{source}"] += 1

    # the verifier is the gate: re-check every stored assistant turn against its own TOOL_RESULT block
    bad = 0
    for ex in examples:
        user = ex["messages"][1]["content"]
        tr = json.loads(user.split("TOOL_RESULT:\n", 1)[1].split("\n\nQUESTION:", 1)[0])
        ans = json.loads(ex["messages"][2]["content"])["answer"]
        bad += not verify(ans, tr)["grounded"]
    assert bad == 0, f"{bad} stored replies fail the verifier"

    ids = sorted({e["home_id"] for e in examples})
    val_ids = set(random.Random(a.seed).sample(ids, max(1, len(ids) // 10)))
    tr = [e for e in examples if e["home_id"] not in val_ids]
    va = [e for e in examples if e["home_id"] in val_ids]
    OUT.mkdir(parents=True, exist_ok=True)
    for name, rows in (("sft_train.jsonl", tr), ("sft_val.jsonl", va)):
        with open(OUT / name, "w", encoding="utf-8") as f:
            for e in rows:
                f.write(json.dumps({"messages": e["messages"], "meta": {k: e[k] for k in ("home_id", "situation", "intent", "language", "source")}}, ensure_ascii=False) + "\n")

    pick = curated_fewshot(df, rng)
    json.dump(pick, open(OUT / "fewshot.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    manifest = {"source": "data/generated/homes.parquet", "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest()[:16],
                "split": "train homes only (70%); val/test homes excluded", "examples_train": len(tr), "examples_val": len(va),
                "homes": len(ids), "grounded_rate": 1.0, "stats": dict(stats), "seed": a.seed, "distilled": bool(adv_llm),
                "fewshot_examples": len(pick)}
    json.dump(manifest, open(OUT / "manifest.json", "w"), indent=1)
    print(json.dumps(manifest, indent=1))


if __name__ == "__main__":
    main()
