"""Supabase persistence (architecture.md §11).

REST client via supabase-py (URL + key). Helpers used by graph nodes and the UI.
"""
from __future__ import annotations
from datetime import datetime, timezone
from functools import lru_cache
from typing import Optional

from supabase import Client, create_client

from src import config


@lru_cache(maxsize=1)
def get_client() -> Client:
    if not config.SUPABASE_URL or not config.SUPABASE_KEY:
        raise RuntimeError("Supabase not configured — set SUPABASE_URL/SUPABASE_KEY in .env")
    return create_client(config.SUPABASE_URL, config.SUPABASE_KEY)


def ping() -> bool:
    """Lightweight connectivity check (requires schema applied)."""
    get_client().table("seller_profile").select("id").limit(1).execute()
    return True


# ── Seller Profile (single row, D12) ────────────────────────────────────────
def get_seller_profile() -> Optional[dict]:
    res = get_client().table("seller_profile").select("*").eq("id", 1).limit(1).execute()
    return res.data[0] if res.data else None


def save_seller_profile(profile: dict) -> dict:
    payload = {"id": 1, "updated_at": datetime.now(timezone.utc).isoformat(), **profile}
    res = get_client().table("seller_profile").upsert(payload).execute()
    return res.data[0] if res.data else {}


# ── Runs ────────────────────────────────────────────────────────────────────
def create_run(data: dict) -> str:
    res = get_client().table("runs").insert(data).execute()
    return res.data[0]["id"]


def update_run(run_id: str, fields: dict) -> None:
    get_client().table("runs").update(fields).eq("id", run_id).execute()


def find_runs_by_company(company_key: str) -> list[dict]:
    """Powers account_collision."""
    res = (
        get_client().table("runs").select("*")
        .eq("company_key", company_key).order("created_at", desc=True).execute()
    )
    return res.data or []


def list_runs(limit: int = 100) -> list[dict]:
    res = (
        get_client().table("runs").select("*")
        .order("created_at", desc=True).limit(limit).execute()
    )
    return res.data or []


def get_run(run_id: str) -> Optional[dict]:
    res = get_client().table("runs").select("*").eq("id", run_id).limit(1).execute()
    return res.data[0] if res.data else None


# ── Child records ────────────────────────────────────────────────────────────
def _insert_rows(table: str, run_id: str, rows: list[dict]) -> None:
    if not rows:
        return
    get_client().table(table).insert([{**r, "run_id": run_id} for r in rows]).execute()


def save_sources(run_id: str, sources: list[dict]) -> None:
    _insert_rows("research_sources", run_id, sources)


def save_signals(run_id: str, signals: list[dict]) -> None:
    _insert_rows("signals", run_id, signals)


def save_hook(run_id: str, hook: dict) -> None:
    _insert_rows("hooks", run_id, [hook])


def save_drafts(run_id: str, drafts: list[dict]) -> None:
    _insert_rows("drafts", run_id, drafts)


def log_action(run_id: str, stage: str, action: str, payload: Optional[dict] = None) -> None:
    _insert_rows("human_actions", run_id, [{"stage": stage, "action": action, "payload": payload}])


# ── Read helpers (Dashboard) ──────────────────────────────────────────────────

def get_signals(run_id: str) -> list[dict]:
    res = (
        get_client().table("signals").select("*")
        .eq("run_id", run_id).order("total_score", desc=True).execute()
    )
    return res.data or []


def get_hooks(run_id: str) -> list[dict]:
    res = get_client().table("hooks").select("*").eq("run_id", run_id).execute()
    return res.data or []


def get_drafts(run_id: str) -> list[dict]:
    res = get_client().table("drafts").select("*").eq("run_id", run_id).execute()
    return res.data or []


def get_actions(run_id: str) -> list[dict]:
    res = (
        get_client().table("human_actions").select("*")
        .eq("run_id", run_id).order("created_at", desc=False).execute()
    )
    return res.data or []


def get_sources(run_id: str) -> list[dict]:
    res = (
        get_client().table("research_sources").select("*")
        .eq("run_id", run_id).order("age_days", desc=False).execute()
    )
    return res.data or []


def mark_stale_runs_failed(minutes: int = 15) -> int:
    """Mark runs stuck in 'researching' for longer than `minutes` as 'failed'.

    Runs in progress for <15 min are left alone to avoid clobbering active runs.
    Returns the number of rows updated.
    """
    from datetime import datetime, timedelta, timezone
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()
    res = (
        get_client().table("runs")
        .update({"status": "failed"})
        .eq("status", "researching")
        .lt("created_at", cutoff)
        .execute()
    )
    return len(res.data or [])
