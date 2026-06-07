"""Tests for TavilyProvider (src/providers/tavily_provider.py)."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from src.providers.cache import cache_path
from src.providers.tavily_provider import TavilyProvider, _age_days, _QUERY_META


# ── helpers ──────────────────────────────────────────────────────────────────

def _raw(title="Title", url="http://x.com", content="Snippet", published_date="2026-01-01"):
    return {"title": title, "url": url, "content": content, "published_date": published_date}


REQUIRED_KEYS = {"category", "title", "url", "snippet", "published_date", "age_days"}

PERSON_SPECIFIC_COUNT = sum(1 for _, _, ps in _QUERY_META if ps)
ACCOUNT_QUERY_COUNT = len(_QUERY_META) - PERSON_SPECIFIC_COUNT  # 4


# ── _age_days unit tests ──────────────────────────────────────────────────────

def test_age_days_none_when_missing():
    assert _age_days(None) is None


def test_age_days_none_when_invalid():
    assert _age_days("not-a-date") is None


def test_age_days_positive_for_past_date():
    result = _age_days("2020-01-01")
    assert isinstance(result, int) and result > 0


def test_age_days_zero_for_today():
    from datetime import date
    today = date.today().isoformat()
    assert _age_days(today) == 0


# ── query count tests ─────────────────────────────────────────────────────────

def test_account_mode_drops_person_queries(tmp_path):
    """With no prospect_name, only 4 company-level queries should run."""
    with patch("src.providers.tavily_provider._run_with_backoff", return_value=[_raw()]) as mock_run:
        provider = TavilyProvider(cache_dir=tmp_path)
        provider.search(None, "Acme Corp")
    assert mock_run.call_count == ACCOUNT_QUERY_COUNT


def test_personalized_mode_runs_all_queries(tmp_path):
    """With a prospect_name, all 6 queries should run."""
    with patch("src.providers.tavily_provider._run_with_backoff", return_value=[_raw()]) as mock_run:
        provider = TavilyProvider(cache_dir=tmp_path)
        provider.search("Alice Smith", "Acme Corp")
    assert mock_run.call_count == len(_QUERY_META)


# ── cache tests ───────────────────────────────────────────────────────────────

def test_cache_hit_skips_api(tmp_path):
    """Pre-populated cache entries should be returned without calling Tavily."""
    provider = TavilyProvider(cache_dir=tmp_path)
    # Pre-populate cache for all 4 account-mode queries
    for template, _, person_specific in _QUERY_META:
        if person_specific:
            continue
        query = template.format(prospect_name="", company_name="Acme Corp")
        p = cache_path(f"tavily:{query}", cache_dir=tmp_path)
        p.write_text(json.dumps([_raw(title="Cached")]), encoding="utf-8")

    with patch("src.providers.tavily_provider._run_with_backoff") as mock_run:
        results = provider.search(None, "Acme Corp")

    mock_run.assert_not_called()
    assert all(r["title"] == "Cached" for r in results)


# ── partial failure test ──────────────────────────────────────────────────────

def test_partial_failure_proceeds(tmp_path):
    """A single query failure should not abort; other queries return results."""
    good = [_raw(title="Good")]
    side_effects = [Exception("rate limit")] + [good] * (len(_QUERY_META) - 1)
    with patch("src.providers.tavily_provider._run_with_backoff", side_effect=side_effects):
        provider = TavilyProvider(cache_dir=tmp_path)
        results = provider.search("Alice Smith", "Acme Corp")

    # 5 successful queries × 1 result each
    assert len(results) == len(_QUERY_META) - 1
    assert all(r["title"] == "Good" for r in results)


# ── schema / normalization tests ──────────────────────────────────────────────

def test_normalized_schema(tmp_path):
    """Every returned source must have the full required schema."""
    with patch("src.providers.tavily_provider._run_with_backoff", return_value=[_raw()]):
        provider = TavilyProvider(cache_dir=tmp_path)
        results = provider.search("Alice Smith", "Acme Corp")

    assert results, "expected at least one result"
    for r in results:
        assert REQUIRED_KEYS <= set(r.keys()), f"missing keys in {r}"


def test_age_days_populated_in_results(tmp_path):
    """age_days must be an int (not None) when published_date is provided."""
    with patch("src.providers.tavily_provider._run_with_backoff", return_value=[_raw(published_date="2026-01-01")]):
        provider = TavilyProvider(cache_dir=tmp_path)
        results = provider.search("Alice Smith", "Acme Corp")

    assert all(isinstance(r["age_days"], int) for r in results)


def test_missing_published_date_gives_none_age_days(tmp_path):
    """Results with no published_date should have age_days=None."""
    raw_no_date = {"title": "T", "url": "http://x", "content": "C"}
    with patch("src.providers.tavily_provider._run_with_backoff", return_value=[raw_no_date]):
        provider = TavilyProvider(cache_dir=tmp_path)
        results = provider.search("Alice Smith", "Acme Corp")

    assert all(r["age_days"] is None for r in results)


def test_categories_correct_in_personalized_mode(tmp_path):
    """Each result's category must match the query that produced it."""
    expected_categories = [cat for _, cat, _ in _QUERY_META]  # all 6
    with patch("src.providers.tavily_provider._run_with_backoff", return_value=[_raw()]):
        provider = TavilyProvider(cache_dir=tmp_path)
        results = provider.search("Alice Smith", "Acme Corp")

    actual_cats = [r["category"] for r in results]
    assert actual_cats == expected_categories
