"""Phase 7 — Edge-case validation.

Usage:
  # Unit tests only (zero API calls, ~2 seconds):
  .\.venv\Scripts\python.exe scripts\test_edge_cases.py

  # Full pipeline run for one specific flag (uses Gemini + Tavily quota):
  .\.venv\Scripts\python.exe scripts\test_edge_cases.py --flag no_signal
  .\.venv\Scripts\python.exe scripts\test_edge_cases.py --flag account_collision
  .\.venv\Scripts\python.exe scripts\test_edge_cases.py --flag stale_signals
  .\.venv\Scripts\python.exe scripts\test_edge_cases.py --flag funding_round
  .\.venv\Scripts\python.exe scripts\test_edge_cases.py --flag new_role
  .\.venv\Scripts\python.exe scripts\test_edge_cases.py --flag sensitive_news
  .\.venv\Scripts\python.exe scripts\test_edge_cases.py --flag ambiguous_name

Flags:
  no_signal         - company-only run (no prospect name)
  account_collision - same company as a prior completed run
  stale_signals     - company with no recent news (all signals > 90d)
  funding_round     - company that raised funding in last 60 days
  new_role          - prospect who recently changed roles (< 90d)
  sensitive_news    - company with layoffs / lawsuits / controversy
  ambiguous_name    - name that matches multiple distinct people
"""
from __future__ import annotations

import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.edges.checks import compute_flags, build_framing_directive, detect_funding_round, detect_new_role


# ── Deterministic unit tests (no API) ────────────────────────────────────────

def _make_signal(
    sig_type: str,
    age_days: int = 30,
    is_sensitive: bool = False,
    description: str = "test signal",
) -> dict:
    today = date.today()
    pub = (today - timedelta(days=age_days)).isoformat()
    return {
        "id": "sig_01",
        "type": sig_type,
        "description": description,
        "published_date": pub,
        "age_days": age_days,
        "is_sensitive": is_sensitive,
    }


def test_no_signal_account_mode():
    result = compute_flags([], mode="account")
    assert "no_signal" in result["flags"], f"expected no_signal, got {result['flags']}"
    print("PASS  no_signal (account mode, no prospect)")


def test_no_signal_empty_signals():
    result = compute_flags([], mode="personalized")
    assert "no_signal" in result["flags"], f"expected no_signal (empty), got {result['flags']}"
    print("PASS  no_signal (personalized mode, zero signals)")


def test_funding_round_fires():
    sig = _make_signal("funding", age_days=30)
    result = compute_flags([sig], mode="personalized")
    assert "funding_round" in result["flags"], f"expected funding_round, got {result['flags']}"
    print("PASS  funding_round (30d old funding signal)")


def test_funding_round_stale_does_not_fire():
    sig = _make_signal("funding", age_days=90)
    result = compute_flags([sig], mode="personalized")
    assert "funding_round" not in result["flags"], "funding_round should not fire for 90d+ old signal"
    print("PASS  funding_round does NOT fire for 90d-old funding (outside 60d window)")


def test_new_role_fires():
    sig = _make_signal("new_role", age_days=45)
    result = compute_flags([sig], mode="personalized")
    assert "new_role" in result["flags"], f"expected new_role, got {result['flags']}"
    print("PASS  new_role (45d old new_role signal)")


def test_new_role_leadership_hire():
    sig = _make_signal("leadership_hire", age_days=60)
    result = compute_flags([sig], mode="personalized")
    assert "new_role" in result["flags"], f"expected new_role via leadership_hire, got {result['flags']}"
    print("PASS  new_role via leadership_hire type")


def test_stale_signals():
    sig = _make_signal("product_launch", age_days=120)
    result = compute_flags([sig], mode="personalized")
    assert "stale_signals" in result["flags"], f"expected stale_signals, got {result['flags']}"
    assert result["signal_freshness"] == "stale", f"expected stale freshness, got {result['signal_freshness']}"
    print("PASS  stale_signals (120d signal, > 90d threshold)")


