# Green Ghar Score: System Architecture Document

**Version** 1.0 · 10 October 2026 · **Owner** Backend team (Megathon X · PS2, India adaptation)
**Code** `greenghar/` (Python 3.12, FastAPI) · **Database** Supabase project `green-ghar` (ref `rnsirfybfxfjnlhteurm`, region ap-south-1, Postgres 17)

---

## 1. Executive summary and core objectives

### 1.1 System overview
Green Ghar Score is the backend for an Indian home-energy product that a bank or housing-finance company runs for its customers. For any home it:

1. computes a 0-100 **Green Ghar Score** from metered usage (smart meter, a photographed bill, or bill-payment history) and a short survey, with a per-component explanation and a data-confidence badge;
2. produces a **retrofit plan** of feasible upgrades (cool roof, 5-star inverter AC, BLDC fans, rooftop solar and so on), ordered by physical interaction, with per-fuel kWh, rupee savings at the household's real tariff slab, CO₂ and payback;
3. reruns the engine for **what-if** questions in about 120 ms;
4. builds the **finance case**: PM Surya Ghar subsidy, loan EMI against monthly bill saving, 25-year savings, a budget roadmap, and an indicative property-value range;
5. answers questions through a **grounded multilingual advisor** (web chat and a Telegram bot, text or voice). Every figure is verified against engine output;
6. gives the lender a **portfolio view**: score distribution, poor homes, ranking by improvement potential, financed emissions, green-finance targets and housing-society leads;
7. exposes a **Model Lab** with metrics against baselines, live hidden-scenario tests, emission factors and the data card.

Business purpose: one reason to talk to every home-loan customer every summer, originating solar and efficiency loans, plus property-level energy data for climate-risk disclosure.

### 1.2 Core architectural goals
| Pillar | Target | How it is met |
|---|---|---|
| Correctness and rigour | Every number traceable to a documented model; monotonic score; no double counting | Deterministic engine, fixed weights, property-based tests, SQL/Python parity tests |
| Grounded AI | LLM groundedness ≥ 90%, unsupported claims < 5% | LLM narrates only; numeric verifier, then retry, then template fallback (measured: 100% / 0%) |
| Low latency | What-if p50 < 300 ms (measured 120 ms); score < 200 ms (measured 4-35 ms); chat < 3 s | Pure-Python engine (no I/O on the hot path), cached boosters, LLM reply cache |
| Reproducibility | One command rebuilds data, models and reports | Seed 42, `make all`, versioned reference CSVs, model content hashes |
| Graceful degradation | Works with zero external keys | Provider chains (NIM → Groq → template; Whisper on Groq → NIM; Magpie → edge-tts; Gemini → Tesseract) |
| Privacy | DPDP Act 2023 consent, least privilege | RLS on every table, service-role key server-side only, consent flags gate marketing lists, consumer numbers masked |
| Horizontal scalability | Stateless API replicas | All state in Postgres; the engine is pure functions; caches are per-replica and safe to lose |

---

## 2. High-level architecture and system context

### 2.1 Architectural pattern
**A modular monolith (one FastAPI service) with a database-side compute layer and offline batch jobs.**

- The engines (score, plan, finance, roadmap, heatwave) are pure functions of a `Home` value object. They need no network or database access and run in-process, which keeps what-if under 300 ms and makes them trivially testable.
- **Why not microservices:** the workload is CPU-light, the team is four people, and every screen needs the same engine. Network hops between services would cost latency and add operational load without isolating any real failure domain. The external-provider adapters (LLM, STT, TTS, OCR, Telegram) are the only parts likely to scale on their own, and they are already isolated behind interfaces so they can be split later (see Phase 3).
- **Database-side compute:** Postgres functions `gg.energy`, `gg.score` and `synth.generate` let analysts score and generate homes inside Supabase. Python stays the source of truth, and parity is enforced by tests.
- **Batch jobs:** data generation, model training, evaluation and portfolio rescoring run offline and write versioned artifacts (Parquet, LightGBM text models, JSON reports) and database rows.

