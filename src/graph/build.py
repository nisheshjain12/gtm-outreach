"""Assemble the real LangGraph pipeline (architecture.md §5).

Interrupt nodes: disambiguate (conditional), signal_review, draft_review, approve.
Checkpointer defaults to in-memory MemorySaver; inject a persistent one for prod.
"""
from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from src.graph.nodes import (
    account_check,
    approve,
    disambiguate,
    draft,
    draft_review,
    extract,
    flag,
    hook,
    ingest,
    research,
    score,
    signal_review,
    store,
)
from src.graph.state import RunState


def _route_after_flag(state: RunState) -> str:
    return "disambiguate" if "ambiguous_name" in state.get("flags", []) else "score"


def build_graph(checkpointer=None):
    """Return a compiled LangGraph pipeline.

    Args:
        checkpointer: LangGraph checkpointer instance.
            Defaults to MemorySaver (transient, per-process).
            Use a persistent checkpointer for production.
    """
    g = StateGraph(RunState)

    g.add_node("ingest",        ingest)
    g.add_node("account_check", account_check)
    g.add_node("research",      research)
    g.add_node("extract",       extract)
    g.add_node("flag",          flag)
    g.add_node("disambiguate",  disambiguate)
    g.add_node("score",         score)
    g.add_node("signal_review", signal_review)
    g.add_node("hook",          hook)
    g.add_node("draft",         draft)
    g.add_node("draft_review",  draft_review)
    g.add_node("approve",       approve)
    g.add_node("store",         store)

    g.add_edge(START,           "ingest")
    g.add_edge("ingest",        "account_check")
    g.add_edge("account_check", "research")
    g.add_edge("research",      "extract")
    g.add_edge("extract",       "flag")

    g.add_conditional_edges(
        "flag",
        _route_after_flag,
        {"disambiguate": "disambiguate", "score": "score"},
    )

    g.add_edge("disambiguate",  "score")   # after disambiguation always score
    g.add_edge("score",         "signal_review")
    g.add_edge("signal_review", "hook")
    g.add_edge("hook",          "draft")
    g.add_edge("draft",         "draft_review")
    g.add_edge("draft_review",  "approve")
    g.add_edge("approve",       "store")
    g.add_edge("store",         END)

    return g.compile(checkpointer=checkpointer or MemorySaver())
