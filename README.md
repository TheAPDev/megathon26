# Green Ghar Score: backend

Home-energy score, retrofit plan, what-if engine, finance (EMI vs savings, PM Surya Ghar), a grounded multilingual AI advisor, a Telegram bot, a lender portfolio and a model lab, all built for Indian homes.

> Every number comes from a documented model, every sentence is checked against those numbers, and every tricky case the judges listed is tested.

## Windows quick start
1. `setup.bat`: creates `.venv` and installs the backend (Python 3.11 or 3.12).
2. `connect_supabase.bat`: paste the Supabase service-role key once. It tests the connection and switches the API to the live database. Skip this step to use the bundled local dataset.
3. `run.bat`: opens http://localhost:8000/app/

`.env` already points at the `green-ghar` Supabase project (see `supabase/PROJECT.md`). Keep it private.

## Quick start
```bash
pip install -r requirements.txt
make data      # 50,000-home synthetic population + benchmarks + portfolio scores (~3 min, seed 42)
make train     # energy / ranker / value models + reports/eval_report.json
make eval      # LLM groundedness eval -> reports/llm_eval.json
make test      # 76 tests: monotonicity, hidden scenarios, leakage, SQL parity (score + package), API, auth, persistence, real data
make serve     # http://localhost:8000/docs
```
Or `cp .env.example .env && docker compose up --build`.

The zip already contains generated data, trained models and reports, so `make serve` works immediately.

## Web app (5 screens + 3 differentiators)
```bash
make web       # build frontend/dist once (Node 20+)
make serve     # open http://localhost:8000/app  (demo home H000011; lender view at /app/portfolio)
make web-test  # typecheck, lint, unit/component tests      make e2e  # Playwright against a real backend
```
Screens: Dashboard, Retrofit studio, Paisa, AI Saathi and Lender portfolio. Differentiators: Bill photo → score (with a Telegram handoff), the verified-number advisor, and Garmi mode (real weather). The integration map, every design element that was not wired and why, the config, and the test results are in `docs/frontend_integration.md`.

## What's inside
| Path | What |
|---|---|
| `greenghar/engine/` | physics, score, tariff (slab-aware), plan & what-if, solar, finance, roadmap optimiser, heatwave, portfolio |
| `greenghar/ml/` | features (leakage guard), training & evaluation, runtime inference |
| `greenghar/llm/` | tool specs, orchestrator (NVIDIA Nemotron 3.5 Lightning → Groq → template), project knowledge card + few-shot examples built from the dataset, numeric verifier, templates (EN/HI) |
| `greenghar/speech/`, `ocr/`, `bot/` | Whisper STT, Magpie / edge TTS, Gemini bill OCR, Telegram webhook bot |
| `greenghar/api/` | FastAPI app; 38 endpoints for the 8 screens, Supabase-JWT auth (`auth.py`), rate limiting |
| `greenghar/realdata.py` | offline part of the real public-data layer (Census 2011 + NFHS-5 state profiles, calibration) |
| `greenghar/synth/` | synthetic population generator (Python) |
| `greenghar/lab.py` | hidden-scenario, monotonicity and worked-example checks (also served live at `/lab/scenarios`) |
| `supabase/migrations/` | 001-019: schema, RLS, reference data, SQL score and package engine, in-DB generator, portfolio RPCs, bills bucket, real public-data layer |
| `data/reference/` | versioned CSVs: 43 cities, 24 state tariffs, CEA factors, subsidies, retrofit catalogue, appliances |
| `frontend/` | React + TypeScript web app (Vite), served by the API at `/app` |
| `docs/` | data card, model card, responsible-AI note, OpenAPI spec, system architecture document |
| `reports/` | eval report, LLM eval, bias report |