### 2.2 System component map
```
                ┌────────────── Clients ──────────────┐
  Web / mobile dashboard (8 screens)   Telegram app (bot + Mini App)   Analyst console
                │                              │                         │
                ▼ HTTPS JSON                   ▼ Bot API webhook          ▼ HTTPS + X-API-Key
        ┌───────────────────────── FastAPI service (greenghar.api) ─────────────────────────┐
        │ middleware: request-id, timing, CORS, error envelope                              │
        │ routers: homes · advisor · channels (bills, speech, telegram) · portfolio · lab · reference │
        │                                                                                   │
        │ ┌──── engine (pure) ────┐  ┌──── ml (in-process) ────┐  ┌──── llm ────────────────┐ │
        │ │ physics  score  tariff│  │ energy hybrid (LightGBM) │  │ router → tools → LLM    │ │
        │ │ plan/what-if  solar   │  │ LambdaRank ranker        │  │ numeric verifier        │ │
        │ │ finance  roadmap      │  │ hedonic value + conformal│  │ templates (EN/HI)       │ │
        │ │ heatwave  portfolio   │  │ 10x bootstrap uplift     │  │ reply cache             │ │
        │ └───────────────────────┘  └──────────────────────────┘  └─────────────────────────┘ │
        │ memory store · bot (Telegram) · speech (STT/TTS) · ocr (bill) · lab (scenario suite) │
        │ repositories: LocalRepo (Parquet) | SupabaseRepo (PostgREST, service role)           │
        └───────────────┬──────────────────────────────┬────────────────────────────────────┘
                        │                              │ outbound HTTPS / gRPC
                        ▼                              ▼
     Supabase Postgres 17 (ap-south-1)        External providers (free tiers)
     public: 20 tables + meter_readings view   NVIDIA NIM (LLM, Whisper, Magpie TTS via Riva gRPC)
     gg: energy/score/rescore functions        Groq (LLM fallback, Whisper large-v3)
     synth: in-DB generator + truth table      Google Gemini Flash (bill OCR)
     RLS on every table; Supabase Auth          Telegram Bot API
                        ▲
     Offline jobs: generate_data · ml.train · llm_eval · bias_report · rescore_supabase · push_to_supabase
     Artifacts: data/generated/*.parquet · models/*.txt (+ .json meta, hash) · reports/*.json
```

### 2.3 Data and signal flow: primary request (what-if)
`POST /homes/H000011/scenario {"retrofits": ["cool_roof","ac_5star_inverter","rooftop_solar"]}`

