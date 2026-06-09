"""Pipeline nodes (architecture.md §5).

Each function: (state: RunState) -> dict  (partial state update).
Interrupt nodes use langgraph.types.interrupt() and resume via Command(resume=...).
"""
from __future__ import annotations

import json
import logging
from datetime import date
from typing import Optional

from langgraph.types import interrupt

from src import config
from src.db import supabase_client as db
from src.edges.checks import (
    compute_flags,
    build_framing_directive,
    normalize_company_key,
)
from src.graph.state import RunState
from src.llm import client as llm
from src.providers.tavily_provider import TavilyProvider

log = logging.getLogger(__name__)


# ── 1. ingest ────────────────────────────────────────────────────────────────

def ingest(state: RunState) -> dict:
    company = state["company"]
    prospect_name = state.get("prospect_name") or None
    company_key = normalize_company_key(company)
    mode: str = "account" if not prospect_name else "personalized"

    # Seller Profile fills product_description if not supplied per-run
    product_description = state.get("product_description")
    if not product_description:
        profile = db.get_seller_profile() or {}
        product_description = profile.get("product_description", "")

    run_id = db.create_run({
        "company": company,
        "company_key": company_key,
        "prospect_name": prospect_name,
        "mode": mode,
        "product_description": product_description,
        "outreach_goal": state.get("outreach_goal"),
        "extra_context": state.get("extra_context"),
        "status": "researching",
    })

    return {
        "run_id": run_id,
        "company_key": company_key,
        "mode": mode,
        "prospect_name": prospect_name,
        "product_description": product_description,
        "flags": [],
        "errors": [],
        "account_contacts": [],
    }


# ── 2. account_check ─────────────────────────────────────────────────────────

def account_check(state: RunState) -> dict:
    prior = [
        r for r in db.find_runs_by_company(state["company_key"])
        if r["id"] != state.get("run_id") and r.get("status") == "completed"
    ]
    contacts = [
        {
            "name": r.get("prospect_name") or "Unknown",
            "role": r.get("role"),
            "hook": None,   # hook text stored separately; load lazily if needed
            "run_id": r["id"],
        }
        for r in prior
    ]
    return {"account_contacts": contacts}


# ── 3. research ──────────────────────────────────────────────────────────────

def research(state: RunState) -> dict:
    provider = TavilyProvider()
    sources = provider.search(state.get("prospect_name"), state["company"])

    if state.get("run_id") and sources:
        db.save_sources(state["run_id"], sources)

    return {
        "research": sources,
        "research_from_cache": False,
        "research_categories_done": list({s["category"] for s in sources}),
    }


# ── 4. extract ───────────────────────────────────────────────────────────────

def extract(state: RunState) -> dict:
    result = llm.extract_signals(
        prospect_name=state.get("prospect_name"),
        company_name=state["company"],
        research_json=json.dumps(state.get("research", [])),
        extra_context=state.get("extra_context", ""),
    )
    signals = result.get("signals", [])
    for i, sig in enumerate(signals):
        if not sig.get("id"):
            sig["id"] = f"sig_{i+1:02d}"
    return {"signals": signals}


# ── 5. flag ──────────────────────────────────────────────────────────────────

def flag(state: RunState) -> dict:
    signals = state.get("signals", [])
    mode = state.get("mode", "personalized")
    account_contacts = state.get("account_contacts", [])

    # LLM judges ambiguous_name only (never date math — that's deterministic code)
    research_sample = json.dumps(state.get("research", [])[:10])
    classify = llm.classify_edges(
        prospect_name=state.get("prospect_name"),
        company_name=state["company"],
        research_json=research_sample,
    )
    ambiguous = bool(classify.get("ambiguous_name")) and bool(state.get("prospect_name"))
    candidates = classify.get("candidate_identities", [])

    flag_result = compute_flags(
        signals,
        mode=mode,
        account_collision=len(account_contacts) > 0,
        ambiguous_name=ambiguous,
    )

    prior_hooks = [c.get("hook") for c in account_contacts if c.get("hook")]
    framing = build_framing_directive(
        flag_result["flags"],
        role=state.get("role"),
        account_n=len(account_contacts) + 1 if account_contacts else None,
        account_m=len(account_contacts) + 1 if account_contacts else None,
        prior_hooks=prior_hooks or None,
    )

    return {
        **flag_result,
        "candidate_identities": candidates,
        "framing_directive": framing,
        "edge_evidence": {"classify": classify},
    }


# ── 6. disambiguate (interrupt — only fires when ambiguous_name flag set) ────