def test_fresh_signal_no_stale_flag():
    sig = _make_signal("product_launch", age_days=30)
    result = compute_flags([sig], mode="personalized")
    assert "stale_signals" not in result["flags"], "should not fire stale_signals for fresh signal"
    print("PASS  fresh signal does NOT fire stale_signals")


def test_sensitive_news():
    sig = _make_signal("challenge", age_days=20, is_sensitive=True)
    result = compute_flags([sig], mode="personalized")
    assert "sensitive_news" in result["flags"], f"expected sensitive_news, got {result['flags']}"
    print("PASS  sensitive_news (is_sensitive=True signal)")


def test_account_collision():
    result = compute_flags(
        [_make_signal("product_launch", age_days=20)],
        mode="personalized",
        account_collision=True,
    )
    assert "account_collision" in result["flags"], f"expected account_collision, got {result['flags']}"
    print("PASS  account_collision flag from prior run at same company")


def test_ambiguous_name():
    result = compute_flags(
        [_make_signal("other", age_days=20)],
        mode="personalized",
        ambiguous_name=True,
    )
    assert "ambiguous_name" in result["flags"], f"expected ambiguous_name, got {result['flags']}"
    print("PASS  ambiguous_name flag passed through")


def test_multiple_flags_orthogonal():
    # funding_round requires age <= 60d (freshness stays "fresh"),
    # so stale_signals can't co-fire with it — they are mutually exclusive.
    # Valid co-occurring combo: funding_round + account_collision + sensitive_news
    sigs = [
        _make_signal("funding", age_days=30, is_sensitive=False),
        _make_signal("challenge", age_days=20, is_sensitive=True),
    ]
    result = compute_flags(sigs, mode="personalized", account_collision=True, ambiguous_name=True)
    assert "funding_round" in result["flags"], f"funding_round missing: {result['flags']}"
    assert "account_collision" in result["flags"], f"account_collision missing: {result['flags']}"
    assert "sensitive_news" in result["flags"], f"sensitive_news missing: {result['flags']}"
    assert "ambiguous_name" in result["flags"], f"ambiguous_name missing: {result['flags']}"
    print("PASS  orthogonal flags — funding_round + account_collision + sensitive_news + ambiguous_name")


def test_framing_directive_sensitive():
    directive = build_framing_directive(["sensitive_news"])
    assert "sensitive" in directive.lower() or "avoid" in directive.lower(), \
        f"sensitive framing not in directive: {directive}"
    print("PASS  framing_directive contains sensitive guidance")


def test_framing_directive_funding():
    directive = build_framing_directive(["funding_round"])
    assert "round" in directive.lower() or "funding" in directive.lower(), \
        f"funding framing not in directive: {directive}"
    print("PASS  framing_directive contains funding round guidance")


def test_framing_directive_stale():
    directive = build_framing_directive(["stale_signals"])
    assert "stale" in directive.lower() or "hedge" in directive.lower() or "dated" in directive.lower(), \
        f"stale framing not in directive: {directive}"
    print("PASS  framing_directive contains stale signal guidance")


