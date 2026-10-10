# Green Ghar web app: integration report

The web app lives in `frontend/`. It uses React 18, TypeScript (strict), Vite 5, TanStack Query 5 and Zustand, with hand-built SVG charts and no chart library.

- It talks only to the FastAPI backend. The browser never queries Supabase tables directly.
- In production, the API serves the built app at `/app` from the same origin, so no CORS setup is needed.
- In development, Vite runs on :5173 and proxies the API paths to :8000.

## Architecture

```
Browser (React SPA, /app)
  └─ src/api/client.ts   one fetch wrapper: X-Request-ID, 30 s timeout, GET-only retries (2, backoff),
  │                      never retries writes, parses {"error":{code,message,details,request_id}},
  │                      single token refresh + replay on 401, 429 -> retry_after_s countdown
  ├─ src/api/endpoints.ts  one function per backend route (38 routes; 31 used by the UI)
  ├─ src/api/hooks.ts      TanStack Query keys per home; writes cancel + invalidate ['home', id]
  ├─ src/auth/auth.ts      Supabase username + password (sign-in / sign-up) when /config publishes url + anon key; else demo mode
  ├─ src/state/session.ts  active home, recent homes, language (persisted, storage-failure safe)
  └─ src/screens/*         5 screens + 2 differentiator screens, lazy-loaded per route
FastAPI (greenghar/api) ── engine, ML, LLM verifier, OCR, speech, repos (local JSONL or Supabase)
```

## Screens, endpoints and support status

| Screen (design) | Route | Backend used | Status |
|---|---|---|---|
| 1 Dashboard / My Ghar Score | `/app/` | `GET /homes/{id}`, `/score`, `/plan`, `POST /scenario` (full plan), `/weather-signature` | Supported |
| 2 Retrofit plan & what-if studio | `/app/studio?r=…&sp=…&pv=…` | `/plan`, `POST /scenario` (debounced 250 ms, abortable), `POST /memory`, `/reference/retrofits` | Supported |
| 3 Paisa: value, finance & solar | `/app/paisa?r=…` | `POST /finance`, `/value`, `/solar?kw=`, `/subsidy-application`, `/roadmap` | Supported |
| 4 AI Saathi: advisor, voice & memory | `/app/saathi` | `POST /advisor/chat`, `/speech/transcribe`, `/speech/tts`, `/journey`, `POST /memory` | Supported (voice needs Groq/NVIDIA keys) |
| 5 Lender portfolio | `/app/portfolio` | `/portfolio/summary`, `/map`, `/poor-homes`, `/ranking`, `/targets`, `/rwa-leads`, `/homes/{id}/score` + `/scenario` | Supported |
| D1 Instant bill photo to score | `/app/bill` | `POST /bills/parse` (Gemini, Tesseract fallback), `POST /homes`, `POST /bills/parse?home_id=` (stores the bill), `POST /homes/{id}/telegram-link` | Supported |
| D2 Verified-number advisor | `/app/saathi` (verification panel) | `grounding{total, verified, unsupported, badge}`, `tool_calls`, `fallback_reason` | Supported |
| D3 Garmi mode | `/app/garmi` | `/heatwave`, `/weather-signature`, `/reference/real/city/{city}` | Supported. Real-weather parts need `GG_REPO=supabase` |

### How each differentiator works

- **D1, bill photo to score.**
  - Before upload: the file type is checked, and phone photos are shrunk to 2,000 px JPEG.
  - After the bill is read: the user reviews a 12-month grid (read / typed / missing). Blank months are sent as `null`, never as 0.
  - On submit: the home is created, and the bill is stored against it afterwards, so storage is tied to that purpose.
  - If the bill reader is down (`503 ocr_unavailable`), the screen switches to manual entry.
  - "Continue on Telegram" asks the API for a signed deep link that expires in 15 minutes (`GG_LINK_SECRET`), so the home ID is never used as a credential.
- **D2, verified-number advisor.**
  - `src/lib/figures.ts` is a line-for-line port of the number extractor in `greenghar/llm/verifier.py`, with the same exemptions. A unit test pins the two together.
  - Every counted figure is highlighted green (matched to engine output) or amber (listed in `unsupported`).
  - The side panel lists each figure with its status, the engine tools used with their arguments, and links to the screen that shows the same calculation.
  - When the backend replaced an LLM draft with the checked template answer (`fallback_reason`), the reply says so.
