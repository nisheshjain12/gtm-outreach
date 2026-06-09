# GTM Outreach Engine

**An AI-assisted B2B outreach tool that turns a prospect's name into a researched, personalized, human-approved cold email — not a template with the name filled in.**

Live app: *(your Streamlit Cloud URL)* · Stack: Streamlit · LangGraph · Gemini · Tavily · Supabase

---

# Part 1 — The Non-Technical Explanation

## The problem

B2B sales lives or dies on the first message. A generic *"Hi {FirstName}, we sell X…"* gets deleted. A message that references something real — a recent funding round, a new hire, a product launch — gets a reply. The difference is **research**: finding the signal, understanding why it matters to *this* person, and turning it into something worth reading.

The catch is time. A sales rep working 200 prospects can't spend 20 minutes researching each one. So they don't — they blast templates, and the reply rate shows it.

**This tool automates the research and drafting, while keeping the human in control of every decision.**

## What it does, in one breath

You type a company (and optionally a person). The tool:
1. **Researches** them across the live web.
2. **Extracts** discrete facts ("signals").
3. **Scores and ranks** those signals so the most useful one rises to the top.
4. **Asks you** which angle to use.
5. **Writes** a personalized email and LinkedIn message built on that angle.
6. **Lets you edit, regenerate, and approve** before anything is final.
7. **Saves** the whole run to a history dashboard.

Nothing is ever sent automatically. The human approves at three points.

## Two key words

- **Signal** — a real, factual piece of intelligence found during research. Examples: *"raised a $50M Series B in April"*, *"hiring 12 engineers"*, *"launched a new product"*, *"the CEO gave a podcast interview about scaling challenges."* The tool usually finds 10–20 signals per prospect.
- **Hook** — the *single* signal you choose to build the message around, plus the angle for using it. Example — Signal: *"Company raised a Series B."* → Hook: *"Congrats on the Series B — scaling that fast usually strains operations, which is exactly where we help."* The tool explains **why** it recommends each hook and **why it rejected the others**.

## The happy path, step by step (what you see on screen)

1. **You fill a short form** — Company is required; person name, role, goal, and context are optional. (What you *sell* is set once in Settings, not per prospect.)

2. **Research runs** — The tool fires **6 targeted web searches** (see below) and pulls ~30 sources. You see the count climb.

3. **Signals are extracted** — The AI reads all 30 sources and pulls out the factual signals, ignoring marketing fluff. It never invents anything not in the sources.

4. **Signals are scored** — Each signal gets a 1–10 score on four axes (see below), and the list is ranked best-first. Anything sensitive (layoffs, lawsuits) is flagged and pushed down.

5. **You pick a signal (first human checkpoint)** — You see the ranked list with scores and reasoning. Accept the top pick, choose another, or add a steering instruction like *"focus on the hiring signal"* or *"keep it executive and brief."*

6. **The hook is written** — The AI crafts the angle and shows its reasoning: why this hook, why not the others.

7. **The drafts are written** — A full **email** (subject + 3 short paragraphs + one call to action) and a **LinkedIn message** (≤400 characters), both grounded only in the chosen hook and real facts.

8. **You review and refine (second human checkpoint)** — Edit either draft inline, or type an instruction and **Regenerate** — the AI rewrites and shows you the new version. You can regenerate as many times as you want.

9. **You approve (third human checkpoint)** — A final read-only look, then **Approve**. The run is saved to history.

10. **The Dashboard** — Every run is stored permanently: prospect, company, status, flags, signals, scores, hook, drafts, and a log of every human decision.

## What it searches (the 6 queries)

For each prospect the tool runs six focused web searches, because one broad search misses things — funding news, hiring pages, and podcast interviews all live in different corners of the web:

