@echo off
REM One-time setup on Windows: Python virtual env + backend dependencies. The web app is pre-built in frontend\dist.
cd /d %~dp0
if not exist .venv python -m venv .venv
call .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
echo.
echo Setup done. Next:
echo   connect_supabase.bat   (once: paste the service-role key to use the live database)
echo   run.bat                (starts the API + web app at http://localhost:8000/app/)
