"""LangGraph run state. See architecture.md §4.

Edge conditions are ORTHOGONAL FLAGS (a run can carry several at once),
not a single enum.
"""
from __future__ import annotations
from typing import TypedDict, Literal, Optional

EdgeFlag = Literal[
    "funding_round",
    "new_role",
    "ambiguous_name",
    "no_signal",
    "sensitive_news",
    "stale_signals",
    "account_collision",
]


class RunState(TypedDict, total=False):
    run_id: str

    # Stage 1 — input (company required, person optional)
    prospect_name: Optional[str]
    company: str
    company_key: str                       # normalized for history match
    mode: Literal["personalized", "account"]
    role: Optional[str]
    product_description: Optional[str]     # from Seller Profile (set once), overridable
    outreach_goal: Optional[str]
    extra_context: Optional[str]

    # Account awareness (pre-research)
    account_contacts: list[dict]           # [{name, role, hook, run_id}]

    # Stage 2 — research
    research: list[dict]                   # [{category,title,url,snippet,published_date,age_days}]
    research_categories_done: list[str]
    research_from_cache: bool

    # Edge flags (orthogonal)
    flags: list[EdgeFlag]
    signal_freshness: Literal["fresh", "stale", "very_stale"]
    candidate_identities: list[dict]       # ambiguous_name
    company_level_only: bool               # no_signal / account mode
    edge_evidence: dict

    # Stage 3/4 — signals
    signals: list[dict]

    # Stage 5 — human signal review
    selected_signal_id: Optional[str]
    user_instructions: Optional[str]

    # Stage 6 — hook
    hook: Optional[dict]
    framing_directive: str                 # built from flags; steers the draft

    # Stage 7 — drafts
    drafts: dict                           # {"email": {...}, "linkedin": {...}}

    # Stage 8/9
    human_edits: list[dict]
    approval_status: Literal["draft", "approved"]
    status: str
    errors: list[dict]
