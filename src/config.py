"""Central config: secrets + tunables. See architecture.md §14."""
from __future__ import annotations
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── Secrets (Phase 0: fill .env) ───────────────────────────────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# ── Models — Gemini (free tier via AI Studio) ──────────────────────────────
# gemini-2.5-flash: primary (works when not under extreme load)
# gemini-2.5-flash-lite: cascade fallback when primary daily quota exhausted
MODEL_EXTRACT  = os.getenv("MODEL_EXTRACT",  "gemini-2.5-flash")
MODEL_SCORE    = os.getenv("MODEL_SCORE",    "gemini-2.5-flash")
MODEL_HOOK     = os.getenv("MODEL_HOOK",     "gemini-2.5-flash")
MODEL_DRAFT    = os.getenv("MODEL_DRAFT",    "gemini-2.5-flash")
MODEL_CLASSIFY = os.getenv("MODEL_CLASSIFY", "gemini-2.5-flash")

# ── Tunables ───────────────────────────────────────────────────────────────
FRESH_DAYS = 90              # > this => stale
VERY_STALE_DAYS = 180       # > this => very_stale
FUNDING_WINDOW_DAYS = 60    # funding within this => high-intent
NEW_ROLE_DAYS = 90          # role started within this => new_role
SENSITIVE_WINDOW_DAYS = 180
NUM_QUERIES = 6
MAX_SIGNALS_SHOWN = 5

# ── Paths ──────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = Path(os.getenv("CACHE_DIR", ROOT / "cache"))


def missing_keys() -> list[str]:
    """Return names of secrets that are not set (for a Settings/health banner)."""
    pairs = {
        "GEMINI_API_KEY": GEMINI_API_KEY,
        "TAVILY_API_KEY": TAVILY_API_KEY,
        "SUPABASE_URL": SUPABASE_URL,
        "SUPABASE_KEY": SUPABASE_KEY,
    }
    return [k for k, v in pairs.items() if not v]
