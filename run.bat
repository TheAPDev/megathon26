@echo off
REM Start Green Ghar: API + web app on http://localhost:8000/app/
cd /d %~dp0
call .venv\Scripts\activate
start "" http://localhost:8000/app/
uvicorn greenghar.api.main:app --host 127.0.0.1 --port 8000
