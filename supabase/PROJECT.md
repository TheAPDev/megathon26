# Supabase project

| | |
|---|---|
| Project | `green-ghar` |
| Ref | `rnsirfybfxfjnlhteurm` |
| Region | ap-south-1 (Mumbai), Postgres 17 |
| API URL | https://rnsirfybfxfjnlhteurm.supabase.co |
| Dashboard | https://supabase.com/dashboard/project/rnsirfybfxfjnlhteurm |
| Status on 11 Oct 2026 | ACTIVE_HEALTHY |

## What's in it
- `public`: 50,000 homes (with 24-month readings), customers, scores, retrofits, sales, memory, advisor logs, Telegram links and bill uploads, plus the reference tables. RLS is on everywhere.
- `gg`: SQL port of the score and package engine (Python parity is tested in `tests/test_sql_parity.py`).
- `synth`: the in-database generator.
- `realdata`: 80,811 rows of real public data from Census 2011, NFHS-5, Open-Meteo, NASA POWER, OWID, WRI and the World Bank.
- Storage: a private `bills` bucket.
- Migrations 001-019 are applied, except `007_move_rls_helpers_PENDING.sql`. Paste that one into the SQL editor yourself.

## Keeping the connection
1. `.env` already holds `SUPABASE_URL` and the public anon key.
2. Run `python scripts/connect_supabase.py` once. Paste the **service-role (secret) key** when it asks. It tests every table and RPC the API uses, then saves the key and sets `GG_REPO=supabase`.
3. Run `python scripts/connect_supabase.py --check` any time to re-test.
4. Free-tier projects **pause after 7 days with no activity**. If the check fails with a connection error, open the dashboard and click *Restore project*. All data is kept.
5. Never put the service-role key in the web app or share `.env`. The web app only ever receives the anon key, through `/config`.