def run_unit_tests() -> int:
    tests = [
        test_no_signal_account_mode,
        test_no_signal_empty_signals,
        test_funding_round_fires,
        test_funding_round_stale_does_not_fire,
        test_new_role_fires,
        test_new_role_leadership_hire,
        test_stale_signals,
        test_fresh_signal_no_stale_flag,
        test_sensitive_news,
        test_account_collision,
        test_ambiguous_name,
        test_multiple_flags_orthogonal,
        test_framing_directive_sensitive,
        test_framing_directive_funding,
        test_framing_directive_stale,
    ]

    failed = 0
    for t in tests:
        try:
            t()
        except AssertionError as e:
            print(f"FAIL  {t.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"ERROR {t.__name__}: {e}")
            failed += 1

    print()
    if failed == 0:
        print(f"All {len(tests)} unit tests passed.")
    else:
        print(f"{failed}/{len(tests)} unit tests FAILED.")
    return failed


# ── Demo input cheatsheet ────────────────────────────────────────────────────

DEMO_INPUTS: dict[str, dict] = {
    "no_signal": {
        "company":       "Basecamp",
        "prospect_name": "",          # leave blank = account mode
        "role":          "",
        "outreach_goal": "book a discovery call",
        "extra_context": "",
        "note": "No prospect name -> account mode -> no_signal fires automatically.",
    },
    "account_collision": {
        "company":       "Perplexity AI",   # already has completed runs in DB
        "prospect_name": "Denis Yarats",    # different person than prior runs
        "role":          "CTO & Co-founder",
        "outreach_goal": "book a discovery call",
        "extra_context": "",
        "note": "Same company as prior runs -> account_collision fires from DB lookup.",
    },
    "stale_signals": {
        "company":       "Basecamp",
        "prospect_name": "Jason Fried",
        "role":          "CEO",
        "outreach_goal": "book a discovery call",
        "extra_context": "",
        "note": "Basecamp deliberately avoids PR; most signals will be 90d+ old.",
    },
    "funding_round": {
        "company":       "Anthropic",
        "prospect_name": "Dario Amodei",
        "role":          "CEO & Co-founder",
        "outreach_goal": "partner on AI safety tooling",
        "extra_context": "",
        "note": "Anthropic raises frequently; recent round likely within 60d window.",
    },
    "new_role": {
        "company":       "Figma",
        "prospect_name": "Dylan Field",
        "role":          "CEO & Co-founder",
        "outreach_goal": "book a product demo",
        "extra_context": "",
        "note": (
            "If research shows a recent exec change or hire at Figma, "
            "new_role fires. Backup: search for any company with a C-suite "
            "appointment in the last 90 days and use that prospect."
        ),
    },
    "sensitive_news": {
        "company":       "Boeing",
        "prospect_name": "Kelly Ortberg",
        "role":          "CEO",
        "outreach_goal": "sell supply-chain risk software",
        "extra_context": "",
        "note": (
            "Boeing has ongoing quality/safety controversy; "
            "LLM scorer should mark those signals is_sensitive=True -> "
            "sensitive_news fires + framing_directive says 'avoid the sensitive topic'."
        ),
    },
    "ambiguous_name": {
        "company":       "Google",
        "prospect_name": "John Smith",
        "role":          "VP Engineering",
        "outreach_goal": "book a discovery call",
        "extra_context": "",
        "note": (
            "Extremely common name at a large company -> classify LLM returns "
            "ambiguous_name=True with multiple candidate_identities -> "
            "disambiguate interrupt fires."
        ),
    },
}


def print_cheatsheet():
    print()
    print("=" * 62)
    print("DEMO INPUT CHEATSHEET — one reliable input per flag")
    print("=" * 62)
    for flag_name, inp in DEMO_INPUTS.items():
        print(f"\n[{flag_name}]")
        if inp.get("prospect_name"):
            print(f"  Prospect : {inp['prospect_name']}")
        else:
            print(f"  Prospect : (leave blank)")
        print(f"  Company  : {inp['company']}")
        if inp.get("role"):
            print(f"  Role     : {inp['role']}")
        if inp.get("outreach_goal"):
            print(f"  Goal     : {inp['outreach_goal']}")
        if inp.get("extra_context"):
            print(f"  Context  : {inp['extra_context']}")
        print(f"  WHY      : {inp['note']}")


# ── Full pipeline runner for one flag ─────────────────────────────────────────

def _drive_to_completion(graph, thread_cfg: dict, verbose: bool = True) -> dict:
    from langgraph.types import Command

    while True:
        snap = graph.get_state(thread_cfg)
        if not snap.next:
            return snap.values

        node = snap.next[0]
        state = snap.values
        if verbose:
            print(f"  [interrupt] {node}", end=" ")

        if node == "disambiguate":
            candidates = state.get("candidate_identities", [])
            choice = candidates[0] if candidates else {}
            if verbose:
                print(f"-> picking: {choice.get('name', 'first')}")
            graph.invoke(Command(resume=choice), config=thread_cfg)

        elif node == "signal_review":
            signals = state.get("signals", [])
            top = next(
                (s for s in sorted(signals, key=lambda s: s.get("total_score", 0), reverse=True)
                 if not s.get("is_sensitive")),
                signals[0] if signals else None,
            )
            sig_id = top["id"] if top else "sig_01"
            if verbose:
                print(f"-> selecting [{sig_id}]")
            graph.invoke(Command(resume={"signal_id": sig_id, "instructions": ""}), config=thread_cfg)

        elif node == "draft_review":
            if verbose:
                print("-> approving")
            graph.invoke(Command(resume={"action": "approve"}), config=thread_cfg)

        elif node == "approve":
            if verbose:
                print("-> approved")
            graph.invoke(Command(resume={"action": "approve"}), config=thread_cfg)

        else:
            if verbose:
                print(f"-> resuming (unknown: {node})")
            graph.invoke(Command(resume={}), config=thread_cfg)


def run_full_pipeline(flag_name: str) -> int:
    if flag_name not in DEMO_INPUTS:
        print(f"Unknown flag: {flag_name!r}. Choose from: {', '.join(DEMO_INPUTS)}")
        return 1

    inp = DEMO_INPUTS[flag_name]
    print(f"\n=== Full pipeline test: [{flag_name}] ===")
    print(f"Prospect : {inp.get('prospect_name') or '(none)'}")
    print(f"Company  : {inp['company']}")
    print(f"WHY      : {inp['note']}")
    print()

    from src.graph.build import build_graph
    graph = build_graph()
    thread_id = f"edge-{flag_name}-{uuid.uuid4().hex[:6]}"
    cfg = {"configurable": {"thread_id": thread_id}}

    initial = {
        "company":          inp["company"],
        "prospect_name":    inp.get("prospect_name") or None,
        "role":             inp.get("role") or None,
        "outreach_goal":    inp.get("outreach_goal", "book a discovery call"),
        "extra_context":    inp.get("extra_context") or None,
    }

    print("[1] Invoking pipeline...")
    graph.invoke(initial, config=cfg)

    print("[2] Driving through interrupts...")
    final = _drive_to_completion(graph, cfg)

    flags     = final.get("flags", [])
    freshness = final.get("signal_freshness")
    signals   = final.get("signals", [])
    status    = final.get("status")
    framing   = final.get("framing_directive", "")

    print()
    print(f"  Status    : {status}")
    print(f"  Flags     : {flags}")
    print(f"  Freshness : {freshness}")
    print(f"  Signals   : {len(signals)} extracted")
    print(f"  Framing   : {framing[:120]}{'...' if len(framing) > 120 else ''}")
    print()

    hit = flag_name in flags
    if hit:
        print(f"PASS  [{flag_name}] fired as expected.")
    else:
        print(f"WARN  [{flag_name}] did NOT fire. Got flags: {flags}")
        print(f"      (Check Tavily results for the expected signal type.)")
    return 0 if hit else 1


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> int:
    args = sys.argv[1:]

    if "--flag" in args:
        idx = args.index("--flag")
        flag_name = args[idx + 1] if idx + 1 < len(args) else ""
        return run_full_pipeline(flag_name)

    # Default: unit tests + cheatsheet
    print("=== Phase 7 — Edge Case Unit Tests ===")
    print()
    failed = run_unit_tests()
    print_cheatsheet()
    return failed


if __name__ == "__main__":
    raise SystemExit(main())
