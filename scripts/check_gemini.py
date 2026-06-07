"""Smoke test: verify Gemini API key works and returns valid JSON.

Run:
    .\.venv\Scripts\python.exe scripts\check_gemini.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.llm.client import call_json, extract_signals  # noqa: E402
from src import config  # noqa: E402


def main() -> int:
    print(f"GEMINI_API_KEY set: {'yes' if config.GEMINI_API_KEY else 'NO'}")
    print(f"Models: extract={config.MODEL_EXTRACT}, classify={config.MODEL_CLASSIFY}")

    # Basic call_json
    print("\n[1] Basic call_json (gemini-2.0-flash)...")
    result = call_json(config.MODEL_EXTRACT, 'Return ONLY JSON: {"status": "ok", "value": 42}')
    assert result.get("status") == "ok", f"unexpected: {result}"
    print(f"    OK: {result}")

    # Lightweight classify model
    print(f"\n[2] Lightweight model ({config.MODEL_CLASSIFY})...")
    result2 = call_json(config.MODEL_CLASSIFY, 'Return ONLY JSON: {"ping": true}')
    assert result2.get("ping") is True, f"unexpected: {result2}"
    print(f"    OK: {result2}")

    # Real signal extraction with minimal stub research
    print("\n[3] extract_signals with stub research...")
    stub_research = json.dumps([{
        "title": "Perplexity AI raises $500M Series B",
        "url": "https://example.com/perplexity-funding",
        "snippet": "Perplexity AI announced a $500M Series B led by SoftBank.",
        "published_date": "2026-04-10",
        "category": "funding",
    }])
    signals = extract_signals("Aravind Srinivas", "Perplexity AI", stub_research)
    assert "signals" in signals, f"missing 'signals' key: {signals}"
    print(f"    OK: {len(signals['signals'])} signal(s) extracted")
    if signals["signals"]:
        s = signals["signals"][0]
        print(f"    First signal: type={s.get('type')} | {s.get('description','')[:80]}")

    print("\nALL GOOD — Gemini is wired up.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
