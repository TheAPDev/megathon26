"""Numeric verifier: every number in a reply must match a number in the tool results.

Numbers are extracted with units/formatting stripped (Rs, commas, Indian lakh grouping, %, kWh, units,
lakh/crore words). A number is grounded if it matches any tool value, or the value rounded to the precision
the reply used (tolerance 0.5% or half the last shown digit, whichever is larger). Small integers 0-12 used as
counts or ordinals, and calendar years, are exempt and not counted.
"""
from __future__ import annotations

import math
import re
from typing import Any, Iterable

NUM = re.compile(r"(?<![\w.])[-−]?\d[\d,]*(?:\.\d+)?(?:\s*(?:lakh|lakhs|crore|cr|k)\b)?(?:\s*%)?", re.IGNORECASE)
DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")


def tool_numbers(obj: Any) -> list[float]:
    out: list[float] = []

    def walk(o):
        if isinstance(o, bool):
            return
        if isinstance(o, (int, float)):
            if not (isinstance(o, float) and math.isnan(o)):
                out.append(float(o))
        elif isinstance(o, dict):
            for v in o.values():
                walk(v)
        elif isinstance(o, (list, tuple)):
            for v in o:
                walk(v)
        elif isinstance(o, str):
            for m in NUM.finditer(o):
                v = _parse(m.group(0))
                if v is not None:
                    out.append(v[0])
    walk(obj)
    return out


def _parse(tok: str) -> tuple[float, float] | None:
    t = tok.strip().lower().replace("−", "-").rstrip("%").strip()
    mult = 1.0
    for word, m in (("lakhs", 1e5), ("lakh", 1e5), ("crore", 1e7), ("cr", 1e7), ("k", 1e3)):
        if t.endswith(word):
            mult, t = m, t[: -len(word)].strip()
            break
    t = t.replace(",", "")
    try:
        v = float(t)
    except ValueError:
        return None
    decimals = len(t.split(".")[1]) if "." in t else 0
    step = 10 ** (-decimals) * mult
    return v * mult, step


def extract(text: str) -> list[tuple[str, float, float, bool]]:
    text = text.translate(DEVANAGARI_DIGITS)
    res = []
    for m in NUM.finditer(text):
        p = _parse(m.group(0))
        if p is None:
            continue
        v, step = p
        tok = m.group(0)
        pct = tok.rstrip().endswith("%")
        if float(v).is_integer() and 0 <= v <= 12 and step >= 1 and mult_free(tok) and not pct:
            continue  # counts / ordinals
        if float(v).is_integer() and 1990 <= v <= 2060 and not pct:
            continue  # years
        res.append((tok.strip(), v, step, pct))
    return res


def mult_free(tok: str) -> bool:
    return not re.search(r"lakh|crore|cr|k", tok, re.IGNORECASE)


def grounded(value: float, step: float, pool: Iterable[float], pct: bool = False) -> bool:
    """Match against a tool value with rounding tolerance (half the shown precision, or 0.5% of the value).
    A percentage may also match a fraction (0.63 -> 63%), but only when the reply token carries '%'."""
    for t in pool:
        cands = [abs(t)]
        if pct and abs(t) <= 1:
            cands.append(abs(t) * 100)
        for cand in cands:
            tol = max(cand * 0.005, step / 2 + 1e-9)
            if abs(abs(value) - cand) <= tol:
                return True
    return False


def verify(text: str, tool_results: list[dict]) -> dict:
    pool = [100.0]  # score scale ("/100")
    for r in tool_results:
        pool += tool_numbers(r)
    nums = extract(text)
    bad = [tok for tok, v, step, pct in nums if not grounded(v, step, pool, pct)]
    total = len(nums)
    return {"total": total, "verified": total - len(bad), "unsupported": bad, "grounded": not bad,
            "badge": f"Grounded ✓ {total - len(bad)}/{total} figures verified" if not bad else
                     f"Not grounded: {len(bad)} of {total} figures unsupported"}
