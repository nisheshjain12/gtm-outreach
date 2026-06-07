"""Headless end-to-end pipeline test — Phase 4 happy-path milestone.

Drives all 4 interrupt nodes programmatically and verifies a complete run
is stored in Supabase. Uses real Tavily + Gemini APIs (cached after first run).

Run:
    .\.venv\Scripts\python.exe scripts\test_headless.py
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langgraph.types import Command

from src.graph.build import build_graph
from src.db import supabase_client as db


PROSPECT = "Aravind Srinivas"
COMPANY  = "Perplexity AI"
ROLE     = "CEO & Co-founder"
GOAL     = "book a 20-minute discovery call"
PRODUCT  = (
    "AI workflow automation platform — helps ops and sales teams cut manual "
    "data work by ~70% using AI agents."
)

THREAD_ID = f"headless-{uuid.uuid4().hex[:8]}"


def _drive_to_completion(graph, thread_cfg: dict) -> dict:
    """Resume graph through every interrupt until done. Returns final state."""
    while True:
        snap = graph.get_state(thread_cfg)
        if not snap.next:
            return snap.values

        node = snap.next[0]
        state = snap.values
        print(f"  [PAUSE] interrupted at [{node}]", end=" ")

        if node == "disambiguate":
            candidates = state.get("candidate_identities", [])
            choice = candidates[0] if candidates else {}
            print(f"-> picking candidate: {choice.get('name', 'first')}")
            graph.invoke(Command(resume=choice), config=thread_cfg)

        elif node == "signal_review":
            signals = state.get("signals", [])
            top = next(
                (s for s in sorted(signals, key=lambda s: s.get("total_score", 0), reverse=True)
                 if not s.get("is_sensitive")),
                signals[0] if signals else None,
            )
            sig_id = top["id"] if top else "sig_01"
            print(f"-> selecting signal [{sig_id}]: {top.get('description', '')[:60] if top else '(none)'}")
            graph.invoke(Command(resume={"signal_id": sig_id, "instructions": ""}), config=thread_cfg)

        elif node == "draft_review":
            print("-> approving draft as-is")
            graph.invoke(Command(resume={"action": "approve"}), config=thread_cfg)

        elif node == "approve":
            print("-> final approval")
            graph.invoke(Command(resume={"action": "approve"}), config=thread_cfg)

        else:
            print(f"-> unknown interrupt, resuming empty")
            graph.invoke(Command(resume={}), config=thread_cfg)


def main() -> int:
    print(f"=== Headless pipeline test ===")
    print(f"Prospect : {PROSPECT} @ {COMPANY}")
    print(f"Thread   : {THREAD_ID}")
    print()

    graph = build_graph()
    thread_cfg = {"configurable": {"thread_id": THREAD_ID}}

    initial_state = {
        "company":          COMPANY,
        "prospect_name":    PROSPECT,
        "role":             ROLE,
        "outreach_goal":    GOAL,
        "product_description": PRODUCT,
    }

    print("[1/3] Starting pipeline (research + extract + flag + score)...")
    graph.invoke(initial_state, config=thread_cfg)

    print("[2/3] Driving through interrupts...")
    final = _drive_to_completion(graph, thread_cfg)

    print()
    print("[3/3] Verifying results...")

    run_id = final.get("run_id")
    assert run_id, "run_id missing from final state"

    flags      = final.get("flags", [])
    freshness  = final.get("signal_freshness")
    signals    = final.get("signals", [])
    hook_val   = final.get("hook", {})
    drafts     = final.get("drafts", {})
    status     = final.get("status")

    print(f"  run_id   : {run_id}")
    print(f"  mode     : {final.get('mode')}")
    print(f"  flags    : {flags}")
    print(f"  freshness: {freshness}")
    print(f"  signals  : {len(signals)} extracted")
    print(f"  status   : {status}")
    print()

    assert status == "completed", f"expected completed, got {status!r}"
    assert isinstance(signals, list), "signals should be a list"
    assert hook_val, "hook missing"
    assert drafts.get("email"), "email draft missing"
    assert drafts.get("linkedin"), "linkedin draft missing"

    # Verify run was written to Supabase
    db_run = db.get_run(run_id)
    assert db_run, f"run {run_id} not found in Supabase"
    assert db_run["status"] == "completed", f"DB status: {db_run['status']}"
    print(f"  Supabase : run {run_id} -> status={db_run['status']}")

    print()
    print("-- Email subject ----------------------------------------------")
    print(drafts["email"].get("subject", "(no subject)"))
    print()
    print("-- Email body (first 400 chars) -------------------------------")
    print(drafts["email"].get("body", "(empty)")[:400])
    print()
    print("-- LinkedIn ---------------------------------------------------")
    print(drafts["linkedin"].get("body", "(empty)")[:400])
    print()
    print("HAPPY PATH MILESTONE -- full pipeline completed end-to-end.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
