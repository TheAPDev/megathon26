"""Electricity bill photo -> structured usage (any discom format).

Primary: Gemini Flash (free tier) with a JSON response schema. Fallback: Tesseract OCR + regex for the
common fields. The result is validated before it touches the engine: implausible values are dropped and
flagged, and the consumer number is masked."""
from __future__ import annotations

import base64
import json
import os
import re

import httpx

from ..reference import cities, tariff_states

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
PROMPT = """Extract from this Indian electricity bill. Return JSON only:
{"discom": str, "state": str, "consumer_number": str, "bill_month": "YYYY-MM", "units_this_bill": number,
 "billing_period_months": 1 or 2, "history": [{"month": "YYYY-MM", "units": number}], "sanctioned_load_kw": number,
 "tariff_category": str, "amount_inr": number, "city": str}
Use null when a field is not printed. Copy numbers exactly as printed. history = the consumption history table if present."""


class OCRError(RuntimeError):
    pass


def parse_bill(image: bytes, mime: str = "image/jpeg") -> dict:
    raw, provider = None, None
    if os.environ.get("GEMINI_API_KEY"):
        try:
            raw, provider = _gemini(image, mime), "gemini"
        except OCRError:
            raw = None
    if raw is None:
        raw, provider = _tesseract(image, mime), "tesseract"
    return validate(raw) | {"provider": provider}


def _gemini(image: bytes, mime: str) -> dict:
    model = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")
    body = {"contents": [{"parts": [{"text": PROMPT}, {"inline_data": {"mime_type": mime, "data": base64.b64encode(image).decode()}}]}],
            "generationConfig": {"response_mime_type": "application/json", "temperature": 0}}
    try:
        r = httpx.post(GEMINI_URL.format(model=model), params={"key": os.environ["GEMINI_API_KEY"]}, json=body, timeout=60)
    except httpx.HTTPError as e:
        raise OCRError(str(e)) from e
    if r.status_code >= 400:
        raise OCRError(f"HTTP {r.status_code}: {r.text[:200]}")
    text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
    return json.loads(text)


def _pdf_text(pdf: bytes) -> str:
    """Text layer first (most DISCOM e-bills have one); scanned PDFs are rasterised with pdftoppm and OCR'd."""
    import io
    import subprocess
    import tempfile
    from pathlib import Path

    text = ""
    try:
        from pypdf import PdfReader
        text = "\n".join((pg.extract_text() or "") for pg in PdfReader(io.BytesIO(pdf)).pages[:6])
    except Exception:
        text = ""
    if len(re.findall(r"\d", text)) >= 30:
        return text
    import pytesseract  # type: ignore
    from PIL import Image
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "bill.pdf").write_bytes(pdf)
        subprocess.run(["pdftoppm", "-r", "200", "-l", "3", "-png", str(Path(d) / "bill.pdf"), str(Path(d) / "pg")], check=True, timeout=60)
        return text + "\n" + "\n".join(pytesseract.image_to_string(Image.open(f)) for f in sorted(Path(d).glob("pg*.png")))


def _tesseract(image: bytes, mime: str = "image/jpeg") -> dict:
    try:
        import io

        import pytesseract  # type: ignore
        from PIL import Image
        text = _pdf_text(image) if mime == "application/pdf" else pytesseract.image_to_string(Image.open(io.BytesIO(image)))
    except Exception as e:
        raise OCRError(f"No OCR provider available (set GEMINI_API_KEY or install tesseract): {e}") from e
    return parse_text(text)


def parse_text(text: str) -> dict:
    """Regex extraction for OCR'd text (also used by tests)."""
    def num(pat):
        m = re.search(pat, text, re.I)
        return float(m.group(1).replace(",", "")) if m else None
    hist = [{"month": f"{y}-{int(mo):02d}", "units": float(u)} for mo, y, u in
            re.findall(r"(\d{1,2})[/-](20\d\d)\s+(\d{2,5})\b", text)]
    return {"discom": None, "state": None, "consumer_number": (re.search(r"(?:consumer|ca|account)\s*(?:no|number)?[.:\s]*([\w-]{6,})", text, re.I) or [None, None])[1],
            "units_this_bill": num(r"(?:units|consumption|kwh)[^\d]{0,20}(\d[\d,]*)"),
            "sanctioned_load_kw": num(r"(?:sanctioned|connected)\s*load[^\d]{0,15}(\d+(?:\.\d+)?)"),
            "amount_inr": num(r"(?:amount|total)\s*(?:payable|due)?[^\d]{0,15}(\d[\d,]*(?:\.\d+)?)"),
            "billing_period_months": 2 if re.search(r"bi-?monthly", text, re.I) else 1, "history": hist, "bill_month": None,
            "tariff_category": None, "city": None}


def validate(raw: dict) -> dict:
    warnings = []
    out = dict(raw)
    cn = str(raw.get("consumer_number") or "")
    out["consumer_number_masked"] = ("*" * max(0, len(cn) - 4) + cn[-4:]) if cn else None
    out.pop("consumer_number", None)
    period = raw.get("billing_period_months") or 1
    months = {}
    for h in raw.get("history") or []:
        u = h.get("units")
        if u is None or not (0 <= float(u) <= 6000 * period):
            warnings.append(f"Ignored implausible reading for {h.get('month')}: {u}")
            continue
        months[h["month"]] = float(u) / period
    if raw.get("bill_month") and raw.get("units_this_bill") is not None:
        months.setdefault(raw["bill_month"], float(raw["units_this_bill"]) / period)
    monthly = [None] * 12
    for k, v in months.items():
        try:
            monthly[int(k.split("-")[1]) - 1] = round(v, 1)
        except (ValueError, IndexError):
            warnings.append(f"Unreadable month '{k}'")
    if raw.get("state") and raw["state"] not in tariff_states():
        warnings.append(f"State '{raw['state']}' has no tariff table yet; savings will use national averages")
    if raw.get("city") and raw["city"] not in cities():
        warnings.append(f"City '{raw['city']}' not in the climate table; pick the nearest city")
    out["monthly_kwh"] = monthly
    out["months_found"] = sum(v is not None for v in monthly)
    out["warnings"] = warnings
    return out
