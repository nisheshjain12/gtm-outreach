"""Per-query read-through cache (architecture.md §7).

Reused on account_collision (reuse prior sources) and makes demos
deterministic/offline. Wrap every Tavily/Claude call in cached().
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Optional

from src.config import CACHE_DIR


def _hash(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:24]


def cache_path(key: str, cache_dir: Optional[Path] = None) -> Path:
    return Path(cache_dir or CACHE_DIR) / f"{_hash(key)}.json"


def cached(key: str, fn: Callable[[], Any], cache_dir: Optional[Path] = None) -> Any:
    """Return cached JSON for `key`; otherwise call fn(), persist, and return it."""
    d = Path(cache_dir or CACHE_DIR)
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{_hash(key)}.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    result = fn()
    p.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result
