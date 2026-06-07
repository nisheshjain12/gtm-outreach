"""Gemini LLM client (architecture.md §8, §14).

Uses google-genai SDK (the new, non-deprecated package).
Responsibilities:
- call_json(model, prompt) → dict  with backoff + one JSON-repair retry
- per-stage helpers that fill templates from src.llm.prompts
"""
from __future__ import annotations

import json
import logging
import time
from functools import lru_cache
from typing import Optional

from google import genai
from google.genai import types

from src import config
from src.llm import prompts

log = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _get_client() -> genai.Client:
    if not config.GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY not set — add it to .env")
    return genai.Client(api_key=config.GEMINI_API_KEY)


_JSON_CONFIG = types.GenerateContentConfig(
    response_mime_type="application/json",
)

# Model cascade: on daily quota exhaustion, try the partner model.
# Both gemini-2.5-flash and gemini-2.5-flash-lite have ~20 req/day free tier
# but independent per-model quotas, so exhausting one leaves the other usable.
_FALLBACK_CHAIN: dict[str, str] = {
    "gemini-2.5-flash":      "gemini-2.5-flash-lite",
    "gemini-2.5-flash-lite": "gemini-2.5-flash",
}


def _raw_call(model_name: str, prompt: str) -> str:
    """Single Gemini call; raises on any error."""
    client = _get_client()
    response = client.models.generate_content(
        model=model_name,
        contents=prompt,
        config=_JSON_CONFIG,
    )
    return response.text


def _is_daily_quota_exhausted(exc: Exception) -> bool:
    msg = str(exc)
    return "RESOURCE_EXHAUSTED" in msg and "PerDay" in msg


def _call_with_backoff(model_name: str, prompt: str) -> str:
    """Call Gemini with backoff + model cascade on daily quota exhaustion.

    Transient errors (503, per-minute 429): retry with (0,5,15,30,60)s backoff.
    Daily quota exhaustion: immediately cascade to fallback model, no point sleeping.
    """
    last_exc: Exception | None = None
    tried: list[str] = []
    current = model_name

    while current and current not in tried:
        tried.append(current)
        daily_exhausted = False

        for delay in (0, 5, 15, 30, 60):
            if delay:
                log.info("Gemini backing off %ds [%s]...", delay, current)
                time.sleep(delay)
            try:
                return _raw_call(current, prompt)
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                log.warning("Gemini error [%s]: %s", current, str(exc)[:200])
                if _is_daily_quota_exhausted(exc):
                    daily_exhausted = True
                    break  # no point retrying; jump to fallback

        if not daily_exhausted:
            break  # all retries exhausted for a transient error

        fallback = _FALLBACK_CHAIN.get(current)
        if fallback:
            log.warning("Daily quota exhausted for %s — cascading to %s", current, fallback)
        current = fallback  # type: ignore[assignment]

    raise RuntimeError(
        f"Gemini failed after retries [{model_name}]: {last_exc}"
    ) from last_exc


def call_json(model_name: str, prompt: str) -> dict:
    """Call Gemini and return parsed JSON. One repair-retry on parse failure."""
    raw = _call_with_backoff(model_name, prompt)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        log.warning("JSON parse failed, attempting repair...")
        repair = (
            "The following is malformed JSON. Return ONLY the corrected, valid JSON "
            "with no extra text or markdown:\n" + raw
        )
        repaired = _call_with_backoff(model_name, repair)
        return json.loads(repaired)  # raises if still broken


# ── Per-stage helpers ────────────────────────────────────────────────────────

def extract_signals(
    prospect_name: Optional[str],
    company_name: str,
    research_json: str,
    extra_context: str = "",
) -> dict:
    prompt = prompts.EXTRACT.format(
        prospect_name=prospect_name or "(none — account mode)",
        company_name=company_name,
        extra_context=extra_context or "(none)",
        research_json=research_json,
    )
    return call_json(config.MODEL_EXTRACT, prompt)


def score_signals(
    signals_json: str,
    today: str,
    prospect_name: Optional[str],
    role: Optional[str],
    company_name: str,
) -> dict:
    prompt = prompts.SCORE.format(
        signals_json=signals_json,
        today=today,
        prospect_name=prospect_name or "(none)",
        role=role or "Unknown",
        company_name=company_name,
    )
    return call_json(config.MODEL_SCORE, prompt)


def select_hook(
    selected_signal_json: str,
    other_signals_json: str,
    flag_rules: str,
    user_instructions: str,
    prospect_name: Optional[str],
    company_name: str,
    outreach_goal: str,
) -> dict:
    prompt = prompts.HOOK.format(
        selected_signal_json=selected_signal_json,
        other_signals_json=other_signals_json,
        flag_rules=flag_rules,
        user_instructions=user_instructions or "(none)",
        prospect_name=prospect_name or "(company-level)",
        company_name=company_name,
        outreach_goal=outreach_goal or "book a discovery call",
    )
    return call_json(config.MODEL_HOOK, prompt)


def generate_draft(
    hook_json: str,
    prospect_name: Optional[str],
    role: Optional[str],
    company_name: str,
    product_description: str,
    outreach_goal: str,
    framing_directive: str,
    user_instructions: str = "",
) -> dict:
    prompt = prompts.DRAFT.format(
        hook_json=hook_json,
        prospect_name=prospect_name or "(company-level)",
        role=role or "Decision Maker",
        company_name=company_name,
        product_description=product_description,
        outreach_goal=outreach_goal or "book a discovery call",
        framing_directive=framing_directive,
        user_instructions=user_instructions or "(none)",
    )
    return call_json(config.MODEL_DRAFT, prompt)


def classify_edges(
    prospect_name: Optional[str],
    company_name: str,
    research_json: str,
) -> dict:
    prompt = prompts.CLASSIFY.format(
        prospect_name=prospect_name or "(none)",
        company_name=company_name,
        research_json=research_json,
    )
    return call_json(config.MODEL_CLASSIFY, prompt)