## Screens → endpoints
| Screen | Endpoints |
|---|---|
| 1 My Ghar Score | `GET /homes/{id}/score` |
| 2 Retrofit Plan | `GET /homes/{id}/plan` |
| 3 What-If Studio | `POST /homes/{id}/scenario` (~120 ms) |
| 4 Paisa: Value & Finance | `GET /homes/{id}/value`, `POST /homes/{id}/finance`, `GET /homes/{id}/solar`, `GET /homes/{id}/subsidy-application`, `GET /homes/{id}/roadmap` |
| 5 AI Saathi | `POST /advisor/chat`, `POST /speech/transcribe`, `POST /speech/tts`, `POST /bills/parse`, `POST /telegram/webhook` |
| 6 Memory & Journey | `GET /homes/{id}/journey`, `POST /homes/{id}/memory`, `GET /homes/{id}/heatwave` |
| 7 Lender Portfolio | `GET /portfolio/summary`, `/poor-homes`, `/ranking`, `/map`, `/targets`, `/rwa-leads` (X-API-Key) |
| 8 Model Lab | `GET /lab/metrics`, `/lab/scenarios`, `/lab/factors`, `/lab/data-card` |
| Real data | `GET /reference/real/sources`, `/reference/real/state/{state}`, `/reference/real/city/{city}`, `/reference/real/calibration`, `GET /homes/{id}/weather-signature` |

## Supabase (project `green-ghar`, ap-south-1)
- **Contents:** 20 tables plus a readings view, with RLS on every table. It holds 50,000 homes (1.02M monthly readings), 50,000 customers, 9,200 retrofits, 12,237 sales, 5,519 memory items and 50,000 scores.
- **SQL engine:** `select * from gg.score(h) from public.homes h where home_id = 'HD000007';` matches the Python engine exactly (`tests/test_sql_parity.py`).
- **Run the API on Supabase:** `GG_REPO=supabase` with `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY`.
- **Optional:** `scripts/push_to_supabase.py` adds the Python population (H/C ids); `scripts/rescore_supabase.py` fills in package savings and improvement potential.
- **Pending (owner action):** paste `supabase/migrations/007_move_rls_helpers_PENDING.sql` into the Supabase SQL editor. It moves the RLS helper functions out of the public API schema; the tooling blocks drop statements, so it has to be run by hand.
- **Portfolio in Postgres:** `GG_REPO=supabase` serves `/portfolio/*` from SQL RPCs (`portfolio_summary`, ..., migration 010).

## Real public data (schema `realdata`, migrations 012-019)
The database fetches the public files itself (`http` extension), keeps the raw copy for provenance and parses it in SQL. 80,811 real rows from 9 sources:

| Source | Rows | Used for |
|---|---|---|
| Census of India 2011, 640 districts (118 fields kept in `attrs`) | 640 | ownership, household size, LPG, assets, income (power-parity) per state |
| NFHS-5 state fact sheets (132 indicators, urban/rural/total) | 4,847 | electricity access, clean cooking, sanitation, internet use |
| NFHS-5 district fact sheets (phase 1) | 35,464 | district drill-down |
| Open-Meteo / ERA5 daily weather, 43 cities, Oct 2024-Sep 2026 | 31,390 | **real** CDD24, heatwave days, humid-heat days, solar per billing month |
| NASA POWER monthly climatology, 43 cities, 10 parameters | 5,590 | irradiance cross-check of PV yields (engine within ~5%) |
| OWID energy + CO2, India yearly | 301 | grid carbon intensity check (705 g/kWh in 2024 vs CEA 0.727 used) |
| WRI Global Power Plant Database, India | 1,589 | generation fleet near each city/state |
| World Bank WDI, India (24 indicators) | 990 | access, T&D losses, urbanisation, lending rate, PM2.5 |

Derived: `realdata.state_profile`, `realdata.synth_vs_real_state` (calibration report: synthetic homes vs Census/NFHS), `realdata.city_climate_check`, and `realdata.home_weather_signature` (42,524 homes: kWh per real cooling degree-day and weather-normalised annual use, by OLS over 24 billing months; mean R² 0.55).
Refresh: `select realdata.load_open_meteo('2024-10-01','2026-09-30',10);` (repeat each minute until 0), `select realdata.load_nasa_power();`, `select realdata.load_worldbank();`. Offline mode reads `data/real/raw/` (`python scripts/fetch_real_data.py`).

