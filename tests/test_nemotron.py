"""NVIDIA Nemotron provider: request shape, SSE parsing (reasoning kept out of replies), prompt contents. No network."""
import contextlib
import json

import pytest

from greenghar.llm import orchestrator as O
from greenghar.llm import providers as P
from greenghar.llm.knowledge import fewshot_messages, project_card
from greenghar.schemas import Home


def sse(*deltas, usage=None):
    lines = [f"data: {json.dumps({'choices': [{'delta': d}]})}" for d in deltas]
    if usage:
        lines.append(f"data: {json.dumps({'choices': [], 'usage': usage})}")
    return lines + ["data: [DONE]"]


class FakeStream:
    def __init__(self, status, lines, text=""):
        self.status_code, self._lines, self.text = status, lines, text

    def read(self):
        pass

    def iter_lines(self):
        yield from self._lines


@pytest.fixture
def nim(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test")
    seen = {}

    def fake_stream(method, url, json=None, headers=None, timeout=None):
        seen.update(url=url, body=json, headers=headers)
        resp = seen.pop("next")
        return contextlib.nullcontext(resp)

    monkeypatch.setattr(P.httpx, "stream", fake_stream)
    return seen


def test_default_provider_is_nemotron_with_thinking():
    p = P.chain()[0]
    assert p.name == "nvidia_nim" and p.model == "nvidia/nemotron-3.5-lightning-30b-a3b"
    assert p.stream and p.reasoning and p.reasoning_budget == 16384 and p.temperature == 1 and p.top_p == 0.95 and p.max_tokens == 16384


def test_request_matches_nvidia_example_and_reasoning_is_dropped(nim):
    nim["next"] = FakeStream(200, sse({"reasoning_content": "let me think about the score"}, {"reasoning_content": " more"},
                                      {"content": '{"answer": "Your score is 57.", '}, {"content": '"cited_fields": [], "caveats": []}'},
                                      usage={"total_tokens": 99}))
    out = P.chat(P.chain()[0], [{"role": "user", "content": "hi"}])
    b = nim["body"]
    assert nim["url"] == "https://integrate.api.nvidia.com/v1/chat/completions" and nim["headers"]["Authorization"] == "Bearer nvapi-test"
    assert b["stream"] is True and b["model"] == "nvidia/nemotron-3.5-lightning-30b-a3b"
    assert b["chat_template_kwargs"] == {"enable_thinking": True} and b["reasoning_budget"] == 16384
    assert (b["temperature"], b["top_p"], b["max_tokens"]) == (1, 0.95, 16384)
    assert json.loads(out["message"]["content"])["answer"] == "Your score is 57."
    assert "think" not in out["message"]["content"] and out["usage"]["reasoning_chars"] > 0 and out["usage"]["total_tokens"] == 99


def test_inline_think_tags_are_stripped(nim):
    nim["next"] = FakeStream(200, sse({"content": "<think>secret plan</think>{\"answer\": \"ok\"}"}))
    assert P.chat(P.chain()[0], [])["message"]["content"] == '{"answer": "ok"}'


def test_tool_call_deltas_are_assembled(nim):
    nim["next"] = FakeStream(200, sse({"tool_calls": [{"index": 0, "id": "c1", "function": {"name": "get_score", "arguments": ""}}]},
                                      {"tool_calls": [{"index": 0, "function": {"arguments": "{}"}}]}))
    m = P.chat(P.chain()[0], [], tools=[{"type": "function"}])["message"]
    assert m["tool_calls"][0]["function"] == {"name": "get_score", "arguments": "{}"} and m["tool_calls"][0]["id"] == "c1"


def test_http_errors_become_provider_errors(nim):
    nim["next"] = FakeStream(429, [], "slow down")
    with pytest.raises(P.ProviderError, match="rate limited"):
        P.chat(P.chain()[0], [])
    nim["next"] = FakeStream(401, [], "bad key")
    with pytest.raises(P.ProviderError, match="HTTP 401"):
        P.chat(P.chain()[0], [])


def test_thinking_can_be_switched_off(monkeypatch):
    monkeypatch.setenv("NVIDIA_THINKING", "off")
    assert P.chain()[0].reasoning is False and "chat_template_kwargs" not in P._body(P.chain()[0], [], None, False, 0.1)


def test_prompt_is_project_specific():
    s = O.system_prompt("hi")
    assert "Hindi" in s and "Hinglish" in s and "TOOL_RESULT" in s and "Infeasible" in s
    for w in ("energy_efficiency", "consumption_intensity", "rooftop_solar", "PM Surya Ghar"):
        assert w in project_card()


def test_fewshot_examples_are_grounded_and_in_prompt():
    from greenghar.llm.verifier import verify
    msgs = fewshot_messages()
    assert len(msgs) == 6 and msgs[0]["role"] == "user" and msgs[1]["role"] == "assistant"
    for u, a in zip(msgs[::2], msgs[1::2]):
        tr = json.loads(u["content"].split("TOOL_RESULT:\n", 1)[1].split("\n\nQUESTION:", 1)[0])
        assert verify(json.loads(a["content"])["answer"], tr)["grounded"]


def test_advisor_sends_system_fewshot_and_toolresult(monkeypatch):
    sent = {}

    class Prov(P.Provider):
        def __init__(self):
            super().__init__("nvidia_nim", "http://x", "nvidia/nemotron-3.5-lightning-30b-a3b", "NONE")

        @property
        def available(self):
            return True

    def fake_chat(provider, messages, tools=None, json_mode=False, **kw):
        sent["m"] = messages
        return {"message": {"content": json.dumps({"answer": "Your score is fine.", "cited_fields": [], "caveats": []})}, "usage": {}}

    monkeypatch.setattr(O, "chat", fake_chat)
    h = Home(home_id="T1", city="Pune", carpet_area_m2=80, monthly_kwh=[200] * 12)
    r = O.Advisor(providers=[Prov()]).answer(h, "Why is my score low?")
    m = sent["m"]
    assert m[0]["role"] == "system" and "PROJECT FACTS" in m[0]["content"]
    assert [x["role"] for x in m[1:-1]] == ["user", "assistant"] * 3 and m[-1]["content"].startswith("TOOL_RESULT:")
    assert r["provider"] == "nvidia_nim"
