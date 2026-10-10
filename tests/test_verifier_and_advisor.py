from greenghar.llm.orchestrator import Advisor, detect_language, mentioned_retrofits, parse_budget
from greenghar.llm.providers import Provider
from greenghar.llm.verifier import extract, verify
from greenghar.schemas import Home


def test_verifier_catches_invented_numbers():
    v = verify("Your bill drops by Rs 9,999 and the score goes to 77.", [{"facts": {"saving": 1200, "score": 70}}])
    assert not v["grounded"] and set(v["unsupported"]) == {"9,999", "77"}


def test_verifier_accepts_indian_formatting_and_rounding():
    facts = [{"facts": {"saving_inr_year": 123456.0, "kwh": 1412.4, "pct": 0.63}}]
    assert verify("Saves Rs 1,23,456 a year and 1,412 units; 63% less.", facts)["grounded"]
    assert verify("About 1.2 lakh rupees.", [{"facts": {"x": 123456.0}}])["grounded"]


def test_devanagari_digits_are_checked():
    assert not verify("बचत ₹९९९९", [{"facts": {"x": 1200}}])["grounded"]


def test_small_counts_and_years_exempt():
    assert [t for t, *_ in extract("Do these 3 things in 2027")] == []
    assert [t for t, *_ in extract("cuts 63% of use")] == ["63%"]


def test_router_handles_negation_and_hinglish():
    assert mentioned_retrofits("What if I skip insulation and just get solar?") == ["rooftop_solar"]
    assert "bldc_fans" in mentioned_retrofits("pankha badalna hai")
    assert parse_budget("mera budget 50 hazaar hai") == 50000
    assert parse_budget("I have 1.5 lakh") == 150000
    assert detect_language("मेरा बिल कैसे कम होगा?") == "hi"


class FakeProvider(Provider):
    def __init__(self, text):
        super().__init__("fake", "http://x", "fake-model", "NONE")
        self.text = text

    @property
    def available(self):
        return True


def test_hallucinating_llm_falls_back_to_template(monkeypatch):
    import greenghar.llm.orchestrator as O
    calls = {"n": 0}

    def fake_chat(provider, messages, tools=None, json_mode=False, **kw):
        calls["n"] += 1
        return {"message": {"content": '{"answer": "You will save Rs 98,765 every year, guaranteed.", "cited_fields": [], "caveats": []}'},
                "usage": {}, "latency_s": 0.0, "provider": "fake", "model": "fake"}
    monkeypatch.setattr(O, "chat", fake_chat)
    h = Home(home_id="T", city="Delhi", carpet_area_m2=100, n_ac=1, monthly_kwh=[300.0] * 12)
    r = Advisor(providers=[FakeProvider("x")]).answer(h, "Why is my score low?")
    assert r["provider"] == "template" and r["grounding"]["grounded"] and calls["n"] == 2  # retried once, then fell back
    assert "98,765" not in r["answer"]


def test_grounded_llm_reply_is_used(monkeypatch):
    import greenghar.llm.orchestrator as O
    from greenghar.engine.score import score_home
    h = Home(home_id="T", city="Delhi", carpet_area_m2=100, n_ac=1, monthly_kwh=[300.0] * 12)
    s = score_home(h).score

    def fake_chat(provider, messages, tools=None, json_mode=False, **kw):
        return {"message": {"content": f'{{"answer": "Your score is {s} out of 100. This is an estimate.", "cited_fields": ["score"], "caveats": []}}'},
                "usage": {}, "latency_s": 0.0, "provider": "fake", "model": "fake"}
    monkeypatch.setattr(O, "chat", fake_chat)
    r = Advisor(providers=[FakeProvider("x")]).answer(h, "What is my score?")
    assert r["provider"] == "fake" and r["grounding"]["grounded"]