## Auth, persistence, limits
- **Login:** username + password accounts on Supabase Auth (`POST /auth/signup`, sign-in in the browser); the API verifies the JWTs (JWKS, or `SUPABASE_JWT_SECRET` for HS256). Customers reach only their own homes; `app_metadata.app_role = 'analyst'` reaches any home and the portfolio. `GG_ENV=prod` makes tokens mandatory; dev stays open for the demo.
- **Durable writes:** homes (with owner), memory, advisor logs (every turn with its grounding result, API and Telegram), Telegram chat links and bill images. They go to Supabase tables and the private `bills` bucket, or to `data/runtime/*.jsonl` locally.
- **Rate limit:** `GG_RATE_LIMIT_PER_MIN` (default 30) on chat, OCR and speech.

## Keys (all free tiers)
`NVIDIA_API_KEY`, `GROQ_API_KEY`, `GEMINI_API_KEY`, `TELEGRAM_BOT_TOKEN`, `NVIDIA_TTS_FUNCTION_ID`. Everything degrades gracefully: without keys the advisor uses grounded templates, and STT, TTS and OCR return a clear 503.

## Headline results (held-out test)
- **Energy model:** MAE 384 kWh vs 944 for the baseline (−59%).
- **Ranker:** NDCG@5 0.986 vs 0.881 for popularity. 0% infeasible recommendations.
- **Value model:** MAPE 6.7% vs 11.4%. The 80% conformal interval covers 81.6%.
- **Advisor:** groundedness 100% and factual accuracy 99% (templates). The adversarial test caught 95 of 95 injected figures.
- **Checks:** 7 of 7 hidden scenarios pass. Monotonicity: 0 failures in 16,704 checks.


## AI Saathi model and "training" on the backend dataset

The advisor uses `nvidia/nemotron-3.5-lightning-30b-a3b` through NVIDIA's OpenAI-compatible endpoint (thinking on, 16384-token
budget, streamed). Keys live only in the server `.env` / `local.env`. Fine-tuning the hosted model is not possible through that
API, so the project adapts it three ways instead, all built from the backend data:

1. **Project prompt** (`llm/orchestrator.py`, `llm/knowledge.py`): India context, the seven score components and bands (read from the
   engine, so they cannot drift), refusal rules for infeasible retrofits, Hindi/Hinglish handling, the no-invented-numbers rule.
2. **Few-shot examples** (`data/llm/fewshot.json`): three real homes, real tool output, verified answers, injected into every call.
3. **SFT dataset** (`python scripts/build_llm_dataset.py`): 1,500 chat-format examples from the train split of `homes.parquet`
   (`data/llm/sft_train.jsonl`, `sft_val.jsonl`), every answer checked by the numeric verifier. Use it with NVIDIA NeMo Customizer or
   your own GPU run if you want real weight updates. `--distill` lets the live model write the answers (verified ones only).

Measure with `python scripts/llm_eval.py --llm` on held-out homes (the dataset builder never touches them).


## Deploy to Vercel (CLI, no GitHub needed)

From this folder on your laptop: `npm i -g vercel`, `vercel login`, `vercel link`, then add the environment variables below
(`vercel env add NAME production`, paste each value) and run `vercel --prod`.

| Variable | Value |
| --- | --- |
| `GG_ENV` | `prod` (customer routes then require a login token; leave `dev` only for private demos) |
| `GG_REPO`, `GG_LOGIN` | `supabase`, `on` |
| `GG_RUNTIME_DIR` | `/tmp/gg` (Vercel's disk is read-only except /tmp) |
| `GG_ANALYST_KEYS`, `GG_ADMIN_KEYS` | your own long random strings (lender portfolio and admin routes) |
| `GG_LINK_SECRET` | any long random string |
| `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY` | from `local.env` |
| `NVIDIA_API_KEY`, `GROQ_API_KEY`, `GEMINI_API_KEY`, `TELEGRAM_BOT_TOKEN` | from `local.env` |

After the first deploy, register the Telegram webhook once:
`https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://<your-app>.vercel.app/telegram/webhook` (set `TELEGRAM_WEBHOOK_SECRET` as well).
`vercel.json`, `api/index.py` and `.vercelignore` are already set up. The Python bundle (pandas, scikit-learn, LightGBM, models) is large;
if Vercel rejects its size or cold starts are too slow, deploy the included `Dockerfile` on Render, Railway or Fly.io instead.
