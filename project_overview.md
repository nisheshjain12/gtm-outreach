# Project Overview — GTM Personalized Outreach Engine

> **One-liner:** A live, human-in-the-loop tool that takes a B2B prospect (company required, person optional), does real web research, finds and ranks meaningful signals with explainable logic, and produces a grounded, personalized outreach draft — with full run visibility and persistent history.

This is the north-star document. For the detailed spec see [instruction_set.md](instruction_set.md); for the technical design see [architecture.md](architecture.md); for the task plan see [build_tracker.md](build_tracker.md); for live status see [progress_tracker.md](progress_tracker.md). The original brief is [assessment.txt](assessment.txt).

---

## 1. The Problem (Case Study PS-3 — GTM)

B2B sales lives or dies on first contact. Generic outreach gets deleted; a message that references something *real* — a recent hire, a funding round, a problem the company is publicly grappling with — gets a reply. The gap between the two is **research time**. An SDR working 200 prospects can't spend 20 minutes each, so they swap in the company name and send something passable at scale.

But the signal *is* there — in company news, job postings, funding announcements, executive interviews, press. **The job we're automating:** a rep names a target → the process does the research, identifies the most relevant hook, and surfaces a draft worth reviewing. A human stays in the loop before anything sends.

## 2. What We're Building

An **AI-assisted GTM research tool**, not a prompt wrapper. The system:

1. Accepts a prospect as input (company required; person/role optional; product set once via Seller Profile).
2. Runs **real, multi-query web research** (Tavily).
3. Extracts **structured signals** from raw results (Claude).
4. **Scores and ranks** signals on explainable axes (recency, specificity, actionability, confidence).
5. Lets a **human review, override, or steer** signal selection.
6. Generates a **hook** with written justification (why this, why not the alternatives).
7. Generates **grounded outreach drafts** (email + LinkedIn) — no hallucinated personalization.
8. Lets the human **edit / re-tone / regenerate / approve**.
9. **Persists every run** for a dashboard of history, status, and outputs.

## 3. Why It's Different (the design thesis)

The application must **never** behave like:

```
Input → Claude → Email
```

It must behave like a deliberate pipeline where judgment is visible at every step:

```
Input → Research → Signal Discovery → Signal Ranking → Human Review
      → Hook Selection → Draft Generation → Human Approval → Store
```

The strongest, most-defensible parts of the system are deliberately: **signal discovery, signal ranking, hook selection, explainability, and the human-in-the-loop workflow** — not the text generation.

## 4. How It's Graded → How We Hit It

| Grading criterion (from assessment) | How this build addresses it |
|---|---|
| Process actually runs end-to-end on real inputs | Live LangGraph pipeline + live Tavily/Claude calls; demo-ready on Streamlit Cloud |
| Edge cases handled deliberately (2–4) | 7 edge conditions (orthogonal flags) with explicit detection + distinct pipeline behavior |
| UI quality — live run view + dashboard | Streamlit + custom theming: real-time stage view + persistent run-history dashboard |
| Judgment behind design choices | Explainable scoring; "why this hook / why not the others"; assumptions logged |
| Fluent live explanation | Every decision point is surfaced in the UI and documented for the pitch |

## 5. Tech Stack (locked)

| Layer | Choice | One-line reason |
|---|---|---|
| App / UI | **Streamlit + custom theming** | Single Python codebase, fast, good-enough polish in a week |
| Orchestration | **LangGraph** | Explicit stages, state, conditional edge-case routing, HITL checkpoints |
| LLM | **Claude API** | Strong reasoning, structured extraction, explainable scoring + drafting |
| Research | **Tavily API** | Public news, funding, hiring, press, public web (public info only) |
| Persistence | **Supabase (Postgres)** | Durable history across restarts; powers the dashboard |
| Deploy | **Streamlit Community Cloud** | Free, simple, reliable for a live demo |

## 6. Edge Cases (7 — orthogonal flags; a run can trigger several)

**Positive buying triggers**
1. **`funding_round`** — raised < 60 days ago → elevate above all signals; urgency framing; "high intent window".
2. **`new_role`** — started a job < 90 days ago → person-centric "congrats on the move" angle.

**Workflow / control**
3. **`ambiguous_name`** — multiple real people match → pause, ask the human to disambiguate, resume.
4. **`no_signal` / ghost (= Account mode)** — little/no info, or no person given → company-level signals, lower confidence, honest about limits.

**Judgment / honesty**
5. **`sensitive_news`** — layoffs / lawsuit / scandal → flag sensitive, never auto-use, recommend safer alternatives.
6. **`stale_signals`** — newest signal > 90d (`stale`) / > 180d (`very_stale`) → forward-looking, hedged framing instead of stale specifics.
7. **`account_collision`** — prior contact(s) at the same company → reuse research cache, differentiate the hook by role.

> Assessment asked for 2–4; we build all 7 for robustness. Video showcases the strongest 2–3 (`funding_round`, `account_collision`, `sensitive_news`); the rest are demoed live.

## 7. Deliverables (due Day 3 — 2026-06-08)

1. **A working process** — live and runnable on Streamlit Cloud, with live-run view + dashboard.
2. **A ≤5-minute demo video** — happy path running live, then at least one edge case, narrated.
3. *(Follow-up)* A live interview demo: happy path + prepared edge cases.

## 8. Success Criteria

The project succeeds when: the process runs end-to-end on real input · research is real · signals are meaningful · ranking is explainable · the human stays in control · all edge flags behave deliberately · history persists · **every decision can be explained live.**

## 9. Top Risks (watch these)

1. **Streamlit's rerun model vs. LangGraph's pause/resume** — the #1 technical risk. Mitigation in [architecture.md](architecture.md) (checkpointer + `session_state` + `interrupt`).
2. **Live API flakiness during the demo** — mitigation: cached/fixture fallback + rehearsed inputs validated the day before.
3. **Stale "recent news" test cases** — mitigation: validate all demo prospects live via Tavily right before recording/interview.

## 10. Decisions Locked

See the full, dated decision log in [progress_tracker.md](progress_tracker.md). Headline calls: Streamlit+theming UI · 7 edge flags · Account mode (company required, person optional) · Seller Profile (product set once) · 3-day build · LangGraph-checkpointer (transient run state) separated from Supabase (durable history) · **public information only** (no private LinkedIn scraping).
