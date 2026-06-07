"""Tavily research provider (architecture.md §7).

6 query templates; person-specific queries 1 & 5 dropped in Account mode.
Each query individually cached; exponential backoff (1s,2s,4s; max 3 retries);
partial query failure proceeds with remaining results.
"""
from __future__ import annotations

import logging
import time
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Optional

from tavily import TavilyClient

from src import config
from src.providers.cache import cached

log = logging.getLogger(__name__)

# (template, category, person_specific)
# Queries 1 & 5 are person-specific — dropped in Account mode (no prospect_name).
_QUERY_META: list[tuple[str, str, bool]] = [
    ('"{prospect_name}" {company_name}',                                    "prospect",       True),
    ("{company_name} news 2026",                                            "news",           False),
    ("{company_name} funding OR raised OR Series",                          "funding",        False),
    ('{company_name} hiring OR "is hiring" OR open roles',                  "hiring",         False),
    ('"{prospect_name}" interview OR podcast OR keynote',                   "exec_interview", True),
    ("{company_name} announcement OR launch OR partnership press release",  "press",          False),
]

_MAX_PER_QUERY = 5


@lru_cache(maxsize=1)
def _get_client() -> TavilyClient:
    if not config.TAVILY_API_KEY:
        raise RuntimeError("TAVILY_API_KEY not set")
    return TavilyClient(api_key=config.TAVILY_API_KEY)


def _age_days(published_date: Optional[str]) -> Optional[int]:
    if not published_date:
        return None
    try:
        d = datetime.fromisoformat(str(published_date)[:10]).date()
        return max(0, (date.today() - d).days)
    except (ValueError, TypeError):
        return None


def _normalize(raw: dict, category: str) -> dict:
    pub = raw.get("published_date") or raw.get("published") or None
    return {
        "category": category,
        "title": raw.get("title", ""),
        "url": raw.get("url", ""),
        "snippet": raw.get("content", ""),
        "published_date": pub,
        "age_days": _age_days(pub),
    }


def _run_with_backoff(query: str) -> list[dict]:
    """Search Tavily with up to 3 retries on failure (1s, 2s, 4s backoff)."""
    client = _get_client()
    last_exc: Exception | None = None
    for delay in (0, 1, 2, 4):
        if delay:
            time.sleep(delay)
        try:
            resp = client.search(query, max_results=_MAX_PER_QUERY)
            return resp.get("results", [])
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            log.warning("Tavily retry after %ds — %.60s: %s", delay, query, exc)
    log.error("Tavily gave up on %.60r: %s", query, last_exc)
    return []


class TavilyProvider:
    """Tavily-backed research provider.

    Args:
        cache_dir: Override the default cache directory (useful in tests).
    """

    def __init__(self, cache_dir: Optional[Path] = None) -> None:
        self._cache_dir = cache_dir

    def search(self, prospect_name: Optional[str], company: str) -> list[dict]:
        """Return normalized research sources for a prospect / company.

        In Account mode (prospect_name is None/empty), person-specific queries
        (1 and 5) are silently dropped, leaving 4 company-level queries.

        Each query is served from cache if a prior hit exists; otherwise Tavily
        is called and the result is persisted. A single query's failure does not
        abort the run — partial results are returned and the error is logged.

        Returns:
            List of dicts: {category, title, url, snippet, published_date, age_days}
        """
        account_mode = not prospect_name
        sources: list[dict] = []

        for template, category, person_specific in _QUERY_META:
            if person_specific and account_mode:
                continue

            query = template.format(
                prospect_name=prospect_name or "",
                company_name=company,
            )
            try:
                raw_results: list[dict] = cached(
                    f"tavily:{query}",
                    lambda q=query: _run_with_backoff(q),
                    cache_dir=self._cache_dir,
                )
            except Exception as exc:  # noqa: BLE001
                log.error("Query skipped due to error %.60r: %s", query, exc)
                raw_results = []

            sources.extend(_normalize(r, category) for r in raw_results)

        return sources