1. **Middleware** assigns `X-Request-ID` (or reuses the caller's) and starts a timer.
2. **Validation:** Pydantic validates `ScenarioRequest`. Unknown retrofit ids return 422 `unknown_retrofit` with the valid list.
3. **Load home:** the `home_or_404` dependency asks the repository for the home. With `LocalRepo` that is a Parquet index lookup; with `SupabaseRepo` it is `GET /rest/v1/homes?home_id=eq.H000011` (one row, about 3 KB). The row becomes a `Home`; the last 12 readings are mapped to calendar order and nulls stay null.
4. **Profile:** `engine.consumption.profile` drops reading errors (a month more than 4x or less than 1/4 of the median implied annual), then annualises 6-11 months with seasonal weights. With fewer than 6 months it calls the ML energy model, and every such path is flagged as estimated.
5. **Scenario:** `engine.plan.run_scenario` sorts the retrofits by interaction order (envelope → controls → cooling → appliances/water/fuel switch → backup → generation). For each step it:
   - checks feasibility (an infeasible step is refused with a reason);
   - applies the retrofit to a copy of the home;
   - reruns physics;
   - scales the modelled monthly change onto the metered profile;
   - bills both states month by month at the state's slab tariff, with net metering and free-unit schemes;
   - computes per-fuel kWh, CO₂ (ΔE x factor per fuel) and cost net of subsidy.
   The package total is baseline minus after-all, never a sum of standalone steps.
6. **Score after:** `score_home(after, annual_override)`.
7. **Value:** `ml.predict.value_range` runs the hedonic model at score_before and score_after (counterfactual), adds the conformal interval, and takes the 10-model bootstrap uplift range.
8. **Response:** JSON with baseline, after, per-fuel savings, ₹, CO₂, improvement potential, score before/after, steps, refused items, value and data method (about 120 ms p50). The middleware adds `Server-Timing` and writes a structured log line.

**Advisor flow** (`POST /advisor/chat`):
1. Detect the language from the script; route the intent with keyword and Hinglish rules, including negation ("skip insulation").
2. Execute the tools deterministically.
3. If a provider is configured, send a compact `TOOL_RESULT` and the question to NVIDIA NIM; the LLM may call up to 3 more tools.
4. Verify every number in the reply against all tool JSON. On a mismatch, retry once with the unsupported figures named.
5. If it still fails, or no provider is available, use the template text.
6. Return the answer, language, provider, grounding badge, tool calls, latency and token usage.

**Telegram flow:**
1. Telegram calls `POST /telegram/webhook`; the secret-token header is checked.
2. A photo is downloaded via `getFile` → Gemini OCR → validated monthly units → a new home is created → score card with inline buttons.
3. A voice note is downloaded (OGG) → Whisper → advisor → text reply plus an optional voice reply (TTS).

---

## 3. Detailed component and service breakdown

### 3.1 API gateway layer: `greenghar.api`
- **Responsibility:** HTTP surface, validation, auth, error envelope, request context, OpenAPI. **Does not** hold business logic.
- **Stack:** FastAPI ≥ 0.115, Starlette, Pydantic v2, Uvicorn (2 workers per container).
- **State:** stateless. Per-process singletons hold the repository, the advisor (with its LRU reply cache of 512 entries) and the Telegram bot sessions (move to `telegram_links` in Phase 1).
- **Error format** (every non-2xx):
  `{"error": {"code": "home_not_found", "message": "Home X not found", "details": {}, "request_id": "a1b2c3d4e5f6a7b8"}}`
  Codes: `validation_error` (422), `unknown_retrofit` (422), `unknown_city` (422), `home_not_found` (404), `unknown_state` (404), `not_eligible` (409), `unauthorized` (401), `bad_secret` (401), `file_too_large` (413), `ocr_unavailable` / `stt_unavailable` / `tts_unavailable` (503), `internal_error` (500).

### 3.2 Engine: `greenghar.engine` (pure, deterministic)
| Module | Responsibility | Key rules |
|---|---|---|
| `physics.py` | Monthly end-use model: cooling (CDD base 24 °C, envelope factor, set-point, ISEER with 1%/yr degradation), fans and coolers, fridge, lighting, water heating, plug loads, induction, backup losses; PV generation, self-consumption and export | Solar cuts imports, not demand; generation, self-use and export are kept separate |
| `consumption.py` | Metered profile, outlier exclusion, seasonal annualisation, ML/physics prediction | Never zero-fills; every estimate is labelled |
| `score.py` | 7 sub-scores, fixed weights, bands, confidence, data-conflict warnings | Monotonic mappings; conflict when a 4-5★ label meets >1.5x benchmark use (or a 1-2★ label meets <0.6x) |
| `tariff.py` | State slab bills, category switches (Telangana), fuel surcharge, duty, free-unit schemes, net metering | Savings = bill(before) − bill(after), month by month |
| `retrofits.py` | Apply, feasibility (hard rules, then the zone table), cost ranges, PM Surya Ghar and state top-ups | Tenants: no roof, solar or structural work; mid-floor flats: no roof retrofits |
| `plan.py` | `run_scenario`, `recommend` (incremental savings in interaction order, optional ML ranker) | Package ≠ sum of parts; infeasible items refused |
| `solar.py` | Size PV to the post-efficiency load, the roof (10 m²/kW) and the sanctioned load | Rounded to 0.5 kW, minimum 1 kW |
| `finance.py` | Loans (solar ≤ 3 kW at 5.75%, top-up at 8.75%, consumer EMI), EMI vs saving, payback, 25-year savings (3% tariff escalation, 0.5%/yr PV degradation), subsidy navigator | Free-unit states pivot the message to comfort, backup and export |
| `roadmap.py` | Per-year 0/1 knapsack under a budget | Solar only after affordable envelope, controls and cooling items; drops items whose payback exceeds their lifetime |
| `heatwave.py` | Indoor peak drop ranges and April-June AC hours avoided | Literature ranges, labelled as estimates |
| `portfolio.py` | Lender analytics over `home_scores` | Financed CO₂ = home CO₂ x outstanding / property value |

### 3.3 ML: `greenghar.ml`
| Model | Algorithm | Features | Artifact |
|---|---|---|---|
| Energy | LightGBM regressor on log(actual/physics) | 46 allow-listed features (home attributes, physics outputs, city tier, summer temperature) | `models/energy_hybrid.txt` + `.json` (features, category maps, sha-12 version) |
| Ranker | LightGBM LambdaRank (NDCG@5) | retrofit id, suitability, order, cost, engine savings and ROI, home context | `models/ranker.txt` |
| Value | LightGBM regressor on log price, monotone in score; split-conformal q at α 0.2; 10 bootstrap boosters | city, zone, tier, type, floor, area, age at sale, month offset, score, city price/sq ft | `models/value_hedonic.txt`, `value_boot_*.txt` |

- **Training:** `python -m greenghar.ml.train` (about 25 s).
- **Inference:** in-process; boosters are loaded once and cached.
- **Leakage guard:** `features.FORBIDDEN`, enforced in code and tests.

### 3.4 LLM layer: `greenghar.llm`
- **`tools.py`:** 8 OpenAI-format tools: `get_score`, `get_recommendations`, `run_scenario`, `get_finance_plan`, `get_solar_quote`, `get_roadmap`, `get_heatwave`, `get_factors`. Each returns `{facts, data_quality}`.
- **`orchestrator.py`:** language detection (Devanagari, Tamil, Telugu, Kannada, Bengali, Gujarati scripts); the router; the provider loop (at most 3 tool rounds); verify, then retry, then fallback; a reply cache keyed on the hash of (home state, message, language).
- **`verifier.py`:** extracts numbers, handling ₹, Indian comma grouping, lakh/crore/k, %, and Devanagari digits. A figure matches a tool value within half the shown precision or 0.5%. Counts 0-12 and years 1990-2060 are exempt. A % token may match a fraction.
- **`providers.py`:** `httpx` POST to `/chat/completions` (OpenAI-compatible) with a 25 s timeout. HTTP 429 or 5xx moves on to the next provider.
- **`templates.py`:** deterministic EN/HI renderers, Indian number formatting.

### 3.5 Channels
| Component | Primary | Fallback | Notes |
|---|---|---|---|
| `speech/stt.py` | Groq Whisper large-v3 (multipart REST) | NVIDIA NIM Whisper | OGG accepted; `language` hint; 25 MB limit |
| `speech/tts.py` | NVIDIA Magpie TTS Multilingual (Riva gRPC `grpc.nvcf.nvidia.com:443`, `function-id` metadata) | edge-tts (hi/ta/mr/te/kn/bn/gu/en-IN voices) | Returns audio bytes and MIME type |
| `ocr/bill.py` | Gemini Flash `generateContent` with a JSON response | Tesseract + regex | Validation: plausible ranges, bi-monthly halving, consumer number masking |
| `bot/telegram.py` | Telegram Bot API (webhook) | n/a | `/start`, demo, photo, voice, text, inline buttons, Mini App button |

### 3.6 Memory: `greenghar.memory.store`
- **Holds:** constraints (`tenure: renting`, `budget_inr`, `exclude`), preferences (language) and feedback (`accepted` / `rejected`).
- **Behaviour:** `personalised_plan` applies the memory (excluded or over-budget flags), and `what_changed` diffs the plan before and after a new item.
- **Storage:** the `memory` table (Supabase), or the generated Parquet plus an in-process list when running locally.

### 3.7 Data storage: Supabase Postgres
Schemas:
- **`public`:** API-visible, with RLS.
- **`gg`:** engine functions; not exposed.
- **`synth`:** generator and the hidden truth table; not exposed.
- **`private`:** RLS helpers, pending migration 007.

| Table | Key | Purpose / notable constraints |
|---|---|---|
| cities | city | NBC zone check, 12 temperatures (array length check), PV yield 800-2200 |
| tariff_states, tariff_slabs | state; identity | slabs with category bands; `slab_to > slab_from` |
| emission_factors | fuel | CEA v20 grid 0.727, LPG 0.227, PNG 0.202, DG 0.89 kg/kWh |
| subsidy_rules, finance_products, appliances, retrofit_catalogue, zone_suitability, benchmarks | natural keys | reference data, loaded from CSVs by `scripts/export_reference_sql.py` |
| customers | customer_id | `auth_user_id → auth.users`, loan fields with non-negative checks, consent flags |
| homes | home_id | about 50 typed columns with enum checks; `kwh_24m real[24]`; `dwelling='apartment' or floor='top'`; PV only with roof access (synthetic) |
| retrofit_events, sales, memory | text ids with defaults | FKs to homes and customers with cascade |
| home_scores | home_id | score 0-100, band enum, 7 sub-scores, package savings, engine + version |
| advisor_logs, telegram_links, bill_uploads, model_registry | identity / natural | operations; `telegram_links` and `bill_uploads` are service-role only |
| `meter_readings` (view, security_invoker) | n/a | 24 readings per home, unnested; 1.02 M rows |

- **Indexes:** every FK; `homes(zone, dwelling_type)`, `homes(city)`, `home_scores(band)`, `home_scores(improvement_potential_pct desc)`, `advisor_logs(created_at desc)`.
- **Current contents:** 50,000 homes, 50,000 customers, 9,200 retrofit events, 12,237 sales, 5,519 memory items, 50,000 scores. Database size 64 MB of the 500 MB free tier.

### 3.8 Offline jobs
| Job | Command | Output |
|---|---|---|
| Generate data | `scripts/generate_data.py --n 50000 --seed 42` | `data/generated/{homes,customers,retrofit_events,sales,memory,truth,home_scores}.parquet`, `benchmarks.csv`, `manifest.json` |
| Train | `python -m greenghar.ml.train` | `models/*`, `reports/eval_report.json` |
| LLM eval | `scripts/llm_eval.py [--llm]` | `reports/llm_eval.json` |
| Bias | `scripts/bias_report.py` | `reports/bias_report.json` |
| DB generate | `select synth.generate(start, n, 0.42); select gg.rescore(12500);` | Supabase rows |
| DB load | `scripts/push_to_supabase.py` (COPY, upsert-safe) | Python population in Supabase |
| DB rescore | `scripts/rescore_supabase.py --batch 500` | improvement potential and package columns |

---

## 4. Integration matrix and inputs

### 4.1 Ingested inputs
| Input | Channel | Format | Validation |
|---|---|---|---|
| Home survey / profile | `POST /homes` | `Home` JSON | Pydantic ranges and enums; city must exist; houses forced to `floor=top` |
| Monthly units | inside `Home.monthly_kwh` | 12 floats or nulls | length 12; outliers excluded at use |
| Bill photo / PDF image | `POST /bills/parse`, Telegram photo | JPEG/PNG ≤ 8 MB | OCR JSON validated; implausible months dropped with a warning |
| Voice note | `POST /speech/transcribe`, Telegram voice | OGG/Opus, MP3, M4A, WAV ≤ 25 MB | provider errors → 503 |
| Chat message | `POST /advisor/chat`, Telegram text | 1-2,000 chars | language detected |
| What-if | `POST /homes/{id}/scenario` | retrofit ids + params (`pv_kw` 0.5-10, `ac_setpoint_c` 18-30) | unknown ids → 422 |
| Finance request | `POST /homes/{id}/finance` | retrofits, params, down payment ≥ 0 | n/a |
| Memory item | `POST /homes/{id}/memory` | kind / key / value | kind enum |
| Telegram update | `POST /telegram/webhook` | Bot API Update JSON | `X-Telegram-Bot-Api-Secret-Token` |
| Smart-meter / discom data (Phase 2) | batch import | 15-min or daily kWh | appended to `kwh_24m` / readings |
| BBPS bill-payment history (Phase 2) | lender batch | amount per month | converted to units via the tariff inverse |

### 4.2 Third-party APIs and services
| Service | Purpose | Protocol | Auth | Free limit (Oct 2026) |
|---|---|---|---|---|
| Supabase | Postgres, Auth, REST (PostgREST) | HTTPS REST; Postgres wire for scripts | service-role key (server); JWT (clients) | 500 MB DB, 50k MAU, 2 projects |
| NVIDIA NIM (build.nvidia.com) | primary LLM (`nvidia/nemotron-3.5-lightning-30b-a3b`, streamed, thinking on; reasoning is discarded, only the final answer is verified and shown), Whisper fallback | HTTPS, OpenAI-compatible | Bearer `NVIDIA_API_KEY` | ~40 req/min |
| NVIDIA Magpie TTS | spoken replies (Hindi supported) | gRPC (Riva) to `grpc.nvcf.nvidia.com:443` | Bearer + `function-id` metadata | same key |
| Groq | LLM fallback (`openai/gpt-oss-120b`), Whisper large-v3 STT | HTTPS, OpenAI-compatible | Bearer `GROQ_API_KEY` | 30 req/min, 1,000/day; Whisper 2,000/day |
| Google Gemini | bill-photo OCR (Flash) | HTTPS REST `generateContent` | `key` query parameter | free Flash tier |
| Telegram Bot API | chat channel | HTTPS webhook + REST | bot token in URL; webhook secret header | free |
| edge-tts | TTS fallback | WebSocket (library) | none | free |
| Tesseract | OCR fallback | local binary | n/a | n/a |

### 4.3 Inter-service communication
- Inside the service, everything is in-process function calls on typed Pydantic objects. There is no message bus.
- Outbound calls are synchronous with timeouts (LLM 25 s, STT 60 s, OCR 60 s, Supabase 15 s). Failure moves to the next provider in the chain.
- Offline jobs talk to Supabase over PostgREST (`rescore_supabase.py`) or the Postgres wire protocol (`push_to_supabase.py`, COPY).
- **Phase 2:** bill OCR and voice processing move to a job queue (see 6.3) so Telegram webhooks return within 1 s.

---

## 5. API and interface specifications

### 5.1 Protocols
- REST over HTTPS with JSON (UTF-8), described by an OpenAPI 3.1 spec served at `/openapi.json` and `/docs` (static copy in `docs/openapi.json`).
- Multipart for file uploads.
- Webhook (inbound) for Telegram.

### 5.2 Core endpoints (33 routes)
| Method & path | Screen | Request | Response (abridged) |
|---|---|---|---|
| `GET /health` | ops | n/a | `{status, version, repo, cities, models{energy_hybrid, ranker, value_hedonic}}` |
| `POST /homes` | onboarding | `Home` minus `home_id` | 201 `{home, score}` |
| `GET /homes/{id}` | n/a | n/a | `Home` |
| `GET /homes/{id}/score` | 1 | n/a | `ScoreResult` |
| `GET /homes/{id}/plan` | 2 | n/a | `{home_id, constraints, recommendations[Recommendation + over_budget?], estimated}` |
| `POST /homes/{id}/scenario` | 3 | `{retrofits:[id], params:{pv_kw?, ac_setpoint_c?}}` | `{baseline, after, per_fuel_saving_kwh, saving_inr_year, co2_saving_kg_year, improvement_potential_pct, score_before, score_after, steps[], refused[], value, data_method}` |
| `GET /homes/{id}/value?retrofits=` | 4 | n/a | `{available, current_value_inr, current_value_range_inr, uplift_pct, uplift_range_pct, label, caveat}` or `{available:false, reason}` |
| `POST /homes/{id}/finance` | 4 | `{retrofits, params, down_payment_inr}` | `{gross_cost_inr, subsidy_inr, net_cost_inr, loans[], total_emi_inr_month, bill_saving_inr_month, emi_covered_by_saving, simple_payback_years, savings_25yr_inr, pivot_note}` |
| `GET /homes/{id}/solar?kw=` | 4 | n/a | `{quote{kw, annual_generation_kwh, gross_cost_inr, central_subsidy_inr, state_topup_inr, net_cost_inr}, subsidy{eligible, steps, documents}}` |
| `GET /homes/{id}/subsidy-application` | 4 | n/a | pre-filled PM Surya Ghar draft, or 409 `not_eligible` |
| `GET /homes/{id}/roadmap?budget_inr=&years=&objective=` | 4 | n/a | `{years[{year, items[], spend_inr, saving_inr_year, co2_kg_year}], not_scheduled[]}` |
| `GET /homes/{id}/heatwave` | 6 | n/a | `{ac_hours_apr_jun, measures[{retrofit_id, indoor_peak_drop_c[lo,hi], ac_hours_avoided_apr_jun, cost_inr}]}` |
| `GET /homes/{id}/journey` | 6 | n/a | `{completed_retrofits[], memory[], plan}` |
| `POST /homes/{id}/memory` | 6 | `{kind, key, value}` | 201 `{memory_item, what_changed{changes[]}}` |
| `POST /advisor/chat` | 5 | `{home_id, message, language?, use_llm}` | `{answer, language, provider, model, tool_calls[], grounding{total, verified, unsupported[], grounded, badge}, caveats, latency_s, usage, cached}` |
| `POST /bills/parse` | 5 | multipart `file` | `{monthly_kwh[12], months_found, consumer_number_masked, sanctioned_load_kw, warnings[], provider}` |
| `POST /speech/transcribe?language=` | 5 | multipart `file` | `{text, language, provider}` |
| `POST /speech/tts` | 5 | `{text ≤1500, language}` | audio bytes (`X-TTS-Provider`) |
| `POST /telegram/webhook` | 5 | Telegram Update | `{handled, ...}` |
| `GET /portfolio/summary\|poor-homes\|ranking\|map\|targets\|rwa-leads` | 7 | `X-API-Key` (analyst); filters `city`, `state`, `limit` | aggregates and lists |
| `POST /portfolio/rescore` | 7 | `X-API-Key` (admin) | cache clear / job trigger |
| `GET /lab/metrics\|scenarios\|factors\|data-card` | 8 | n/a | eval report, live checks, factor table, data card |
| `GET /reference/cities\|retrofits\|tariffs/{state}` | n/a | n/a | reference data |

**`ScoreResult` schema:**
```json
{"home_id":"H000011","score":16,"band":"Very poor","raw_score":15.622,
 "components":[{"component":"energy_efficiency","weight":0.25,"score":0.0,"contribution":0.0,
                "why":"No BEE label; modelled rating is 1.74x the warm-humid benchmark","estimated":true}, "... 7 items"],
 "confidence":"medium","confidence_reasons":["4 of 12 months missing; annualised with seasonal weights"],
 "warnings":[],"annual_grid_kwh":8050.6,"annual_grid_kwh_estimated":true,"intensity_kwh_m2":...}
```

---

## 6. Infrastructure, DevOps and deployment

### 6.1 Hosting
| Environment | Hosting | Notes |
|---|---|---|
| Hackathon demo | Hugging Face Spaces (Docker, free CPU) or Render free web service | `Dockerfile` builds data and models if absent; port 8000; healthcheck `/health` |
| Pilot | Google Cloud Run (asia-south1), min 1 / max 10 instances, 1 vCPU / 2 GiB, concurrency 40 | same image; secrets in Secret Manager |
| Database | Supabase `green-ghar`, ap-south-1 (Mumbai) | free tier now; Pro for the pilot (daily backups, PITR) |
| Frontend | Vercel (dashboard), Telegram Mini App served from Vercel | n/a |

### 6.2 Caching and performance
| Cache | Pattern | Key / TTL |
|---|---|---|
| Reference tables, models, bootstrap boosters | load-once (`lru_cache`) | process lifetime; reloaded on deploy |
| Advisor replies | read-through LRU (512) | sha256(home state, message, language, use_llm); evicts oldest; Phase 2: Upstash Redis, TTL 24 h |
| Portfolio frame | load-once, `POST /portfolio/rescore` clears it | Phase 2: materialised views refreshed after rescoring |
| Supabase reads | none (single-row lookups at ~10 ms) | Phase 2: cache-aside in Redis, TTL 10 min, invalidated on `put_home` |

**Measured latency** (in-process test client, 2 vCPU, warm, p50 of 7 calls):

| Endpoint | p50 |
|---|---|
| score, metered home | 4 ms |
| score, ML-predicted home | 35 ms |
| plan, all 15 retrofits costed incrementally | 186 ms |
| what-if with value range | 120 ms |
| finance | 5 ms |
| chat (template path) | 9 ms |
| portfolio summary over 25k loans | 19 ms |

The first request per process pays a one-time model and Parquet load of about 120-215 ms.

### 6.3 Background jobs and workers
- **Now:** cron-style scripts (see 3.8).
- **Pilot:**
  - **Supabase `pg_cron`:** `select gg.rescore(5000)` every 15 minutes for new homes.
  - **Cloud Scheduler → Cloud Run job:** `rescore_supabase.py` nightly at 02:00 IST; `llm_eval.py --llm` and `bias_report.py` weekly; annual summer re-score and heatwave push every 1 March.
- **Phase 2 queue:** Telegram photo and voice handling and OCR move to a Postgres-backed queue (`jobs` table with `for update skip locked`) worked by a separate Cloud Run worker. The webhook acknowledges within 1 s and the bot replies asynchronously.

### 6.4 CI/CD
GitHub Actions on push or PR:
1. `pip install -r requirements.txt`
2. `make data` (cached by the hash of `data/reference/*` and the generator)
3. `make train`
4. `make test`: 58 tests covering monotonicity, hidden scenarios, leakage, SQL parity, API latency and error format.
5. `make eval`. The build fails if groundedness < 0.9 or unsupported claims > 0.05.
6. `docker build`, then push to Artifact Registry.
7. Deploy to Cloud Run staging and smoke-test `/health` and `/lab/scenarios`.
8. Manual approval, then production with a traffic split of 10%, then 100%.

Database migrations in `supabase/migrations` are applied by `supabase db push` in the pipeline. Destructive migrations need a reviewer.

---

## 7. Security, compliance and observability

### 7.1 Authentication and authorisation
- **Customers:** Supabase Auth (username + password; the username maps to a private, never-mailed address), Supabase-signed JWT access tokens with 1-hour expiry and refresh-token rotation. `customers.auth_user_id` links the login. RLS policies give each user only their own customer, homes, scores, events and memory.
- **Analysts:** JWT `app_metadata.app_role = 'analyst'` (RLS read across the portfolio) and `X-API-Key` on `/portfolio/*`. Keys are compared in constant time.
- **Admins:** `GG_ADMIN_KEYS` on `/portfolio/rescore`.
- **Prod hardening (Phase 1):** verify the Supabase JWT in FastAPI (JWKS) and pass the user through to RLS by calling PostgREST with the user's token rather than the service role for customer routes.
- **Telegram:** webhook secret token. A chat is bound to a home on first contact, and `telegram_links` is service-role only.
- **Database:**
  - RLS on all 20 tables. Reference tables are public read-only.
  - `gg` and `synth` are not exposed; `security definer` helpers have `search_path=''`.
  - The pending migration 007 moves the RLS helpers to a `private` schema.

### 7.2 Data security
- **In transit:** TLS 1.2+ to clients, Supabase and every provider. gRPC to NVIDIA uses TLS.
- **At rest:** Supabase AES-256 disk encryption and encrypted backups.
- **Secrets:** environment or Secret Manager only; never logged; the service-role key never reaches clients.
- **PII minimisation:** consumer numbers are masked at parse; no names or addresses are stored (synthetic ids). Bill images are kept only in a private Storage bucket (Phase 1) with a 90-day retention policy.
- **Consent (DPDP Act):** `consent_energy_data` gates processing; `consent_marketing` gates the green-finance target list (enforced in `portfolio.green_finance_targets`).

### 7.3 Monitoring and observability
- **Logs:** structured JSON per request (`request_id`, method, path, status, `duration_ms`) to stdout, which reaches Cloud Logging. Errors log with stack traces; clients only see the request id.
- **Metrics (Phase 1):** Prometheus via `prometheus-fastapi-instrumentator`, covering RED per route, provider error and fallback rates, verifier rejection rate and LLM tokens per query. Dashboards in Grafana Cloud (free).
- **Tracing (Phase 1):** OpenTelemetry FastAPI and httpx instrumentation exported to Grafana Tempo; `X-Request-ID` is propagated.
- **LLM observability:** `advisor_logs` table (question, provider, model, grounded, figures verified/total, latency, tokens); Langfuse for prompt traces.
- **Model monitoring:** weekly `llm_eval.py` and `bias_report.py`; data-drift check on `home_scores` distribution by zone; `model_registry` stores version hashes and metrics.
- **Alerts:**
  - 5xx rate > 1% for 5 minutes
  - what-if p95 > 300 ms
  - verifier fallback rate > 20%
  - provider 429 rate > 10%
  - Supabase database > 400 MB

---

## 8. Implementation roadmap and progress

### 8.1 Completed
- Reference data: 43 cities (zones, temperatures, PV yield, prices), 24 state tariffs with slabs and free-unit schemes, CEA factors, PM Surya Ghar rules, finance products, appliance tables, 15-item retrofit catalogue, zone suitability. Exported to SQL.
- Engines: physics, score (monotonic, 7 fixed weights), slab tariff with net metering, plan and what-if (sequential, per-fuel, refusals), solar sizing, finance (EMI vs saving, 25-year), roadmap knapsack, heatwave, portfolio (financed emissions, targets, RWA leads).
- Synthetic population: 50,000 homes in Python (H ids) and 50,000 in Supabase (HD ids), with customers, loans, retrofits, sales, memory and hidden truth. Data card written.
- ML, test set:
  - energy hybrid MAE 384 vs 944 baseline;
  - LambdaRank NDCG@5 0.986 vs 0.881 popularity;
  - hedonic value MAPE 6.7% vs 11.4%, 80% conformal coverage 81.6%;
  - bias gap 0.9 MAPE points.
- LLM layer: 8 tools, NIM → Groq → template chain, numeric verifier, EN/HI templates, memory. Eval on 180 prompts: groundedness 1.00, unsupported 0.00, accuracy 0.99; adversarial run caught 95 of 95 injected figures.
- Channels: Whisper STT, Magpie / edge TTS, Gemini / Tesseract bill OCR, Telegram webhook bot (start, demo, photo, voice, text, buttons, Mini App).
- API: 33 routes, error envelope, request ids, timing, OpenAPI.
- Supabase `green-ghar`: 20 tables + view, RLS, SQL engine (`gg.energy`, `gg.score`, `gg.rescore`), in-DB generator, advisor fixes (search_path, FK indexes).
- Tests: 58 passing (Hypothesis monotonicity, 5 hidden scenarios + worked example, leakage, SQL parity, API latency and errors, Telegram flow, OCR validation).

### 8.2 Immediate next steps (Phase 1, before the pilot)
1. Apply `007_move_rls_helpers_PENDING.sql` (owner confirmation).
2. Supabase-native portfolio: SQL views over `home_scores ⨝ customers` (summary, ranking, map), with the API reading them when `GG_REPO=supabase`.
3. Write every advisor reply to `advisor_logs`; persist Telegram sessions in `telegram_links`; store bill images in a private Storage bucket and record them in `bill_uploads`.
4. Verify Supabase JWTs in FastAPI and forward user tokens to PostgREST for customer routes; set `GG_ENV=prod` with API keys.
5. Run `rescore_supabase.py` to fill improvement potential for the HD population; schedule `pg_cron` for `gg.rescore`.
6. Add API keys (NVIDIA, Groq, Gemini, Telegram), run `llm_eval.py --llm`, and record the live groundedness in the Model Lab.
7. Deploy to Hugging Face Spaces or Cloud Run; register the Telegram webhook; point the dashboard at the API.

### 8.3 Future backlog
**Phase 2: scale and data**
- Discom smart-meter APIs (15-minute data) and BBPS ingestion through the Account Aggregator consent framework.
- Job queue for OCR and voice.
- Redis cache-aside.
- Materialised portfolio views.
- Load test to 200 req/s.
- More languages in templates (Tamil, Marathi, Telugu).
- Satellite roof-area estimation (Open Buildings polygons in PostGIS).
- PVWatts and Open-Meteo integration for per-home yield and weather normalisation.
- Neutral MNRE-installer marketplace with post-install meter verification.

**Phase 3: product and platform**
- Split the provider adapters into a separate "AI gateway" service if LLM traffic dominates.
- Retrain on pilot data with real verified savings; double-ML causal estimate of the value premium.
- RWA pooled-loan workflow.
- Annual summer check-up notifications.
- RBI climate-risk disclosure export (financed-emissions report).
- Multi-lender tenancy (a `lender_id` column with RLS on every table).


## Addendum (10 Oct 2026): real data layer, auth and persistence wired
- **Real public-data layer.** Schema `realdata` (migrations 012-019) is loaded by the database itself through the `http` extension. Sources: Census 2011, NFHS-5, Open-Meteo/ERA5 daily weather, NASA POWER, OWID, WRI power plants and World Bank WDI, 80,811 rows in total. It is served through service-role RPCs: `real_sources`, `real_state_profile`, `real_city_climate`, `real_home_weather` and `real_synth_vs_real`.
- **Auth.** `greenghar/api/auth.py` verifies Supabase JWTs (JWKS or HS256) on every home route. Customers can reach only their own homes; the analyst role reaches any home and the portfolio. Tokens are mandatory when `GG_ENV=prod`.
- **Persistence.** Advisor turns from the API and Telegram go to `advisor_logs`. Telegram sessions go to `telegram_links`. Bills go to the private `bills` bucket plus `bill_uploads`. Runtime homes are stored with their owner. Locally, the same writes go to `data/runtime/*.jsonl`.
- **Portfolio.** In Supabase mode the portfolio is served from Postgres RPCs (migration 010).
- **Rate limiting.** A sliding-window limiter covers chat, OCR and speech.
- **Tests.** 70 automated tests, including SQL ↔ Python parity for both the score and the package engine.
