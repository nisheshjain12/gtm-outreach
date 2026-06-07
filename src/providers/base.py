"""Research provider interface (architecture.md §2).

Swappable so future providers (LinkedIn, Crunchbase, News) can be added.
MVP implements TavilyProvider only.
"""
from __future__ import annotations
from typing import Optional, Protocol


class ResearchProvider(Protocol):
    def search(self, prospect_name: Optional[str], company: str) -> list[dict]:
        """Return normalized sources:
        [{category, title, url, snippet, published_date, age_days}]"""
        ...
