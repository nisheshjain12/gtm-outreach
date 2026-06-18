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


def gemini_api_keys() -> list[str]:
    """All configured Gemini keys, in priority order.

    Sources (de-duplicated, order preserved):
      • GEMINI_API_KEY, GEMINI_API_KEY_2 … GEMINI_API_KEY_5
      • GEMINI_API_KEYS  (comma-separated bundle)

    The LLM client tries each key in turn; when one key's *daily* quota is
    exhausted it rotates to the next. Each key needs its own free-tier
    quota — see the note in .env.example about per-project limits.
    """
    names = ["GEMINI_API_KEY"] + [f"GEMINI_API_KEY_{i}" for i in range(2, 6)]
    keys = [v.strip() for n in names if (v := os.getenv(n))]
    bundle = os.getenv("GEMINI_API_KEYS")
    if bundle:
        keys += [k.strip() for k in bundle.split(",") if k.strip()]
    seen: set[str] = set()
    return [k for k in keys if k and not (k in seen or seen.add(k))]

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

# LLM payload bounds — keep extraction input/output small enough that the
# model returns complete, valid JSON even for high-volume companies (e.g. Meta).
MAX_RESEARCH_SOURCES = 24   # cap sources sent to the LLM (extract/classify)
MAX_SNIPPET_CHARS = 600     # truncate each source snippet sent to the LLM
MAX_SIGNALS_EXTRACTED = 20  # ceiling on extracted signals (bounds output size)

# ── Paths ──────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = Path(os.getenv("CACHE_DIR", ROOT / "cache"))


def missing_keys() -> list[str]:
    pairs = {
        "GEMINI_API_KEY": GEMINI_API_KEY,
        "TAVILY_API_KEY": TAVILY_API_KEY,
        "SUPABASE_URL": SUPABASE_URL,
        "SUPABASE_KEY": SUPABASE_KEY,
    }
    return [k for k, v in pairs.items() if not v]
