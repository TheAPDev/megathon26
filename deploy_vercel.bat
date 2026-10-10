@echo off
REM Deploy to Vercel production (needs Node.js; will ask you to log in once)
cd /d %~dp0
call .venv\Scripts\activate
python scripts\deploy_vercel.py
