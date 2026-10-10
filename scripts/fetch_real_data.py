"""Download the real public CSVs used offline into data/real/raw (the database loads its own copies; migrations 012-017)."""
from __future__ import annotations

import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from greenghar.realdata import RAW, SOURCES  # noqa: E402

OFFLINE = {"census2011_districts", "nfhs5_states"}  # the rest are large and served from Supabase

if __name__ == "__main__":
    RAW.mkdir(parents=True, exist_ok=True)
    for s in SOURCES:
        if s["source_id"] in OFFLINE or "--all" in sys.argv and s["url"].endswith(".csv"):
            r = httpx.get(s["url"], timeout=120, follow_redirects=True)
            r.raise_for_status()
            (RAW / f"{s['source_id']}.csv").write_bytes(r.content)
            print(s["source_id"], len(r.content), "bytes")
