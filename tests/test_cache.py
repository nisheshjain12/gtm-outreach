"""Tests for the read-through cache (src/providers/cache.py)."""
import tempfile
from pathlib import Path

from src.providers import cache


def test_cache_read_through():
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        return {"data": "x"}

    with tempfile.TemporaryDirectory() as d:
        r1 = cache.cached("q1", fn, cache_dir=Path(d))
        r2 = cache.cached("q1", fn, cache_dir=Path(d))
        assert r1 == r2 == {"data": "x"}
        assert calls["n"] == 1  # second call served from disk, fn not re-invoked


def test_distinct_keys_distinct_files():
    with tempfile.TemporaryDirectory() as d:
        cache.cached("a", lambda: 1, cache_dir=Path(d))
        cache.cached("b", lambda: 2, cache_dir=Path(d))
        assert cache.cached("a", lambda: 99, cache_dir=Path(d)) == 1
        assert cache.cached("b", lambda: 99, cache_dir=Path(d)) == 2
