"""Supabase (PostgREST + Storage) repository. Selected with GG_REPO=supabase.

Uses the service-role key server-side only (never shipped to clients). Same interface as LocalRepo:
homes, customers, memory, advisor logs, Telegram links, bill uploads (Storage bucket `bills`) and the
portfolio RPCs (supabase/migrations/010_portfolio_rpc.sql)."""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

import httpx

from ..data_access import row_to_home
from ..reference import city
from ..schemas import Home

HOME_COLUMNS = ",".join([
    "home_id", "city", "dwelling_type", "floor_position", "tenure", "carpet_area_m2", "occupants", "building_age_years", "roof_area_m2",
    "roof_access", "wall_type", "window_to_wall", "west_glass", "shading", "cool_roof", "roof_insulation", "solar_film", "n_ac", "ac_tech",
    "ac_star", "ac_age_years", "ac_tonnage", "ac_setpoint_c", "n_coolers", "n_fans", "bldc_fan_share", "fridge_star", "fridge_age_years",
    "light_points", "led_share", "water_heating", "cooking", "lpg_cylinders_per_year", "pv_kw", "net_metered", "backup", "outage_hours_month",
    "smart_meter", "tod_tariff", "smart_plugs", "bee_star_label", "sanctioned_load_kw", "income_band", "wfh", "data_source", "kwh_24m"])

PORTFOLIO_RPC = {"summary": "portfolio_summary", "poor_homes": "portfolio_poor_homes", "ranking": "portfolio_ranking",
                 "map": "portfolio_city_map", "targets": "portfolio_targets", "rwa_leads": "portfolio_rwa_leads"}


def _last12_to_24(monthly: Optional[list]) -> list:
    """Calendar Jan..Dec -> the kwh_24m slots 13..24 (Oct 2025..Sep 2026); earlier 12 months unknown."""
    out = [None] * 24
    for m, v in enumerate(monthly or [None] * 12, start=1):
        out[12 + ((m + 2) % 12)] = v
    return out


def service_headers(key: str) -> dict:
    """Legacy service_role keys are JWTs (sent as apikey + Bearer). New `sb_secret_...` keys are opaque and must go
    in the apikey header only; the gateway rejects them as a Bearer token."""
    return {"apikey": key} if key.startswith("sb_") else {"apikey": key, "Authorization": f"Bearer {key}"}