def disambiguate(state: RunState) -> dict:
    candidates = state.get("candidate_identities", [])
    choice = interrupt({
        "type": "disambiguate",
        "prompt": f"Multiple people match '{state.get('prospect_name')}'. Which one?",
        "candidates": candidates,
    })
    if isinstance(choice, dict) and choice.get("name"):
        updated: dict = {
            "prospect_name": choice.get("name", state.get("prospect_name")),
            "flags": [f for f in state.get("flags", []) if f != "ambiguous_name"],
        }
        if choice.get("role"):
            updated["role"] = choice["role"]
        if choice.get("company"):
            updated["company"] = choice["company"]
            updated["company_key"] = normalize_company_key(choice["company"])
        return updated
    # User skipped disambiguation — remove the flag and proceed
    return {"flags": [f for f in state.get("flags", []) if f != "ambiguous_name"]}


# ── 7. score ─────────────────────────────────────────────────────────────────

def score(state: RunState) -> dict:
    signals = state.get("signals", [])
    if not signals:
        return {}

    result = llm.score_signals(
        signals_json=json.dumps(signals),
        today=date.today().isoformat(),
        prospect_name=state.get("prospect_name"),
        role=state.get("role"),
        company_name=state["company"],
    )

    scored_map = {s["id"]: s for s in result.get("signals", [])}
    merged = []
    for sig in signals:
        update = scored_map.get(sig.get("id"), {})
        merged.append({
            **sig,
            "scores":      update.get("scores", {}),
            "total_score": update.get("total_score", 0),
            "reasoning":   update.get("reasoning", ""),
            "is_sensitive": update.get("is_sensitive", False),
        })

    flags = list(state.get("flags", []))
    newly_sensitive = (
        any(s.get("is_sensitive") for s in merged)
        and "sensitive_news" not in flags
    )
    if newly_sensitive:
        flags.append("sensitive_news")

    result: dict = {"signals": merged, "flags": flags}

    # framing_directive was built in the flag node (before scoring).
    # If sensitive_news is only discovered now, rebuild it so the hook
    # and draft generators receive the correct "avoid sensitive topic" instruction.
    if newly_sensitive:
        account_contacts = state.get("account_contacts", [])
        prior_hooks = [c.get("hook") for c in account_contacts if c.get("hook")]
        result["framing_directive"] = build_framing_directive(
            flags,
            role=state.get("role"),
            account_n=len(account_contacts) + 1 if account_contacts else None,
            account_m=len(account_contacts) + 1 if account_contacts else None,
            prior_hooks=prior_hooks or None,
        )

    return result


# ── 8. signal_review (interrupt — required HITL) ─────────────────────────────

def signal_review(state: RunState) -> dict:
    signals = state.get("signals", [])
    sorted_sigs = sorted(signals, key=lambda s: s.get("total_score", 0), reverse=True)
    top = next((s for s in sorted_sigs if not s.get("is_sensitive")), sorted_sigs[0] if sorted_sigs else None)

    choice = interrupt({
        "type": "signal_review",
        "signals": sorted_sigs[:config.MAX_SIGNALS_SHOWN],
        "flags": state.get("flags", []),
        "pre_selected": top.get("id") if top else None,
    })

    return {
        "selected_signal_id": choice.get("signal_id"),
        "user_instructions": choice.get("instructions", ""),
    }


# ── 9. hook ──────────────────────────────────────────────────────────────────

def hook(state: RunState) -> dict:
    signals = state.get("signals", [])
    sel_id = state.get("selected_signal_id")
    selected = next((s for s in signals if s.get("id") == sel_id), signals[0] if signals else {})
    others = [s for s in signals if s.get("id") != selected.get("id")]

    result = llm.select_hook(
        selected_signal_json=json.dumps(selected),
        other_signals_json=json.dumps(others[:3]),
        flag_rules=state.get("framing_directive", ""),
        user_instructions=state.get("user_instructions", ""),
        prospect_name=state.get("prospect_name"),
        company_name=state["company"],
        outreach_goal=state.get("outreach_goal", "book a discovery call"),
    )

    if state.get("run_id"):
        db.save_hook(state["run_id"], {
            "hook_text": result.get("hook_text", ""),
            "why_it_matters": result.get("why_it_matters", ""),
            "why_chosen": result.get("why_chosen", ""),
            "why_alternatives_rejected": result.get("why_alternatives_rejected", []),
        })

    return {"hook": result}


# ── 10. draft ────────────────────────────────────────────────────────────────

