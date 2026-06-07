# Instruction Set — Single Source of Truth (Requirements & Spec)

> Consolidated from the original `instruction-set.md` (project brief) and `instruction.md` (architect deliverables), reconciled against [assessment.txt](assessment.txt). This is the **behavioral / requirements** spec. Implementation detail lives in [architecture.md](architecture.md).

---

## 1. The Core Question

> Given a real operational problem, a week, and access to any AI tools — can you build a process that **actually runs**, handles **real inputs**, and deals with **edge cases gracefully**?

## 2. Goal

Build a live, deployable application that automates personalized B2B outbound research and outreach generation. The system must:

1. Accept a prospect as input.
2. Perform real web research.
3. Discover meaningful prospect/company signals.
4. Rank those signals using **explainable** logic.
5. Allow human review and intervention.
6. Generate personalized outreach drafts.
7. Maintain complete visibility into the workflow.
8. Store and display historical runs.
9. Handle edge cases deliberately.

**The goal is NOT** to generate outreach emails. It is to demonstrate: operational thinking, process design, explainability, judgment, human-in-the-loop workflows, edge-case handling, and AI workflow orchestration. It should feel like **an AI-assisted GTM research tool, not a prompt wrapper.**

## 3. Non-Goals (explicitly out of MVP scope)

Email sending · CRM integration · LinkedIn private-API/scraping · multi-provider research · team collaboration · outreach analytics. These are future enhancements — **do not build them now.**

## 4. Core Definitions

**Signal** — a potentially useful piece of information discovered during research (funding announcement, hiring surge, executive interview, product launch, expansion, partnership, public discussion of a challenge, new leadership hire). Signals are *raw intelligence*; the system may find many.

**Hook** — the single chosen signal that drives outreach; the thread used to start the conversation. Only one signal becomes the primary hook, and **the system must explain why it was selected** (and why alternatives were rejected).

> Example — Signal: "Company raised Series B." → Hook: *"Congratulations on the recent Series B. Growth at that stage often introduces operational scaling challenges…"*

## 5. Decided Stack (with reasoning)

| Layer | Tool | Reasoning | Constraints |
|---|---|---|---|
| App / UI | Streamlit **+ custom theming** | One codebase, fast, native workflow-visibility; theming for polish since UI is graded | Single-script rerun model — handled via LangGraph checkpointer + `@st.cache_resource` (see [architecture.md §3](architecture.md)) |
| Orchestration | LangGraph | Explicit stages, state mgmt, conditional edge-case routing, HITL checkpoints, easy to explain | Keep it **simple** — no subgraphs, no multi-agent, no needless abstraction |
| LLM | Claude API | Strong reasoning, structured extraction, scoring, drafting, explainability | Claude must **never** make final decisions without exposing reasoning |
| Research | Tavily API | Public news, funding, hiring, press, exec interviews, public web | **Public info only**; results cached per query (reused on account collisions + demo robustness) |
| Persistence | Supabase (Postgres) | Durable history across restarts; powers dashboard **and** account-collision detection | Persist inputs, research, signals, scores, hooks, drafts, edits, status, approvals |
| Deploy | Streamlit Community Cloud | Free, simple, reliable for demo | Ephemeral filesystem — durable state must live in Supabase |

**Research Provider Layer** is an interface so future providers (LinkedIn, Crunchbase, dedicated News) can be added. **MVP implements Tavily only.**

## 6. Product Philosophy

Focus on: (1) finding meaningful signals, (2) evaluating them intelligently, (3) explaining decisions, (4) allowing human control, (5) producing grounded outreach. Never `Input → Claude → Email`. Always the deliberate pipeline (§7).

## 7. Workflow (9 stages)

