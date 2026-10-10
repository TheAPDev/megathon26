"""Dataset access: local parquet files (default) or Supabase via REST (when SUPABASE_URL is set).

The engine never cares where a home came from; it only sees a validated `Home`.
"""
from __future__ import annotations

import json
import math
import os
import uuid
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from .schemas import Home

DATA_DIR = Path(os.environ.get("GG_DATA_DIR", Path(__file__).resolve().parent.parent / "data" / "generated"))
RUNTIME_DIR = Path(os.environ.get("GG_RUNTIME_DIR", Path(__file__).resolve().parent.parent / "data" / "runtime"))
START_MONTH = pd.Timestamp("2024-10-01")


def _clean(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    if hasattr(v, "item") and not isinstance(v, (list, tuple)):
        try:
            return v.item()
        except Exception:
            return v
    return v


def last12_calendar(kwh_24m: list) -> list[Optional[float]]:
    """Map the last 12 readings (Oct 2025..Sep 2026) onto calendar order Jan..Dec."""
    out: list[Optional[float]] = [None] * 12
    for k in range(12, 24):
        month = (START_MONTH + pd.DateOffset(months=k)).month
        v = _clean(kwh_24m[k]) if kwh_24m is not None else None
        out[month - 1] = None if v is None else float(v)
    return out


def row_to_home(row: dict | pd.Series) -> Home:
    r = {k: _clean(v) for k, v in dict(row).items()}
    fields = {k: r[k] for k in Home.model_fields if k in r and k != "monthly_kwh"}
    kwh = r.get("kwh_24m")
    if kwh is not None and not isinstance(kwh, list):
        kwh = list(kwh)
    if kwh is not None and any(x is not None and not (isinstance(x, float) and math.isnan(x)) for x in kwh):
        fields["monthly_kwh"] = last12_calendar(kwh)
    return Home(**fields)


@lru_cache(maxsize=1)
def table(name: str) -> pd.DataFrame:
    p = DATA_DIR / f"{name}.parquet"
    if not p.exists():
        raise FileNotFoundError(f"{p} not found. Run `make data` (python scripts/generate_data.py) first.")
    return pd.read_parquet(p)


class LocalRepo:
    """Generated population (read-only Parquet) plus durable runtime writes as JSON Lines in data/runtime/:
    homes created at runtime, memory, advisor logs, Telegram links and bill uploads survive restarts."""

    def __init__(self, runtime_dir: Path | None = None) -> None:
        self._homes: Optional[pd.DataFrame] = None
        self.dir = Path(runtime_dir or RUNTIME_DIR)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.runtime_homes: dict[str, Home] = {}
        self.owners: dict[str, str] = {}
        self.memory: dict[str, list[dict]] = {}
        self.tg_links: dict[int, dict] = {}
        for r in self._read("homes"):
            self.runtime_homes[r["home"]["home_id"]] = Home(**r["home"])
            if r.get("owner"):
                self.owners[r["home"]["home_id"]] = r["owner"]
        for r in self._read("memory"):
            self.memory.setdefault(r["customer_id"], []).append(r)
        for r in self._read("telegram_links"):
            self.tg_links[int(r["chat_id"])] = r

    # ---- JSONL helpers -----------------------------------------------------------------------------
    def _read(self, name: str) -> list[dict]:
        p = self.dir / f"{name}.jsonl"
        if not p.exists():
            return []
        return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]

    def _append(self, name: str, row: dict) -> None:
        with open(self.dir / f"{name}.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")

    @property
    def homes(self) -> pd.DataFrame:
        if self._homes is None:
            self._homes = pd.read_parquet(DATA_DIR / "homes.parquet").set_index("home_id", drop=False)
        return self._homes

    # ---- homes -----------------------------------------------------------------------------------------
    def get_home(self, home_id: str) -> Home:
        if home_id in self.runtime_homes:
            return self.runtime_homes[home_id]
        try:
            return row_to_home(self.homes.loc[home_id])
        except KeyError as e:
            raise KeyError(f"Home {home_id} not found") from e

    def put_home(self, home: Home, owner: Optional[str] = None, source: str = "api") -> None:
        self.runtime_homes[home.home_id] = home
        if owner:
            self.owners[home.home_id] = owner
        self._append("homes", {"home": home.model_dump(), "owner": owner or self.owners.get(home.home_id), "source": source,
                               "at": datetime.now(timezone.utc).isoformat()})

    def owner_of(self, home_id: str) -> Optional[str]:
        return self.owners.get(home_id)

    def homes_of(self, sub: str) -> list[dict]:
        out = []
        for hid, owner in self.owners.items():
            if owner == sub:
                h = self.get_home(hid)
                out.append({"home_id": hid, "city": h.city, "dwelling_type": h.dwelling_type})
        return out

    def customer_for_home(self, home_id: str) -> Optional[dict]:
        p = DATA_DIR / "customers.parquet"
        if not p.exists():
            return None
        df = _customers_df()
        hit = df[df["home_id"] == home_id]
        return {k: _clean(v) for k, v in hit.iloc[0].to_dict().items()} if len(hit) else None

    # ---- memory ----------------------------------------------------------------------------------------
    def memory_for(self, customer_id: str) -> list[dict]:
        stored = []
        p = DATA_DIR / "memory.parquet"
        if p.exists():
            df = _memory_df()
            stored = [{k: _clean(v) for k, v in r.items()} for r in df[df["customer_id"] == customer_id].to_dict("records")]
        return stored + self.memory.get(customer_id, [])

    def add_memory(self, customer_id: str, item: dict) -> None:
        self.memory.setdefault(customer_id, []).append(item)
        self._append("memory", item)

    # ---- operations ------------------------------------------------------------------------------------
    def log_advisor(self, row: dict) -> None:
        self._append("advisor_logs", {**row, "created_at": datetime.now(timezone.utc).isoformat()})

    def get_telegram_link(self, chat_id: int) -> Optional[dict]:
        return self.tg_links.get(int(chat_id))

    def save_telegram_link(self, chat_id: int, home_id: Optional[str], language: str) -> None:
        row = {"chat_id": int(chat_id), "home_id": home_id, "language": language, "updated_at": datetime.now(timezone.utc).isoformat()}
        self.tg_links[int(chat_id)] = row
        self._append("telegram_links", row)

    def save_bill_upload(self, home_id: Optional[str], image: bytes, mime: str, parsed: dict) -> dict:
        ext = {"image/png": "png", "image/webp": "webp", "application/pdf": "pdf"}.get(mime, "jpg")
        folder = self.dir / "bills" / (home_id or "unlinked")
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:6]}.{ext}"
        path.write_bytes(image)
        rel = str(path.relative_to(self.dir))
        self._append("bill_uploads", {"home_id": home_id, "storage_path": rel, "provider": parsed.get("provider"),
                                      "warnings": parsed.get("warnings", []), "months_found": parsed.get("months_found")})
        return {"storage_path": rel}

    # ---- real public data (offline subset; full layer in Supabase) ----------------------------------------
    def real(self, name: str, **params) -> object:
        from . import realdata as R
        if name == "sources":
            return [{**x, "offline": x["source_id"] in ("census2011_districts", "nfhs5_states")} for x in R.SOURCES]
        if name == "state_profile":
            return R.state_profile(params["state"])
        if name == "synth_vs_real":
            return R.synth_vs_real(self.homes)
        return None  # city_climate / home_weather need the database (real weather is loaded in-database)

    # ---- portfolio -------------------------------------------------------------------------------------
    def portfolio(self, name: str, **params) -> object:
        from .engine import portfolio as P
        fn = {"summary": P.summary, "poor_homes": P.poor_homes, "ranking": P.ranking, "map": P.city_map,
              "targets": P.green_finance_targets, "rwa_leads": P.rwa_leads}[name]
        if name == "rwa_leads":
            return fn(params.get("min_homes", 4), params.get("limit", 50))
        return fn(**params)


@lru_cache(maxsize=1)
def _customers_df() -> pd.DataFrame:
    return pd.read_parquet(DATA_DIR / "customers.parquet")


@lru_cache(maxsize=1)
def _memory_df() -> pd.DataFrame:
    return pd.read_parquet(DATA_DIR / "memory.parquet")