def draft(state: RunState) -> dict:
    result = llm.generate_draft(
        hook_json=json.dumps(state.get("hook", {})),
        prospect_name=state.get("prospect_name"),
        role=state.get("role"),
        company_name=state["company"],
        product_description=state.get("product_description", ""),
        outreach_goal=state.get("outreach_goal", "book a discovery call"),
        framing_directive=state.get("framing_directive", ""),
        user_instructions=state.get("user_instructions", ""),
    )

    if state.get("run_id"):
        email = result.get("email", {})
        linkedin = result.get("linkedin", {})
        db.save_drafts(state["run_id"], [
            {"channel": "email", "subject": email.get("subject", ""), "body": email.get("body", "")},
            {"channel": "linkedin", "body": linkedin.get("body", "")},
        ])

    return {"drafts": result}


# ── 11. draft_review (interrupt) ─────────────────────────────────────────────

def draft_review(state: RunState) -> dict:
    """Review loop: interrupts until user approves.

    action == "edit" with instructions → re-calls Gemini, interrupts again
    with the new draft so the user can see it before approving.
    action == "approve" → exits the loop.
    """
    drafts = state.get("drafts", {})
    human_edits = list(state.get("human_edits", []))

    while True:
        choice = interrupt({
            "type": "draft_review",
            "drafts": drafts,
            "hook": state.get("hook", {}),
            "flags": state.get("flags", []),
        })

        action = choice.get("action", "approve")

        if action == "edit":
            instructions = (choice.get("edits") or {}).get("instructions", "")
            if state.get("run_id"):
                db.log_action(state["run_id"], "draft_review", "edit", choice.get("edits"))
            human_edits.append({"stage": "draft_review", "edits": choice.get("edits", {})})

            if instructions:
                # Re-generate with the new instructions then loop back to interrupt
                result = llm.generate_draft(
                    hook_json=json.dumps(state.get("hook", {})),
                    prospect_name=state.get("prospect_name"),
                    role=state.get("role"),
                    company_name=state["company"],
                    product_description=state.get("product_description", ""),
                    outreach_goal=state.get("outreach_goal", "book a discovery call"),
                    framing_directive=state.get("framing_directive", ""),
                    user_instructions=instructions,
                )
                drafts = result
                if state.get("run_id"):
                    email = drafts.get("email", {})
                    linkedin = drafts.get("linkedin", {})
                    db.save_drafts(state["run_id"], [
                        {"channel": "email", "subject": email.get("subject", ""), "body": email.get("body", "")},
                        {"channel": "linkedin", "body": linkedin.get("body", "")},
                    ])
            else:
                # No regen instructions — user edited inline; use the text-area values
                drafts = choice.get("updated_drafts") or drafts
            # loop → interrupt fires again with the updated drafts
        else:
            # "approve" — capture any final inline edits and exit
            drafts = choice.get("updated_drafts") or drafts
            break

    return {"human_edits": human_edits, "drafts": drafts}


# ── 12. approve (interrupt) ──────────────────────────────────────────────────

def approve(state: RunState) -> dict:
    choice = interrupt({
        "type": "approve",
        "drafts": state.get("drafts", {}),
        "hook": state.get("hook", {}),
    })

    action = choice.get("action", "approve")
    if state.get("run_id"):
        db.log_action(state["run_id"], "approve", action, None)

    return {"approval_status": "approved" if action == "approve" else "draft"}


# ── 13. store ────────────────────────────────────────────────────────────────

def _signal_to_row(sig: dict) -> dict:
    scores = sig.get("scores") or {}
    return {
        "type":           sig.get("type"),
        "description":    sig.get("description"),
        "source_url":     sig.get("source_url"),
        "published_date": sig.get("published_date"),
        "age_days":       sig.get("age_days"),
        "funding_meta":   sig.get("funding_meta"),
        "recency":        scores.get("recency"),
        "specificity":    scores.get("specificity"),
        "actionability":  scores.get("actionability"),
        "confidence":     scores.get("confidence"),
        "total_score":    sig.get("total_score"),
        "reasoning":      sig.get("reasoning"),
        "is_sensitive":   sig.get("is_sensitive", False),
        "hook_sentence":  sig.get("hook_sentence"),
    }


def store(state: RunState) -> dict:
    run_id = state.get("run_id")
    if run_id:
        signals = state.get("signals", [])
        if signals:
            db.save_signals(run_id, [_signal_to_row(s) for s in signals])

        db.update_run(run_id, {
            "status":           "completed",
            "flags":            state.get("flags", []),
            "signal_freshness": state.get("signal_freshness"),
            "approval_status":  state.get("approval_status", "draft"),
        })

    return {"status": "completed"}