| # | Search | Finds |
|---|--------|-------|
| 1 | `"Person" Company` | Anything directly about the person |
| 2 | `Company news <year>` | Recent company news |
| 3 | `Company funding OR raised OR Series` | Fundraising activity |
| 4 | `Company hiring OR open roles` | Whether they're growing |
| 5 | `"Person" interview OR podcast OR keynote` | Public talks/interviews |
| 6 | `Company announcement OR launch OR partnership` | Launches, press, partnerships |

If you don't give a person name (**Account mode**), the two person-specific searches are skipped and it does company-level research only.

Every search result is **cached** — so researching a second person at the same company reuses the sources, and repeat runs are instant.

## How it ranks (the 4 scoring axes)

Each signal is scored 1–10 by a deliberately skeptical AI analyst:

| Axis | Question it answers |
|------|---------------------|
| **Recency** | How recent is this? Last week beats two years ago. |
| **Specificity** | Is it about *this person/role*, or just generic company news? |
| **Actionability** | How naturally does it open a relevant conversation? |
| **Confidence** | Is the source trustworthy (major press) or a random blog? |

The four are averaged into a total score, and signals are ranked. This is the **judgment layer** — the point isn't to generate an email, it's to find the right thread to pull and explain why.

## The edge cases (where it behaves differently from the happy path)

