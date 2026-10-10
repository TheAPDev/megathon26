# Model card: Green Ghar engines and models

All metrics are on held-out **test** homes from a home-grouped 70/15/15 split (seed 42). Each model was selected on validation, and test metrics were computed once. Full numbers are in `reports/eval_report.json` and the API route `/lab/metrics`.

## 1. Green Ghar Score (deterministic)
- **What it is:** 7 sub-scores with fixed weights 0.25/0.20/0.15/0.15/0.10/0.10/0.05. Only the final score is rounded.
- **Monotonicity:** tested two ways:
  - Hypothesis property tests: 150 random homes x 12 improvements, plus metered-use reductions.
  - A 300-home sweep with 16,704 checks and **0 failures**.
- **Parity:** the SQL port `gg.score` matches Python exactly on sampled database homes.

## 2. Annual energy model (fills missing data)
| Model | Test MAE (kWh/yr) | MAPE | R² |
|---|---|---|---|
| Baseline: median by zone x type x AC count | 944 | 26.0% | 0.62 |
| Physics only | 502 | 11.7% | 0.88 |
| LightGBM direct | 390 | 9.8% | 0.93 |
| **Hybrid: physics x LightGBM residual** (selected) | **384** | **9.7%** | **0.94** |

- **Improvement:** 59% lower MAE than the baseline.
- **Top SHAP drivers:** income band, work-from-home and city. These are the hidden effects the physics model doesn't know about, which is the intended behaviour.
- **Use:** only for homes with fewer than 6 months of usage data. Results are always labelled as estimates.

## 3. Retrofit relevance ranker (LightGBM LambdaRank)
| Ranker | NDCG@5 | Precision@3 |
|---|---|---|
| Popularity baseline | 0.881 | 0.720 |
| Rules (physics ROI x suitability) | 0.976 | 0.904 |
| **LambdaRank** | **0.986** | **0.942** |

- **Labels:** true incremental ROI from the ground-truth simulator (4,000 homes, 37,170 pairs).
- **Infeasible-recommendation rate: 0%.** Candidates are gated by hard feasibility rules before ranking.

## 4. Savings model (validation against the truth simulator)
- **Electricity MAE per retrofit:** physics only 36.1 kWh; metered-scaled hybrid 23.1 kWh.
- **Sign accuracy:** 100%, including LPG to induction raising electricity use.
- **Package savings:** applied sequentially in interaction order, never summed (tested).

## 5. Hedonic value model + split-conformal intervals
| Model | Test MAPE |
|---|---|
| Baseline: city x type median price per sq ft | 11.4% |
| Baseline: flat rating rule | 29.5% |
| **LightGBM hedonic** (score constrained to be monotonic) | **6.7%** |

- **Intervals:** an 80% split-conformal interval has **81.6% coverage** on test, with a width of about ±12%.
- **Uplift:** counterfactual, predicting the same home at its before and after score. The range comes from a 10-model bootstrap.
- **Labelling:** shown as *indicative, not proven causal*. It returns *unavailable* when carpet area is missing.
- **Caveat:** the premium recovered (1.63% per 10 points) matches the generator's assumption (1.5%). That is internal consistency only.

## 6. LLM layer (grounded by construction)
- **The LLM never calculates.** Tools return engine JSON, and a numeric verifier checks every figure in the reply.
  - On a mismatch: one retry, then a template fallback.
- **Template-only baseline** (180 held-out prompts across 6 categories): groundedness 1.00, unsupported claims 0.00, factual accuracy 0.99. Full numbers are in `reports/llm_eval.json`.
- **Adversarial test:** a fake LLM injects invented figures into 40% of replies (95 injected); **0** reach the user.
- **Live LLM metrics:** run `python scripts/llm_eval.py --llm` with `NVIDIA_API_KEY` or `GROQ_API_KEY` set.

## Limitations
- Everything is trained on synthetic data. Real-world accuracy has to be re-established on pilot data.
- Tariffs, subsidies and prices are indicative (October 2026) and must be verified.
- Climate normals are approximate city means; there is no microclimate or building-orientation modelling.
- The value premium is an assumption, not Indian market evidence.
