@echo off
REM Run the Telegram bot by polling (needs TELEGRAM_BOT_TOKEN in .env or local.env)
cd /d %~dp0
call .venv\Scripts\activate
python scripts\run_telegram.py