A run can trigger **several of these at once** (they're independent flags, not one category). Each one visibly changes the tool's behavior:

| Flag | When it triggers | What the tool does |
|------|------------------|--------------------|
| **Funding round** | A funding signal dated within 60 days | Elevates it above all signals; uses urgent, action-oriented framing ("standing up new infrastructure in the first 90 days"); shows a "high intent" badge |
| **New role** | The person started a role within 90 days | Leads with a genuine "congrats on the move" angle; speaks to early-tenure priorities |
| **Ambiguous name** | Multiple distinct people match the name | **Pauses and asks you** which person is the right one, then resumes (a human checkpoint) |
| **No signal / Account mode** | No person given, or no usable personal info | Degrades honestly to company-level outreach, lowers confidence, and says so — instead of erroring |
| **Sensitive news** | Layoffs, lawsuit, scandal, financial distress | Flags it, refuses to open with it, and steers to a safer angle |
| **Stale signals** | The most recent signal is over 90 days old | Won't pretend old news is fresh; switches to forward-looking, hedged framing; shows a "most recent signal is X old" banner |
| **Account collision** | You've already contacted someone else at this company | Reuses the cached research, differentiates the new hook by role, and shows the prior contacts so you don't repeat the same angle |

**Important honesty point:** some flags are *deterministic* and fire every time the condition is true (account collision, account mode — these are decided in plain code, never by the AI). Others are *emergent* — they depend on what the live web returns and how the AI judges it (funding, sensitive news, stale signals), so the same prospect can surface different flags on different days. That's realistic, not a bug.

---

# Part 2 — The Technical Explanation

## Architecture at a glance

```
Streamlit UI  ──drives──►  LangGraph pipeline (13 nodes, checkpointed)
                                  │
        ┌─────────────────┬───────┼────────────┬──────────────┐
     Tavily            Gemini   deterministic  Supabase     in-memory
    (research)      (extract/    edge checks   (durable      checkpointer
                     score/      (date math,    history)     (resumable
                     hook/draft)  collisions)                 interrupts)
```

- **Streamlit** is the UI and the driver. Its single-script rerun model is reconciled with the stateful pipeline via a cached graph + a per-session `thread_id`.
- **LangGraph** orchestrates the pipeline as an explicit graph of nodes and edges, with `interrupt()` for human-in-the-loop pauses and a checkpointer that makes runs resumable.
- **Gemini** (`google-genai` SDK) does all the language reasoning: extraction, scoring, hook selection, draft writing, and the ambiguity classifier. Every prompt returns strict JSON.
- **Tavily** is the web research provider behind an interface, so other providers could be added later.
- **Supabase** (Postgres) is durable history — it survives restarts and also powers account-collision detection (lookup by company).

## The pipeline — 13 nodes

`START → ingest → account_check → research → extract → flag → [disambiguate?] → score → signal_review → hook → draft → draft_review → approve → store → END`

| # | Node | What it does | Pauses for human? |
|---|------|--------------|-------------------|
| 1 | `ingest` | Creates the DB run row; normalizes the company key; decides Personalized vs Account mode | — |
| 2 | `account_check` | Looks up prior completed runs at the same company → sets up `account_collision` | — |
| 3 | `research` | Runs the 6 Tavily queries (cached); saves sources | — |
| 4 | `extract` | Gemini turns ~30 sources into structured signals | — |
| 5 | `flag` | Deterministic flag checks (dates, collisions) + LLM ambiguity classifier; builds the framing directive | — |
| 6 | `disambiguate` | **Interrupt** — only runs if `ambiguous_name`; asks the user to pick the right person | ✅ conditional |
| 7 | `score` | Gemini scores each signal on the 4 axes; detects sensitive content | — |
| 8 | `signal_review` | **Interrupt** — user picks the signal + optional instructions | ✅ required |
| 9 | `hook` | Gemini writes the hook + the "why chosen / why rejected" explanation | — |
| 10 | `draft` | Gemini writes the email + LinkedIn drafts (uses regen instructions on a loop pass) | — |
| 11 | `draft_review` | **Interrupt** — user edits/approves; a conditional edge loops back to `draft` to regenerate | ✅ required |
| 12 | `approve` | **Interrupt** — final approval | ✅ required |
| 13 | `store` | Persists signals + final run state | — |

**Two routing decisions** are conditional edges:
- After `flag`: go to `disambiguate` if `ambiguous_name`, else straight to `score`.
- After `draft_review`: loop back to `draft` if the user asked to regenerate with instructions, else forward to `approve`. (This is why you can regenerate unlimited times — the loop lives at the graph level, not inside a node.)

## Why the LLM never does date math

All date- and history-based flags (`funding_round` < 60 days, `new_role` < 90 days, `stale_signals` > 90/180 days, `account_collision`) are computed in **pure Python** in `src/edges/checks.py`. The LLM is only trusted with genuine judgment calls — `ambiguous_name` and `is_sensitive`. This keeps the flags grounded in real, dated evidence and prevents the model from hallucinating, say, a "new role" that isn't there.

## State and resumability

- The shared state is a `TypedDict` (`RunState`) merged across nodes — LangGraph only persists keys declared in the schema.
- The graph is compiled with an in-memory `MemorySaver` checkpointer and cached via `@st.cache_resource`, so it survives Streamlit reruns within a session.
- `interrupt()` pauses a node and saves a checkpoint; the UI renders the right panel and resumes with `Command(resume=...)`.
- On an API error mid-run, the checkpoint is preserved — the UI shows **Retry**, which calls `graph.invoke(None)` to resume from the last good node. Failed runs can also be re-run from the Dashboard (the form is pre-filled).
- **Limitation:** `MemorySaver` is per-process RAM. If Streamlit Cloud restarts, in-flight (uncompleted) runs lose their checkpoint. Durable *history* is always safe in Supabase; only mid-run resumability is affected. A persistent (Postgres) checkpointer is the production upgrade path.

## Resilience: quota and retries

- **Gemini calls** retry transient errors (503, per-minute 429) with exponential backoff `(0,5,15,30,60)s`.
- **Model cascade:** if a model is quota-limited, it cascades `gemini-2.5-flash ↔ gemini-2.5-flash-lite`.
- **Multi-key rotation:** configure several keys (`GEMINI_API_KEY`, `GEMINI_API_KEY_2…5`, or a comma-separated `GEMINI_API_KEYS`). When a key is quota-exhausted across both models, the client rotates to the next key. (Free-tier limits are *per Google Cloud project*, so keys must come from different projects to add real capacity.)
- **Malformed JSON** from the model triggers one automatic repair-retry.
- **Tavily** failures retry with backoff; a single failed query doesn't abort the run — partial results proceed.
- **Caching** makes demos deterministic and offline-robust: each query's results are cached to `cache/<hash>.json`.

## Project structure

```
app.py                      Streamlit entry point + sidebar nav + cached graph
src/
  config.py                 Secrets (env), tunable thresholds, multi-key collector
  graph/
    state.py                RunState TypedDict (the shared state schema)
    build.py                Assembles the 13-node graph + conditional edges
    nodes/__init__.py       The 13 node functions (the pipeline logic)
  edges/
    checks.py               Deterministic flag logic — dates, freshness, collisions
  providers/
    tavily_provider.py      6 query templates, backoff, account-mode handling
    cache.py                Per-query read-through file cache
    base.py                 Provider interface
  llm/
    client.py               Gemini wrapper: JSON, backoff, model cascade, key rotation
    prompts.py              The 5 prompt templates (extract/score/hook/draft/classify)
  db/
    supabase_client.py      All Supabase reads/writes
    schema.sql              7-table schema
  ui/
    live_run.py             Live Run page + the 4 interrupt panels
    dashboard.py            History dashboard with per-run detail tabs
    settings.py             Seller Profile page
    components.py           Reusable badges + signal cards + CSS injection
    styles.css              Custom theming
```

## Database schema (7 tables)

`seller_profile` (what you sell, single row) · `runs` (one per pipeline run) · `research_sources` · `signals` (with scores) · `hooks` (with reasoning) · `drafts` (email + LinkedIn) · `human_actions` (audit log of every HITL decision). Foreign keys reference `runs(id)`; `runs.company_key` is indexed to power account-collision lookups. Row-Level Security is on; the server uses the secret key to bypass it.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt

# Configure secrets in .env (see .env.example)
#   GEMINI_API_KEY, TAVILY_API_KEY, SUPABASE_URL, SUPABASE_KEY
#   (optional: GEMINI_API_KEY_2..5 for more quota)

# Apply the schema once in the Supabase SQL editor: src/db/schema.sql

streamlit run app.py
```

For Streamlit Cloud deployment, put the same keys in **Settings → Secrets** (`.streamlit/secrets.toml` format).

## Configuration knobs (`src/config.py`)

| Setting | Default | Meaning |
|---------|---------|---------|
| `FRESH_DAYS` | 90 | Older than this → `stale` |
| `VERY_STALE_DAYS` | 180 | Older than this → `very_stale` |
| `FUNDING_WINDOW_DAYS` | 60 | Funding within this → high-intent |
| `NEW_ROLE_DAYS` | 90 | Role started within this → `new_role` |
| `NUM_QUERIES` | 6 | Research queries per prospect |
| `MAX_SIGNALS_SHOWN` | 5 | Signals shown at the review step |
| `MODEL_*` | `gemini-2.5-flash` | Per-stage model (env-overridable) |

## Design decisions (the short version)

- **Streamlit + LangGraph + Gemini + Tavily + Supabase** — one codebase, explicit stages, free-tier-friendly, durable history.
- **Company required, person optional** — company is the anchor for research and fallback; omitting the person degrades gracefully to Account mode.
- **Orthogonal flags, deterministic-first** — a run can carry several flags; code does the date/collision math, the LLM only judges ambiguity and sensitivity.
- **Seller Profile set once** — product context lives at the account level; the per-run form captures only what differs, mirroring real SDR tooling.
- **Explainability everywhere** — every hook records why it was chosen and why alternatives were rejected; every human action is logged.

## Scope

**In:** the full research→draft pipeline, 6-query cached research, all 7 edge flags, Account mode, Seller Profile, live-run view, persistent dashboard, email + LinkedIn drafts, multi-key resilience.

**Out (deliberately):** sending email, CRM integration, private LinkedIn scraping, multi-provider research, team collaboration, analytics.
```
