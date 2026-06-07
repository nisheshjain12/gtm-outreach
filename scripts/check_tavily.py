"""Smoke test: verify Tavily API returns real results.

Run:
    .\.venv\Scripts\python.exe scripts\check_tavily.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.providers.tavily_provider import TavilyProvider  # noqa: E402


def main() -> int:
    p = TavilyProvider()
    print("Running personalized search (Aravind Srinivas / Perplexity AI)...")
    results = p.search("Aravind Srinivas", "Perplexity AI")
    print(f"  Got {len(results)} sources")
    for r in results[:4]:
        cat = r["category"]
        age = r["age_days"]
        title = r["title"][:65]
        print(f"  [{cat}] age={age}d  {title}")

    print()
    print("Running account-mode search (company only — Perplexity AI)...")
    acc = p.search(None, "Perplexity AI")
    print(f"  Got {len(acc)} sources (expected <=20 from 4 queries)")

    if results and acc:
        print("\nALL GOOD — Tavily is wired up.")
        return 0
    print("\nWARNING: one or both searches returned 0 results.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
