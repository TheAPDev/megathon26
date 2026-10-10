"""Telegram bot (webhook mode). Free Bot API: no per-message fees, no business verification.

Flow: /start -> send a bill photo (or try the demo home) -> score card with buttons -> ask anything by text
or voice note (Hindi, Tamil, Marathi, English...) -> grounded answer, optionally as a voice reply.
Set the webhook once:  POST https://api.telegram.org/bot<TOKEN>/setWebhook
                       {"url": "<API>/telegram/webhook", "secret_token": "<TELEGRAM_WEBHOOK_SECRET>"}
"""
from __future__ import annotations

import os
import uuid
from typing import Any

import httpx

from ..llm.templates import inr
from ..schemas import Home

API = "https://api.telegram.org/bot{token}/{method}"
FILE = "https://api.telegram.org/file/bot{token}/{path}"
DEMO_HOME = os.environ.get("GG_DEMO_HOME", "H000011")


class TelegramBot:
    def __init__(self, repo, advisor, token: str | None = None, send: Any = None):
        self.repo, self.advisor = repo, advisor
        self.token = token or os.environ.get("TELEGRAM_BOT_TOKEN", "")
        self.sessions: dict[int, dict] = {}
        self._send = send  # injectable for tests: fn(method, payload) -> dict
        self.outbox: list[tuple[str, dict]] = []

    # ---- Bot API -----------------------------------------------------------------------------
    def call(self, method: str, payload: dict, files: dict | None = None) -> dict:
        self.outbox.append((method, payload))
        if self._send:
            return self._send(method, payload)
        if not self.token:
            return {"ok": False, "description": "TELEGRAM_BOT_TOKEN not set"}
        r = httpx.post(API.format(token=self.token, method=method), data=payload if files else None,
                       json=None if files else payload, files=files, timeout=30)
        return r.json()

    def download(self, file_id: str) -> bytes:
        info = self.call("getFile", {"file_id": file_id})
        path = info.get("result", {}).get("file_path")
        if not path or not self.token:
            raise RuntimeError("Could not download file from Telegram")
        return httpx.get(FILE.format(token=self.token, path=path), timeout=60).content

    def say(self, chat_id: int, text: str, buttons: list[list[dict]] | None = None) -> None:
        payload: dict = {"chat_id": chat_id, "text": text[:4000]}
        if buttons:
            payload["reply_markup"] = {"inline_keyboard": buttons}
        self.call("sendMessage", payload)

    # ---- Handlers ----------------------------------------------------------------------------
    def menu(self) -> list[list[dict]]:
        rows = [[{"text": "📋 My plan", "callback_data": "plan"}, {"text": "☀️ What if solar?", "callback_data": "whatif:rooftop_solar"}],
                [{"text": "🔥 Heatwave mode", "callback_data": "heatwave"}, {"text": "💰 EMI vs savings", "callback_data": "finance"}],
                [{"text": "हिंदी", "callback_data": "lang:hi"}, {"text": "English", "callback_data": "lang:en"}]]
        url = os.environ.get("GG_MINIAPP_URL")
        if url:
            rows.append([{"text": "📊 Open dashboard", "web_app": {"url": url}}])
        return rows

    def session(self, chat_id: int) -> dict:
        """Chat -> home link and language survive restarts (repo.telegram_links); 'awaiting' is transient."""
        if chat_id not in self.sessions:
            saved = None
            try:
                saved = self.repo.get_telegram_link(chat_id)
            except Exception:  # storage down: carry on with a fresh session
                pass
            self.sessions[chat_id] = {"home_id": (saved or {}).get("home_id"), "lang": (saved or {}).get("language") or "en", "awaiting": None}
        return self.sessions[chat_id]

    def persist(self, chat_id: int) -> None:
        s = self.session(chat_id)
        try:
            self.repo.save_telegram_link(chat_id, s["home_id"], s["lang"])
        except Exception:
            pass

    def handle(self, update: dict) -> dict:
        if "callback_query" in update:
            cq = update["callback_query"]
            self.call("answerCallbackQuery", {"callback_query_id": cq["id"]})
            return self.on_callback(cq["message"]["chat"]["id"], cq.get("data", ""))
        msg = update.get("message") or update.get("edited_message")
        if not msg:
            return {"ignored": True}
        chat_id = msg["chat"]["id"]
        if msg.get("photo") or (msg.get("document", {}).get("mime_type", "").startswith("image/")):
            return self.on_photo(chat_id, msg)
        if msg.get("voice") or msg.get("audio"):
            return self.on_voice(chat_id, msg)
        text = (msg.get("text") or "").strip()
        if text.startswith("/start"):
            arg = text[6:].strip()
            if arg:  # deep link from the web app: /start <signed token>
                from ..api.linking import read_token
                home_id = read_token(arg)
                if home_id:
                    try:
                        return self.link(chat_id, home_id)
                    except KeyError:
                        pass
                self.say(chat_id, "That link has expired. Open Green Ghar on the web and tap 'Continue on Telegram' again.")
                return {"handled": "bad_link"}
            return self.on_start(chat_id)
        if text.lower() in ("demo", "/demo"):
            return self.link(chat_id, DEMO_HOME)
        return self.on_text(chat_id, text)

    def on_start(self, chat_id: int) -> dict:
        self.say(chat_id, "Namaste! I'm Green Ghar. Send a photo of your electricity bill and I'll score your home in about a minute, "
                          "then show what to fix first and what it saves. Type 'demo' to try a sample home.",
                 [[{"text": "🏠 Try the demo home", "callback_data": "demo"}]])
        return {"handled": "start"}

    def link(self, chat_id: int, home_id: str) -> dict:
        s = self.session(chat_id)
        s["home_id"] = home_id
        self.persist(chat_id)
        home = self.repo.get_home(home_id)
        return self.score_card(chat_id, home)

    def score_card(self, chat_id: int, home: Home) -> dict:
        r = self.advisor.answer(home, "Why is my score what it is?", self.session(chat_id)["lang"], use_llm=False)
        self.say(chat_id, f"{r['answer']}\n\n{r['grounding']['badge']}", self.menu())
        return {"handled": "score", "home_id": home.home_id}

    def on_photo(self, chat_id: int, msg: dict) -> dict:
        from ..ocr.bill import OCRError, parse_bill
        file_id = msg["photo"][-1]["file_id"] if msg.get("photo") else msg["document"]["file_id"]
        try:
            self._last_file = self.download(file_id)
            parsed = parse_bill(self._last_file)
        except (OCRError, RuntimeError) as e:
            self.say(chat_id, f"Sorry, I couldn't read that bill ({e}). Try a clearer photo, or type 'demo'.")
            return {"handled": "photo_failed"}
        city = parsed.get("city") if parsed.get("city") else None
        s = self.session(chat_id)
        home = Home(home_id=f"TG-{uuid.uuid4().hex[:8]}", city=city or "Delhi", monthly_kwh=parsed["monthly_kwh"],
                    data_source="bill_ocr", sanctioned_load_kw=parsed.get("sanctioned_load_kw") or 3)
        self.repo.put_home(home, source="telegram")
        s["home_id"] = home.home_id
        self.persist(chat_id)
        try:
            self.repo.save_bill_upload(home.home_id, self._last_file, "image/jpeg", parsed)
        except Exception:
            pass
        note = f"Read {parsed['months_found']} month(s) of usage." + (" " + " ".join(parsed["warnings"]) if parsed["warnings"] else "")
        if not city:
            s["awaiting"] = "city"
            self.say(chat_id, note + " Which city is the home in?")
            return {"handled": "photo", "awaiting": "city"}
        self.say(chat_id, note)
        return self.score_card(chat_id, home)

    def on_voice(self, chat_id: int, msg: dict) -> dict:
        from ..speech.stt import STTError, transcribe
        v = msg.get("voice") or msg.get("audio")
        try:
            t = transcribe(self.download(v["file_id"]), "voice.ogg")
        except (STTError, RuntimeError) as e:
            self.say(chat_id, f"I couldn't hear that clearly ({e}). Please type your question.")
            return {"handled": "voice_failed"}
        out = self.on_text(chat_id, t["text"], voice_reply=True)
        return {**out, "transcript": t["text"]}

    def on_text(self, chat_id: int, text: str, voice_reply: bool = False) -> dict:
        s = self.session(chat_id)
        if s["awaiting"] == "city":
            from ..reference import cities
            match = next((c for c in cities() if c.lower() == text.lower()), None)
            if not match:
                self.say(chat_id, "I don't have climate data for that city yet. Nearest big city?")
                return {"handled": "city_unknown"}
            home = self.repo.get_home(s["home_id"]).model_copy(update={"city": match})
            self.repo.put_home(home, source="telegram")
            s["awaiting"] = None
            return self.score_card(chat_id, home)
        if not s["home_id"]:
            self.say(chat_id, "Send a bill photo first, or type 'demo'.")
            return {"handled": "no_home"}
        home = self.repo.get_home(s["home_id"])
        r = self.advisor.answer(home, text, s["lang"])
        new_lang = r["language"] if r["language"] != "en" else s["lang"]
        if new_lang != s["lang"]:
            s["lang"] = new_lang
            self.persist(chat_id)
        from ..llm.audit import log_answer
        log_answer(self.repo, home.home_id, text, r, "telegram")
        self.say(chat_id, f"{r['answer']}\n\n{r['grounding']['badge']}", self.menu())
        if voice_reply:
            try:
                from ..speech.tts import synthesize
                audio = synthesize(r["answer"], r["language"])
                self.call("sendVoice" if audio["mime"] != "audio/wav" else "sendAudio", {"chat_id": str(chat_id)},
                          files={"voice" if audio["mime"] != "audio/wav" else "audio": ("reply", audio["audio"], audio["mime"])})
            except Exception:  # voice reply is a bonus; the text answer already went out
                pass
        return {"handled": "answer", "grounded": r["grounding"]["grounded"]}

    def on_callback(self, chat_id: int, data: str) -> dict:
        s = self.session(chat_id)
        if data == "demo":
            return self.link(chat_id, DEMO_HOME)
        if data.startswith("lang:"):
            s["lang"] = data.split(":")[1]
            self.say(chat_id, "ठीक है, अब हिंदी में।" if s["lang"] == "hi" else "OK, English from now on.")
            return {"handled": "lang"}
        if not s["home_id"]:
            return self.on_start(chat_id)
        q = {"plan": "What should I do to reduce my bill?", "heatwave": "What should I do before the heatwave?",
             "finance": "Can I afford it on EMI?"}.get(data)
        if data.startswith("whatif:"):
            q = f"What if I add {data.split(':')[1].replace('_', ' ')}?"
        return self.on_text(chat_id, q or "score")


def format_inr(x: float) -> str:
    return "₹" + inr(x)


_ME: dict = {}  # token -> username


def bot_username() -> str | None:
    """TELEGRAM_BOT_USERNAME, or looked up once from the token with getMe (cached)."""
    import os
    u = os.environ.get("TELEGRAM_BOT_USERNAME", "").lstrip("@")
    if u:
        return u
    tok = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not tok:
        return None
    if tok not in _ME:
        try:
            import httpx
            r = httpx.get(f"https://api.telegram.org/bot{tok}/getMe", timeout=5)
            _ME[tok] = (r.json().get("result") or {}).get("username") if r.status_code == 200 else None
        except Exception:
            _ME[tok] = None
    return _ME[tok]
