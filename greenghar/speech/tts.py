"""Text-to-speech for spoken replies.

Primary: NVIDIA Magpie TTS Multilingual (build.nvidia.com), called through the NVIDIA cloud Riva gRPC
endpoint with your NVIDIA_API_KEY and the model's function id (NVIDIA_TTS_FUNCTION_ID, shown on the model's
build.nvidia.com API tab). Needs `pip install nvidia-riva-client`.
Fallback: edge-tts (free, hi-IN / ta-IN / mr-IN voices). Needs `pip install edge-tts`.
Returns audio bytes and a MIME type; the Telegram bot sends them as a voice note."""
from __future__ import annotations

import asyncio
import os

VOICES_EDGE = {"hi": "hi-IN-SwaraNeural", "en": "en-IN-NeerjaNeural", "ta": "ta-IN-PallaviNeural", "mr": "mr-IN-AarohiNeural",
               "te": "te-IN-ShrutiNeural", "kn": "kn-IN-SapnaNeural", "bn": "bn-IN-TanishaaNeural", "gu": "gu-IN-DhwaniNeural"}
MAGPIE_LANG = {"hi": "hi-IN", "en": "en-US"}


class TTSError(RuntimeError):
    pass


def synthesize(text: str, language: str = "en") -> dict:
    errors = []
    if os.environ.get("NVIDIA_API_KEY") and os.environ.get("NVIDIA_TTS_FUNCTION_ID") and language in MAGPIE_LANG:
        try:
            return _magpie(text, language)
        except Exception as e:  # provider failure -> next provider
            errors.append(f"magpie: {e}")
    try:
        return _edge(text, language)
    except Exception as e:
        errors.append(f"edge-tts: {e}")
    raise TTSError("; ".join(errors))


def _magpie(text: str, language: str) -> dict:
    import riva.client  # type: ignore
    auth = riva.client.Auth(uri="grpc.nvcf.nvidia.com:443", use_ssl=True, metadata_args=[
        ["function-id", os.environ["NVIDIA_TTS_FUNCTION_ID"]], ["authorization", f"Bearer {os.environ['NVIDIA_API_KEY']}"]])
    svc = riva.client.SpeechSynthesisService(auth)
    resp = svc.synthesize(text, voice_name=os.environ.get("NVIDIA_TTS_VOICE"), language_code=MAGPIE_LANG[language],
                          sample_rate_hz=22050, encoding=riva.client.AudioEncoding.LINEAR_PCM)
    import io
    import wave
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(22050); w.writeframes(resp.audio)
    return {"audio": buf.getvalue(), "mime": "audio/wav", "provider": "nvidia_magpie"}


def _edge(text: str, language: str) -> dict:
    import edge_tts  # type: ignore

    async def run() -> bytes:
        com = edge_tts.Communicate(text, VOICES_EDGE.get(language, VOICES_EDGE["en"]))
        out = b""
        async for chunk in com.stream():
            if chunk["type"] == "audio":
                out += chunk["data"]
        return out
    return {"audio": asyncio.run(run()), "mime": "audio/mpeg", "provider": "edge_tts"}
