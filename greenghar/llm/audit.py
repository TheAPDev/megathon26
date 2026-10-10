"""Advisor audit trail: every answer, its grounding result and provider, per channel."""
from __future__ import annotations

import logging


def log_answer(repo, home_id: str, question: str, out: dict, channel: str) -> None:
    """Persist every advisor turn (audit trail for groundedness); logging never breaks the reply."""
    try:
        cust = repo.customer_for_home(home_id)
        g = out.get("grounding", {})
        repo.log_advisor({"home_id": home_id, "customer_id": cust.get("customer_id") if cust else None, "channel": channel,
                          "question": question[:2000], "answer": out.get("answer", "")[:4000], "language": out.get("language"),
                          "provider": out.get("provider"), "model": out.get("model"), "grounded": bool(g.get("grounded")),
                          "figures_total": g.get("total"), "figures_verified": g.get("verified"), "tool_calls": out.get("tool_calls"),
                          "latency_ms": int(1000 * (out.get("latency_s") or 0)),
                          "prompt_tokens": (out.get("usage") or {}).get("prompt_tokens"),
                          "completion_tokens": (out.get("usage") or {}).get("completion_tokens")})
    except Exception:  # pragma: no cover - audit log failure is reported in logs only
        logging.getLogger("greenghar").exception("advisor log failed")