- **D3, Garmi mode.**
  - Real cooling degree-days for 24 billing months (Open-Meteo/ERA5, loaded into Supabase) are drawn as a heat strip behind the home's own metered months.
  - A weather-normalised comparison (OLS regression of the home's bills on real CDD) is shown next to it.
  - Passive measures come from `/heatwave`, ranked by AC hours avoided.
  - In local mode, the real-weather endpoints return 404 and the screen falls back to metered months. A component test drives the screen with payloads captured from the live Supabase RPCs.

### Design elements not wired, and why

| Element in the designs | Decision |
|---|---|
| Live weather ("28 °C partly cloudy"), 5-day heatwave forecast | No forecast or current-weather endpoint exists. The app shows the latest real month from ERA5 instead, labelled with its source. |
| "City average 48" on the score card | No endpoint returns a city average. The score is placed on the band scale, and `peer_percentile` is shown when the backend provides it. |
| "Equivalent to 28 trees" | No tree factor is in the engine, so no number was invented. CO₂ is shown in kg with its CEA source. |
| Customer names, loan amounts and EMI per row in the lender view | The backend exposes customer IDs only (DPDP minimisation). The drawer shows score and package from the API. |
| "Sources" tab with MNRE/CESC links in the advisor | The verifier checks figures against engine tool outputs, not web documents. The panel lists the engine calculations used instead of external links. |
| Sidebar items Reports, Community, Compare Scenarios, Grants & Schemes | There is no backend for them. Grants are covered by the PM Surya Ghar navigator in Paisa, and comparing scenarios by the studio. |
| Stock photos | No licensed images were supplied. Retrofit icons stand in for them. |
| Full Hindi interface | The navigation and screen titles are translated (EN/हि toggle). The advisor answers in Hindi or Hinglish. Engine reason texts come from the backend in English. |

## Backend changes made for the web app (backward compatible)

| File | Change | Why |
|---|---|---|
| `greenghar/api/main.py` | `GET /config` (public, no secrets). SPA hosting at `/app` with long-cache assets. `/` redirects to the app. CORS exposes `X-Request-ID`, `Server-Timing` and `X-TTS-Provider` | Same-origin deployment, client config, error references |
| `greenghar/api/routers/homes.py` | `GET /homes` lists the signed-in customer's homes. `POST /homes/{id}/telegram-link` | Home switcher across devices; D1 Telegram handoff |
| `greenghar/api/linking.py` (new) | HMAC-signed, 15-minute deep-link tokens (≤ 64 chars) | Telegram `/start` payload without exposing home IDs |
| `greenghar/bot/telegram.py` | `/start <token>` links the chat to the home | Completes the handoff |
| `greenghar/data_access.py`, `db/supabase_repo.py` | `homes_of(sub)` | Backs `GET /homes` |
| `greenghar/memory/store.py` | `include` / `accepted` undo an exclusion; `budget_inr = 0` clears the budget | Memory is append-only; the design's × on constraint chips needed an undo |
| `tests/test_frontend_support.py` (new) | 6 tests covering the above | |

## Configuration

| Variable | Where | Purpose |
|---|---|---|
| `SUPABASE_URL`, `SUPABASE_ANON_KEY` | API env, published by `/config` | Turns on username + password sign-in (needs `GG_LOGIN=on`). Without them the app runs in demo mode |
| `SUPABASE_JWT_SECRET` (HS256 projects) or JWKS | API env | Verifies the tokens the app sends |
| `GG_ENV=prod` | API env | Tokens are required; anonymous demo mode is off |
| `TELEGRAM_BOT_USERNAME`, `GG_LINK_SECRET` | API env | Telegram deep links |
| `GG_RATE_LIMIT_PER_MIN` | API env | Chat, OCR and speech limiter (the UI shows the countdown) |
| `VITE_API_URL` | frontend build | Only if the API is on another origin (then also set `GG_CORS_ORIGINS`) |
| `GG_API_URL` | Vite dev server | Proxy target (default `http://127.0.0.1:8000`) |

## Run

```bash
make install && make web          # Python deps + build frontend/dist
make serve                        # http://localhost:8000/app  (demo home H000011)
# or develop with hot reload: make serve (terminal 1), make web-dev (terminal 2) -> http://localhost:5173/app
docker compose up --build         # multi-stage image: Node builds the app, Python serves API + app
```

## Tests (all run on 11 Oct 2026; results below are from those runs)

| Suite | Command | Result |
|---|---|---|
| Backend (pytest) | `make test` | 76 passed |
| Typecheck + lint | `make web-test` (tsc strict, eslint `--max-warnings 0`) | clean |
| Unit/component (Vitest) | `npm test` | 10 passed: verifier-parity figures, Indian formatting, API client (error envelope, retries, 401 refresh, query encoding), Garmi with live-captured real weather |
| End-to-end (Playwright, real backend) | `make e2e` | 11 passed: every screen and differentiator, constraint add/undo, OCR on a real bill image, validation, unknown-home recovery, mobile layout |
| Contract | `make contract` | 23 of 23 endpoints return every field the UI reads |

**Not executed here.** Each item below needs credentials or a network this environment doesn't have:

- **Supabase sign-in.** Accounts are `<username>@GG_USERNAME_DOMAIN` inside Supabase Auth (never mailed). Sign-up goes through `POST /auth/signup`, which creates a confirmed user with the server-side service-role key; without that key it falls back to the public sign-up endpoint, which works only if "Confirm email" is off in Supabase. Verified here with mocked Supabase responses; not exercised against the live project from the build sandbox. There is no password reset by email, because usernames have no inbox.
- **API in `GG_REPO=supabase` mode.** The Supabase host is blocked from this sandbox. The RPCs themselves were verified by running them in SQL as `service_role`.
- **Live LLM, STT and TTS calls.** They need provider keys. Without keys the UI shows the template answer and hides voice, as designed.

## Performance and security notes

**Performance**
- Routes are code-split. The first load is about 88 kB of gzipped JavaScript: 51 kB React, 24 kB app shell and dashboard, 13 kB TanStack Query. Each other screen is 3–8 kB gzipped and loads on demand.
- Supabase JS loads only when auth is configured, and fonts are self-hosted.
- Reference data is cached forever. Home queries are cached for 5 minutes.
- Scenario, finance and solar queries are keyed by inputs, so going back to a combination you already tried is instant.
- Inputs are debounced (250–400 ms) and scenario requests are abortable.
- Portfolio tabs load lazily, with server limits plus "load more" and a scrolling table with a sticky header.

**Security**
- The frontend holds no secrets.
- There is no `dangerouslySetInnerHTML`; all API text renders as text.
- External links use `noopener`.
- CSV export neutralises formula injection.
- Writes are never retried automatically.
- Supabase-js stores the session in localStorage, the library default. Moving it to httpOnly cookies would need a backend session endpoint.
- **Known gap:** the rate limiter is per process, so put a gateway limit in front when scaling out.
