"""Tests for the deterministic edge-flag logic (src/edges/checks.py)."""
from datetime import date

from src.edges import checks

TODAY = date(2026, 6, 7)


def test_funding_within_window():
    sigs = [{"type": "funding", "published_date": "2026-05-20"}]
    assert checks.detect_funding_round(sigs, today=TODAY) is True


def test_funding_outside_window():
    sigs = [{"type": "funding", "published_date": "2026-01-01"}]
    assert checks.detect_funding_round(sigs, today=TODAY) is False


def test_new_role_within_window():
    sigs = [{"type": "new_role", "published_date": "2026-04-01"}]
    assert checks.detect_new_role(sigs, today=TODAY) is True


def test_freshness_buckets():
    assert checks.compute_freshness([{"published_date": "2026-06-01"}], today=TODAY) == "fresh"
    assert checks.compute_freshness([{"published_date": "2026-02-01"}], today=TODAY) == "stale"
    assert checks.compute_freshness([{"published_date": "2025-06-01"}], today=TODAY) == "very_stale"
    assert checks.compute_freshness([], today=TODAY) == "fresh"  # empty handled by no_signal


def test_flags_compose():
    sigs = [
        {"type": "funding", "published_date": "2026-05-20"},
        {"type": "other", "published_date": "2026-05-20", "is_sensitive": True},
    ]
    out = checks.compute_flags(sigs, mode="personalized", account_collision=True, today=TODAY)
    assert "funding_round" in out["flags"]
    assert "sensitive_news" in out["flags"]
    assert "account_collision" in out["flags"]
    assert out["signal_freshness"] == "fresh"
    # priority order: funding before sensitive before account_collision
    assert out["flags"].index("funding_round") < out["flags"].index("sensitive_news")


def test_account_mode_triggers_no_signal():
    out = checks.compute_flags([], mode="account", today=TODAY)
    assert "no_signal" in out["flags"]


def test_stale_flag_set_when_old():
    out = checks.compute_flags([{"type": "other", "published_date": "2026-01-01"}], today=TODAY)
    assert "stale_signals" in out["flags"]


def test_framing_directive_for_funding():
    d = checks.build_framing_directive(["funding_round"])
    assert "High-intent" in d


def test_framing_directive_default():
    assert "Standard personalized" in checks.build_framing_directive([])


def test_company_key_normalization():
    # legal suffix stripped -> "Ramp Inc." matches "ramp"
    assert checks.normalize_company_key("Ramp Inc.") == checks.normalize_company_key("ramp")
    assert checks.normalize_company_key("Notion") == "notion"
    assert checks.normalize_company_key("") == ""