| # | Stage | Required input | What happens | Output | Human? |
|---|---|---|---|---|---|
| 1 | **Prospect Input** | **Company (required)**; Prospect Name (optional → *Account mode*); opt: Role, Outreach Goal, Context | Validate & normalize; **merge in Seller Profile** (§7.2); if no person → Account mode; check account history | Structured prospect object | — |
| 2 | **Research** | Prospect object | Multiple focused Tavily queries (or cached results); show progress | Raw results, visible to user | — |
| 3 | **Signal Extraction + Flagging** | Raw results | Convert research → structured signals; run deterministic + LLM edge-flag checks. **Do not select yet.** | Signal list + edge flags + freshness | — |
| 4 | **Signal Scoring** | Signals | Score each on Recency, Specificity, Actionability, Confidence; mark sensitive; store rationale | Ranked signals + reasoning | — |
| 5 | **Human Signal Review** | Ranked signals + flags | Show summary/source/scores/reasoning + freshness/flag badges. User can accept, pick another, regenerate, or add instructions | Selected signal | ✅ required |
| 6 | **Hook Generation** | Selected signal + flags | Transform into a hook; respect flags (elevate funding, exclude sensitive, treat stale as context not opener); explain why chosen / why alternatives rejected | Hook + justification | — |
| 7 | **Draft Generation** | Hook + prospect + context + framing directive | Generate Email **and** LinkedIn drafts; grounded, no hallucination/fake personalization; framing adapts to flags | Drafts | — |
| 8 | **Human Review** | Drafts | User can edit, change tone/length, regenerate, change signal, add instructions. **No auto-send** | Revised draft | ✅ required |
| 9 | **Approval** | Final draft | User approves; store approved version | Stored approved run | ✅ required |

**Scoring axes (Stage 4):** *Recency* (how recent), *Specificity* (how directly tied to this prospect), *Actionability* (how naturally usable in outreach), *Confidence* (how trustworthy the source).

**Steering examples (Stages 5/8):** "Focus on technical challenges" · "Use the hiring signal" · "Ignore funding" · "More concise" · "More executive-friendly" · "More conversational."

### 7.1 Input Model — Company required, Person optional (Account mode)

- **Company is the hard requirement** — it is the anchor for research, disambiguation, and every fallback path.
- **Person name is the personalization driver and the intended happy path.**
- **If the person is omitted → "Account mode":** the system does **not** error. It degrades transparently to company-level outreach (reusing the `no_signal` company-level path), states the limitation honestly, and lowers personalization confidence.
- Rationale & trade-off (deviation from the original "both required" brief) logged as **D9** in [progress_tracker.md](progress_tracker.md).

| Input given | Mode | Personalization |
|---|---|---|
| Person **+** Company | **Primary / happy path** | Full — person-centric hook |
| Company only | Account mode (degraded) | Company-level, honest about limits |

### 7.2 Seller Profile — what you sell, set once (D9b / D12)

What you sell **does not change per prospect**, so it is **not** a per-run field. It is configured **once** on a **Settings / Seller Profile** page and auto-applied to every run:

- **Product / what you sell + value prop** — used by the draft generator to connect the hook → the reason for outreach (without it, drafts find a hook but can't say *why* you're reaching out).
- Optional default tone / length preferences.

The per-run form may expose an **optional, pre-filled override** for the rare case of pitching a different product to a specific prospect — but it's normally left untouched. This mirrors real SDR tooling: product context lives at the account level; the rep only types what's *different* about each prospect.

## 8. Research Strategy

Do not rely on a single query. Run multiple focused queries across categories: (1) Prospect + Company, (2) Company News, (3) Funding Activity, (4) Hiring Activity, (5) Executive Interviews, (6) Press Releases, (7) Public LinkedIn info, (8) Company Announcements. Objective: **maximize signal discovery.** Results must be **visible to the user** and **cached per query** (so a second contact at the same company reuses sources, and demos are robust to API flakiness). Concrete query templates + empty-result / rate-limit / name-collision handling in [architecture.md](architecture.md).

## 9. Live Run View Requirements

The app must visibly execute each stage with clear statuses, e.g.: *Researching Prospect · Gathering Sources · Extracting Signals · Scoring Signals · Awaiting User Selection · Generating Hook · Generating Draft · Awaiting Approval · Completed.* Edge flags surface as badges (freshness color-code, "High intent window", "N other contacts at this account", "Sensitive context"). The user should understand exactly what is happening — transparency is the point.

## 10. Dashboard Requirements

Display historical runs. Each row: **Timestamp · Prospect · Company · Status · Chosen Signal · Signal Type · Approval Status · Flags.** Expandable detail: research results · signals · scores · freshness · hook · draft · human edits. History persists permanently in Supabase and **also powers account-collision detection** (lookup by company).

## 11. Edge Cases (7 conditions — modeled as orthogonal flags)