class SupabaseRepo:
    def __init__(self, url: Optional[str] = None, key: Optional[str] = None, client: Optional[httpx.Client] = None):
        base = (url or os.environ["SUPABASE_URL"]).rstrip("/")
        self.url, self.storage = base + "/rest/v1", base + "/storage/v1"
        key = key or os.environ["SUPABASE_SERVICE_ROLE_KEY"]
        self.h = {**service_headers(key), "Content-Type": "application/json"}
        self.client = client or httpx.Client(timeout=15, headers=self.h)
        self.runtime_homes: dict[str, Home] = {}

    # ---- low level -------------------------------------------------------------------------------
    def _get(self, table: str, params: dict) -> list[dict]:
        r = self.client.get(f"{self.url}/{table}", params=params)
        r.raise_for_status()
        return r.json()

    def _post(self, table: str, row: dict | list, upsert: bool = False) -> None:
        headers = {"Prefer": "resolution=merge-duplicates,return=minimal"} if upsert else {"Prefer": "return=minimal"}
        self.client.post(f"{self.url}/{table}", json=row, headers=headers).raise_for_status()

    def rpc(self, name: str, params: dict) -> object:
        r = self.client.post(f"{self.url}/rpc/{name}", json=params)
        r.raise_for_status()
        return r.json()

    # ---- homes and customers ---------------------------------------------------------------------
    def get_home(self, home_id: str) -> Home:
        if home_id in self.runtime_homes:
            return self.runtime_homes[home_id]
        rows = self._get("homes", {"home_id": f"eq.{home_id}", "select": HOME_COLUMNS})
        if not rows:
            raise KeyError(f"Home {home_id} not found")
        return row_to_home(rows[0])

    def _customer_for_user(self, sub: str, home: Home) -> str:
        rows = self._get("customers", {"auth_user_id": f"eq.{sub}", "select": "customer_id"})
        if rows:
            return rows[0]["customer_id"]
        cid = f"CU-{uuid.uuid4().hex[:10]}"
        self._post("customers", {"customer_id": cid, "auth_user_id": sub, "region": city(home.city).state, "city": home.city,
                                 "income_band": home.income_band, "consent_energy_data": True})
        return cid

    def put_home(self, home: Home, owner: Optional[str] = None, source: str = "api") -> None:
        self.runtime_homes[home.home_id] = home
        c = city(home.city)
        row = home.model_dump(exclude={"monthly_kwh", "has_retrofit_history"})
        row.update({"kwh_24m": _last12_to_24(home.monthly_kwh) if home.monthly_kwh else None, "state": c.state, "zone": c.zone,
                    "lat": c.lat, "lon": c.lon, "source": source})
        if owner:
            row["customer_id"] = self._customer_for_user(owner, home)
        self._post("homes", row, upsert=True)

    def owner_of(self, home_id: str) -> Optional[str]:
        rows = self._get("homes", {"home_id": f"eq.{home_id}", "select": "customer_id,customers(auth_user_id)"})
        if not rows or not rows[0].get("customers"):
            return None
        return rows[0]["customers"].get("auth_user_id")

    def homes_of(self, sub: str) -> list[dict]:
        rows = self._get("customers", {"auth_user_id": f"eq.{sub}", "select": "homes(home_id,city,dwelling_type)"})
        return [h for r in rows for h in (r.get("homes") or [])]

    def customer_for_home(self, home_id: str) -> Optional[dict]:
        rows = self._get("homes", {"home_id": f"eq.{home_id}", "select": "customers(*)"})
        return rows[0]["customers"] if rows and rows[0].get("customers") else None

    # ---- memory ------------------------------------------------------------------------------------
    def memory_for(self, customer_id: str) -> list[dict]:
        rows = self._get("memory", {"customer_id": f"eq.{customer_id}", "select": "*", "order": "created_at.asc"})
        for r in rows:
            r["value"] = json.dumps(r["value"])  # same shape as LocalRepo (JSON-encoded string)
        return rows

    def add_memory(self, customer_id: str, item: dict) -> None:
        self._post("memory", {"customer_id": customer_id, "home_id": item.get("home_id"), "kind": item["kind"], "key": item["key"],
                              "value": json.loads(item["value"]) if isinstance(item["value"], str) else item["value"]})

    # ---- operations ----------------------------------------------------------------------------------
    def log_advisor(self, row: dict) -> None:
        self._post("advisor_logs", row)

    def get_telegram_link(self, chat_id: int) -> Optional[dict]:
        rows = self._get("telegram_links", {"chat_id": f"eq.{chat_id}", "select": "*"})
        return rows[0] if rows else None

    def save_telegram_link(self, chat_id: int, home_id: Optional[str], language: str) -> None:
        self._post("telegram_links", {"chat_id": chat_id, "home_id": home_id, "language": language}, upsert=True)

    def save_bill_upload(self, home_id: Optional[str], image: bytes, mime: str, parsed: dict) -> dict:
        ext = {"image/png": "png", "image/webp": "webp", "application/pdf": "pdf"}.get(mime, "jpg")
        path = f"{home_id or 'unlinked'}/{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:6]}.{ext}"
        r = self.client.post(f"{self.storage}/object/bills/{path}", content=image,
                             headers={**self.h, "Content-Type": mime, "x-upsert": "false"})
        r.raise_for_status()
        self._post("bill_uploads", {"home_id": home_id, "storage_path": f"bills/{path}", "provider": parsed.get("provider"),
                                    "parsed": {k: v for k, v in parsed.items() if k != "provider"}, "warnings": parsed.get("warnings", [])})
        return {"storage_path": f"bills/{path}"}

    # ---- portfolio -----------------------------------------------------------------------------------
    def portfolio(self, name: str, **params) -> object:
        args = {f"p_{k}": v for k, v in params.items() if v is not None}
        return self.rpc(PORTFOLIO_RPC[name], args)

    # ---- real public data layer (schema realdata, migrations 012-019) ---------------------------------
    REAL_RPC = {"sources": ("real_sources", ()), "state_profile": ("real_state_profile", ("state",)),
                "city_climate": ("real_city_climate", ("city",)), "home_weather": ("real_home_weather", ("home_id",)),
                "synth_vs_real": ("real_synth_vs_real", ())}

    def real(self, name: str, **params) -> object:
        fn, keys = self.REAL_RPC[name]
        return self.rpc(fn, {f"p_{k}": params[k] for k in keys})

    def save_score(self, row: dict) -> None:
        self._post("home_scores", row, upsert=True)
