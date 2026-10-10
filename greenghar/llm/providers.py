"""OpenAI-compatible chat providers with a fallback chain: NVIDIA NIM (Nemotron) -> Groq -> (template, in orchestrator).
Keys come from the environment only and never leave the server.

NVIDIA Nemotron 3.5 Lightning is a reasoning model: it is called with `enable_thinking` + a reasoning budget, as a
streamed request (thinking can take a while, streaming keeps the connection alive). `reasoning_content` is read and
discarded; only the final `content` is ever shown to a user, and that is still checked by the numeric verifier."""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field

import httpx

DEFAULT_NVIDIA_MODEL = "nvidia/nemotron-3.5-lightning-30b-a3b"
_THINK = re.compile(r"<think>.*?</think>", re.S)


def _flag(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    return default if v is None else v.strip().lower() in ("1", "true", "on", "yes")


@dataclass
class Provider:
    name: str
    base_url: str
    model: str
    key_env: str
    reasoning: bool = False          # send chat_template_kwargs.enable_thinking + reasoning_budget
    reasoning_budget: int = 16384
    stream: bool = False
    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int = 700
    timeout: float = 25.0
    extra: dict = field(default_factory=dict)

    @property
    def key(self) -> str | None:
        return os.environ.get(self.key_env) or None

    @property
    def available(self) -> bool:
        return bool(self.key)


def chain() -> list[Provider]:
    think = _flag("NVIDIA_THINKING", True)
    return [
        Provider("nvidia_nim", os.environ.get("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1"),
                 os.environ.get("NVIDIA_MODEL", DEFAULT_NVIDIA_MODEL), "NVIDIA_API_KEY",
                 reasoning=think, reasoning_budget=int(os.environ.get("NVIDIA_REASONING_BUDGET", "16384")),
                 stream=True, temperature=float(os.environ.get("NVIDIA_TEMPERATURE", "1")),
                 top_p=float(os.environ.get("NVIDIA_TOP_P", "0.95")),
                 max_tokens=int(os.environ.get("NVIDIA_MAX_TOKENS", "16384")),
                 timeout=float(os.environ.get("NVIDIA_TIMEOUT", "90"))),
        Provider("groq", os.environ.get("GROQ_BASE_URL", "https://api.groq.com/openai/v1"),
                 os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b"), "GROQ_API_KEY"),
    ]


class ProviderError(RuntimeError):
    pass


def _body(provider: Provider, messages, tools, json_mode, temperature) -> dict:
    body: dict = {"model": provider.model, "messages": messages,
                  "temperature": provider.temperature if provider.temperature is not None else temperature,
                  "max_tokens": provider.max_tokens}
    if provider.top_p is not None:
        body["top_p"] = provider.top_p
    if provider.reasoning:
        body["chat_template_kwargs"] = {"enable_thinking": True}
        body["reasoning_budget"] = provider.reasoning_budget
    if provider.stream:
        body["stream"] = True
    if tools:
        body["tools"] = tools
        body["tool_choice"] = "auto"
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    body.update(provider.extra)
    return body


def _headers(provider: Provider) -> dict:
    return {"Authorization": f"Bearer {provider.key}", "Content-Type": "application/json"}


def _check(provider: Provider, status: int, text: str) -> None:
    if status == 429:
        raise ProviderError(f"{provider.name}: rate limited")
    if status >= 400:
        raise ProviderError(f"{provider.name}: HTTP {status} {text[:200]}")


def _read_stream(provider: Provider, body: dict) -> tuple[dict, dict, int]:
    """Accumulate an SSE chat stream into one message. Returns (message, usage, reasoning_chars)."""
    content: list[str] = []
    reasoning_chars = 0
    calls: dict[int, dict] = {}
    usage: dict = {}
    deadline = time.time() + provider.timeout * 2
    with httpx.stream("POST", f"{provider.base_url}/chat/completions", json=body, headers=_headers(provider),
                      timeout=httpx.Timeout(provider.timeout, connect=10.0)) as r:
        if r.status_code >= 400:
            r.read()
            _check(provider, r.status_code, r.text)
        for line in r.iter_lines():
            if time.time() > deadline:
                raise ProviderError(f"{provider.name}: stream exceeded {provider.timeout * 2:.0f}s")
            if not line or not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload == "[DONE]":
                break
            try:
                chunk = json.loads(payload)
            except json.JSONDecodeError:
                continue
            usage = chunk.get("usage") or usage
            for ch in chunk.get("choices") or []:
                d = ch.get("delta") or {}
                reasoning_chars += len(d.get("reasoning_content") or d.get("reasoning") or "")  # read, never shown
                if d.get("content"):
                    content.append(d["content"])
                for tc in d.get("tool_calls") or []:
                    slot = calls.setdefault(tc.get("index", 0), {"id": "", "type": "function", "function": {"name": "", "arguments": ""}})
                    slot["id"] = tc.get("id") or slot["id"]
                    fn = tc.get("function") or {}
                    slot["function"]["name"] += fn.get("name") or ""
                    slot["function"]["arguments"] += fn.get("arguments") or ""
    msg: dict = {"role": "assistant", "content": "".join(content)}
    if calls:
        msg["tool_calls"] = [calls[i] for i in sorted(calls)]
    return msg, usage, reasoning_chars


def chat(provider: Provider, messages: list[dict], tools: list[dict] | None = None, json_mode: bool = False,
         temperature: float = 0.1) -> dict:
    t = time.time()
    reasoning_chars = 0
    try:
        if provider.stream:
            try:
                msg, usage, reasoning_chars = _read_stream(provider, _body(provider, messages, tools, json_mode, temperature))
            except ProviderError as e:
                if tools and "HTTP 400" in str(e):  # model/endpoint without tool calling: answer from TOOL_RESULT only
                    msg, usage, reasoning_chars = _read_stream(provider, _body(provider, messages, None, json_mode, temperature))
                else:
                    raise
        else:
            r = httpx.post(f"{provider.base_url}/chat/completions", json=_body(provider, messages, tools, json_mode, temperature),
                           timeout=provider.timeout, headers=_headers(provider))
            _check(provider, r.status_code, r.text)
            data = r.json()
            msg, usage = data["choices"][0]["message"], data.get("usage", {})
    except httpx.HTTPError as e:
        raise ProviderError(f"{provider.name}: {e}") from e
    if msg.get("content"):
        msg["content"] = _THINK.sub("", msg["content"]).strip()
    return {"message": msg, "usage": {**usage, "reasoning_chars": reasoning_chars} if reasoning_chars else usage,
            "latency_s": round(time.time() - t, 3), "provider": provider.name, "model": provider.model}
