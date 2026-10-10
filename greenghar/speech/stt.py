"""Speech-to-text for voice notes: Whisper large-v3 on Groq (free tier), falling back to Whisper on NVIDIA NIM.
Telegram voice notes are OGG/Opus, which Groq accepts directly."""
from __future__ import annotations

import os

import httpx

GROQ_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
NIM_URL = os.environ.get("NVIDIA_ASR_URL", "https://integrate.api.nvidia.com/v1/audio/transcriptions")


class STTError(RuntimeError):
    pass


def transcribe(audio: bytes, filename: str = "voice.ogg", language: str | None = None) -> dict:
    """Return {"text", "language", "provider"}. `language` is an ISO-639-1 hint (e.g. 'hi')."""
    errors = []
    if os.environ.get("GROQ_API_KEY"):
        try:
            return _openai_style(GROQ_URL, os.environ["GROQ_API_KEY"], os.environ.get("GROQ_STT_MODEL", "whisper-large-v3"),
                                 audio, filename, language, "groq_whisper")
        except STTError as e:
            errors.append(str(e))
    if os.environ.get("NVIDIA_API_KEY"):
        try:
            return _openai_style(NIM_URL, os.environ["NVIDIA_API_KEY"], os.environ.get("NVIDIA_STT_MODEL", "openai/whisper-large-v3"),
                                 audio, filename, language, "nvidia_whisper")
        except STTError as e:
            errors.append(str(e))
    raise STTError("No speech-to-text provider available: " + ("; ".join(errors) or "set GROQ_API_KEY or NVIDIA_API_KEY"))


def _openai_style(url, key, model, audio, filename, language, name) -> dict:
    data = {"model": model, "response_format": "verbose_json", "temperature": "0"}
    if language:
        data["language"] = language
    try:
        r = httpx.post(url, headers={"Authorization": f"Bearer {key}"}, data=data,
                       files={"file": (filename, audio, "audio/ogg")}, timeout=60)
    except httpx.HTTPError as e:
        raise STTError(f"{name}: {e}") from e
    if r.status_code >= 400:
        raise STTError(f"{name}: HTTP {r.status_code} {r.text[:200]}")
    j = r.json()
    return {"text": j.get("text", "").strip(), "language": j.get("language", language), "provider": name}
