"""Deterministic edge-flag logic. Pure functions, no API calls (architecture.md §5.1/§5.2).

The LLM never does date math or DB lookups — these checks do.
"""
from __future__ import annotations
import re
from datetime import date, datetime
from typing import Optional

from src.config import (
    FRESH_DAYS,
    VERY_STALE_DAYS,
    FUNDING_WINDOW_DAYS,
    NEW_ROLE_DAYS,
)

# Display/priority order for flags (architecture.md §5.2)
PRIORITY = [
    "funding_round",
    "new_role",
    "ambiguous_name",
    "sensitive_news",
    "stale_signals",
    "account_collision",
    "no_signal",
]

# Conservative legal suffixes only (avoid over-collapsing brand names)
_SUFFIXES = {
    "inc", "llc", "ltd", "corp", "co", "gmbh", "plc", "sa", "ag",
    "limited", "incorporated", "company",
}


def parse_age_days(published_date: Optional[str], today: Optional[date] = None) -> Optional[int]:
    """Days between published_date (YYYY-MM-DD...) and today; None if unparseable."""
    if not published_date:
        return None
    today = today or date.today()
    try:
        d = datetime.strptime(str(published_date)[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None
    return (today - d).days


def signal_age(sig: dict, today: Optional[date] = None) -> Optional[int]:
    """Prefer an explicit age_days, else derive from published_date."""
    if sig.get("age_days") is not None:
        return sig["age_days"]
    return parse_age_days(sig.get("published_date"), today)


def compute_freshness(
    signals: list[dict],
    today: Optional[date] = None,
    fresh: int = FRESH_DAYS,
    very_stale: int = VERY_STALE_DAYS,
) -> str:
    """'fresh' | 'stale' | 'very_stale' based on the youngest dated signal."""
    ages = [a for s in signals if (a := signal_age(s, today)) is not None]
    if not ages:
        return "fresh"  # can't prove staleness with no dates; no_signal handles emptiness
    youngest = min(ages)
    if youngest <= fresh:
        return "fresh"
    if youngest <= very_stale:
        return "stale"
    return "very_stale"


def detect_funding_round(signals, today=None, window: int = FUNDING_WINDOW_DAYS) -> bool:
    for s in signals:
        if s.get("type") == "funding":
            age = signal_age(s, today)
            if age is not None and age <= window:
                return True
    return False


def detect_new_role(signals, today=None, window: int = NEW_ROLE_DAYS) -> bool:
    for s in signals:
        if s.get("type") in ("new_role", "leadership_hire"):
            age = signal_age(s, today)
            if age is not None and age <= window:
                return True
    return False


def compute_flags(
    signals: list[dict],
    *,
    mode: str = "personalized",
    account_collision: bool = False,
    ambiguous_name: bool = False,
    today: Optional[date] = None,
) -> dict:
    """Assemble deterministic flags + freshness. LLM-judgment flags
    (ambiguous_name) are passed in. Returns {flags, signal_freshness}."""
    freshness = compute_freshness(signals, today)
    found = set()
    if detect_funding_round(signals, today):
        found.add("funding_round")
    if detect_new_role(signals, today):
        found.add("new_role")
    if any(s.get("is_sensitive") for s in signals):
        found.add("sensitive_news")
    if freshness != "fresh":
        found.add("stale_signals")
    if account_collision:
        found.add("account_collision")
    if mode == "account" or len(signals) == 0:
        found.add("no_signal")
    if ambiguous_name:
        found.add("ambiguous_name")
    return {
        "flags": [f for f in PRIORITY if f in found],
        "signal_freshness": freshness,
    }


def build_framing_directive(
    flags: list[str],
    *,
    role: Optional[str] = None,
    account_n: Optional[int] = None,
    account_m: Optional[int] = None,
    prior_hooks: Optional[list[str]] = None,
) -> str:
    """Compose the draft framing directive from active flags (architecture.md §5.2)."""
    parts: list[str] = []
    if "funding_round" in flags:
        parts.append("High-intent: lead with the round; be direct and action-oriented; "
                     "reference the post-raise build-out window.")
    if "new_role" in flags:
        parts.append("Open with genuine congratulations on the move; speak to early-tenure priorities.")
    if "sensitive_news" in flags:
        parts.append("Avoid the sensitive topic entirely; lead with the safe angle.")
    if "stale_signals" in flags:
        parts.append("Most recent signal is dated — use forward-looking, hedged framing "
                     "('given where you were heading, I imagine you're now focused on...'); "
                     "do NOT cite stale specifics as if fresh.")
    if "account_collision" in flags:
        ph = "; ".join(prior_hooks or []) or "(none recorded)"
        parts.append(f"Person {account_n or '?'} of {account_m or '?'} at this account. "
                     f"Emphasize the angle for their function ({role or 'their role'}); "
                     f"do NOT reuse these prior hooks: {ph}.")
    if "no_signal" in flags:
        parts.append("Limited/no personal info — keep it company-level and honest; "
                     "don't imply personal research.")
    if not parts:
        parts.append("Standard personalized outreach grounded in the chosen signal.")
    return " ".join(parts)


def normalize_company_key(company: Optional[str]) -> str:
    """Normalize a company name/domain into a stable key for account-collision lookup."""
    if not company:
        return ""
    s = company.strip().lower()
    s = re.sub(r"^https?://", "", s)
    s = s.split("/")[0]
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    tokens = [t for t in s.split() if t and t not in _SUFFIXES]
    return "".join(tokens) if tokens else re.sub(r"[^a-z0-9]", "", company.lower())
