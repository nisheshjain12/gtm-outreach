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


@lru_cache(maxsize=8)
def _get_client(api_key: str) -> genai.Client:
    return genai.Client(api_key=api_key)


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


def _raw_call(client: genai.Client, model_name: str, prompt: str) -> str:
    """Single Gemini call on a given client; raises on any error."""
    response = client.models.generate_content(
        model=model_name,
        contents=prompt,
        config=_JSON_CONFIG,
    )
    return response.text


def _is_quota_error(exc: Exception | None) -> bool:
    """Any rate/quota rejection (429) — per-minute or per-day."""
    if exc is None:
        return False
    msg = str(exc)
    return "RESOURCE_EXHAUSTED" in msg or "429" in msg


def _is_daily_quota(exc: Exception) -> bool:
    """A per-DAY quota rejection — backoff won't help, fail fast to fallback."""
    return "PerDay" in str(exc)


def _try_key(client: genai.Client, model_name: str, prompt: str):
    """Run the model cascade (flash <-> flash-lite) on ONE key.

    Returns (text, last_exc, should_rotate):
      • text is the response on success, else None
      • should_rotate is True when the failure is a quota error (429) — a
        different key (ideally a different project) has separate quota, so
        rotating helps. A transient server error (503) returns False, since
        another key won't fix a server-side outage.
    """
    last_exc: Exception | None = None
    tried: list[str] = []
    current = model_name

    while current and current not in tried:
        tried.append(current)

        for delay in (0, 5, 15, 30, 60):
            if delay:
                log.info("Gemini backing off %ds [%s]...", delay, current)
                time.sleep(delay)
            try:
                return _raw_call(client, current, prompt), None, False
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                log.warning("Gemini error [%s]: %s", current, str(exc)[:200])
                if _is_daily_quota(exc):
                    break  # daily limit — don't waste the remaining backoff

        if not _is_quota_error(last_exc):
            # Transient server error (503) survived retries — a different model
            # or key won't help. Stop and report it as non-rotatable.
            return None, last_exc, False

        # Quota error on this model — try the partner model on the same key.
        fallback = _FALLBACK_CHAIN.get(current)
        if fallback:
            log.warning("Quota hit on %s — cascading to %s", current, fallback)
        current = fallback  # type: ignore[assignment]

    # Every model on this key is quota-limited — rotate to the next key.
    return None, last_exc, True


def _call_with_backoff(model_name: str, prompt: str) -> str:
    """Call Gemini with per-key model cascade + multi-key rotation.

    For each configured key (config.gemini_api_keys), runs the flash <->
    flash-lite cascade with backoff. When a key is quota-limited across both
    models, rotates to the next key. A transient (503) failure stops early —
    another key won't help a server-side outage.
    """
    keys = config.gemini_api_keys()
    if not keys:
        raise RuntimeError("GEMINI_API_KEY not set — add it to .env")

    last_exc: Exception | None = None
    for idx, api_key in enumerate(keys):
        if idx:
            log.warning("Gemini quota hit — rotating to key #%d of %d", idx + 1, len(keys))
        client = _get_client(api_key)
        text, exc, should_rotate = _try_key(client, model_name, prompt)
        if text is not None:
            return text
        last_exc = exc or last_exc
        if not should_rotate:
            break  # transient/server outage — more keys won't help

    raise RuntimeError(
        f"Gemini failed after retries across {len(keys)} key(s) [{model_name}]: {last_exc}"
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
        max_signals=config.MAX_SIGNALS_EXTRACTED,
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