A run may trigger **several flags at once** (e.g., 2nd contact at a company that just raised = `account_collision` **+** `funding_round`). Detection logic (code), exact pipeline changes, user-facing output, and demo test cases are in [architecture.md §9](architecture.md).

| Flag | Type | Trigger | Required behavior |
|---|---|---|---|
| **`funding_round`** | Positive trigger | Funding terms (Series A/B/C, "raised $X", "closed round") dated **< 60 days** | **Elevate above all signals**; urgency / action-oriented framing ("standing up new infra in the first 90 days"); "High intent window" badge; show amount/round/date |
| **`new_role`** | Positive trigger | Prospect started a role **< 90 days** ago | Prioritize person-centric "congrats on the move" angle; verify tenure |
| **`ambiguous_name`** | Blocking (HITL) | Multiple distinct people match name+company | **Pause**, ask user to select correct person, then resume |
| **`no_signal` (ghost / Account mode)** | Degrade | Little/no public info on the person, **or no person given** | Fall back to company-level signals, lower confidence, **explain the limitation** |
| **`sensitive_news`** | Caution | Layoffs / lawsuit / scandal / financial distress (last ~6 mo) | **Flag sensitive**, do not auto-use, recommend safer alternatives |
| **`stale_signals`** | Quality / honesty | Most recent signal **> 90 days** (`stale`) or **> 180 days** (`very_stale`) | Don't open with stale specifics; shift draft to **forward-looking, hedged framing**; per-signal freshness indicator; "most recent signal is X months old" banner |
| **`account_collision`** | B2B account-aware | Prior run(s) exist for the **same company** | **Reuse research cache**; **differentiate hook by role** ("person N of M — emphasize their function, not the company broadly"); show prior contacts' hooks to avoid overlap |

> **Demo guidance:** the assessment asked for 2–4 edge cases; we build all 7 for robustness. For the ≤5-min video, showcase the strongest 2–3 — recommended: **`funding_round`** (sales timing), **`account_collision`** (B2B fluency), **`sensitive_news`** (restraint). Demo the rest live in the interview.

## 12. Failure Handling (behavior level)

> Full matrix with code-level responses in [architecture.md](architecture.md).

The user must always see a clear, honest state when: Tavily returns 0 results · Claude returns malformed JSON · prospect has no LinkedIn/web presence · an API call times out · the **same person** is run twice (surface prior run; don't silently dup) · the **same company, different person** is run (→ `account_collision`, not a duplicate).

## 13. Scope — In / Out for MVP

**In:** the 9-stage workflow · multi-query Tavily research with caching · Claude extraction/scoring/hook/draft · all 7 edge flags · Account mode · **Seller Profile settings (product set once)** · live-run view · dashboard with persistent history · email + LinkedIn drafts.

**Out:** everything in §3 Non-Goals.

## 14. Assumptions (note for the live pitch)

Per the assessment, ambiguity is part of the exercise — assumptions are logged and referenceable. The living list is in [progress_tracker.md](progress_tracker.md). Headline assumptions:

| # | Assumption | If wrong… |
|---|---|---|
| A1 | "LinkedIn activity" = publicly indexed content via Tavily, not private API | Add a LinkedIn provider (future) |
| A2 | Test inputs are real public companies/people (assessment FAQ, PS-3) | Swap to fabricated-but-plausible inputs |
| A3 | Single-user tool; no auth/multi-tenancy in MVP | Add auth later |
| A4 | Same-person re-run surfaces prior run; same-company triggers `account_collision` | Adjust dedupe/collision policy |
| A5 | Claude returns strict JSON with a repair-retry safety net | Tighten prompts / schema-validate |
| A6 | Freshness windows: `stale` > 90d, `very_stale` > 180d (tunable) | Adjust in `config.py` |
| A7 | Funding "high-intent window" = 60 days (tunable) | Adjust in `config.py` |
| A8 | New-role window = 90 days; sensitive window = ~180 days (tunable) | Adjust in `config.py` |
| A9 | Account collisions keyed by normalized company name/domain | Refine matching (legal entity vs brand) |

## 15. Success Criteria

Process runs end-to-end · research is real · signals are meaningful · ranking is explainable · humans remain in control · edge cases handled deliberately · history preserved · **every decision explainable live.** The strongest parts must be signal discovery, ranking, hook selection, explainability, and HITL — this project demonstrates **judgment, not just content generation.**
