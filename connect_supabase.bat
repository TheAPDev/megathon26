@echo off
REM Connect the API to the green-ghar Supabase project (asks for the service-role key once, tests, saves to .env)
cd /d %~dp0
call .venv\Scripts\activate
python scripts\connect_supabase.py %*
pause
