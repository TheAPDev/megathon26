"""Signed, expiring Telegram deep-link tokens: the web app links a chat to a home without exposing the home id
as a bearer secret. Format fits Telegram's /start payload (<= 64 chars, [A-Za-z0-9_-]): <home_id>_<exp36>_<sig>."""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import time
from typing import Optional

TTL_S = 15 * 60


def _secret() -> Optional[bytes]:
    s = os.environ.get("GG_LINK_SECRET") or os.environ.get("TELEGRAM_WEBHOOK_SECRET")
    if s:
        return s.encode()
    if os.environ.get("GG_ENV", "dev") == "dev":
        return b"greenghar-dev-link-secret"  # dev only; prod refuses without a configured secret
    return None


def _sig(payload: str, key: bytes) -> str:
    return base64.urlsafe_b64encode(hmac.new(key, payload.encode(), hashlib.sha256).digest()[:12]).decode().rstrip("=")


def make_token(home_id: str, now: Optional[float] = None) -> Optional[dict]:
    key = _secret()
    if key is None or not re.fullmatch(r"[A-Za-z0-9-]{1,32}", home_id):
        return None
    exp = int((now or time.time()) + TTL_S)
    payload = f"{home_id}_{exp:x}"
    return {"token": f"{payload}_{_sig(payload, key)}", "expires_at": exp}


def read_token(token: str, now: Optional[float] = None) -> Optional[str]:
    key = _secret()
    m = re.fullmatch(r"([A-Za-z0-9-]{1,32})_([0-9a-f]+)_([A-Za-z0-9_-]{16})", token or "")
    if key is None or not m:
        return None
    home_id, exp_hex, sig = m.groups()
    if not hmac.compare_digest(sig, _sig(f"{home_id}_{exp_hex}", key)) or int(exp_hex, 16) < (now or time.time()):
        return None
    return home_id
