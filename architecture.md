# Architecture — Technical Design

> Implementation-level companion to [instruction_set.md](instruction_set.md). Covers system design, the Streamlit↔LangGraph state strategy, per-stage data contracts, prompt templates, query strategy + caching, edge-flag detection code, the data model, failure handling, and demo test cases.

---

## 1. System Diagram

```
┌──────────────────────────────────────────────────────────────────────┐
│                        Streamlit App (app.py)                          │
│   ┌────────────────────┐            ┌──────────────────────────────┐  │
│   │   Live Run View    │            │         Dashboard            │  │
│   │  (stage-by-stage)  │            │  (history from Supabase)     │  │
│   └─────────┬──────────┘            └──────────────┬───────────────┘  │
└─────────────┼──────────────────────────────────────┼──────────────────┘
              │ drives / resumes                      │ reads
              ▼                                        ▼
┌──────────────────────────────┐          ┌──────────────────────────┐
│   LangGraph Pipeline          │  writes  │       Supabase            │
│   (state machine + interrupts)│─────────▶│  runs, research_sources,  │
│   checkpointer = run state    │          │  signals, hooks, drafts,  │
└───┬───────────┬───────┬───────┘          │  human_actions            │
    │           │       │                   └─────────────┬────────────┘
    ▼           ▼       ▼                                 │ account lookup
┌────────┐ ┌────────┐ ┌──────────┐                       │ (by company)
│ Cache  │ │ Tavily │ │  Claude  │◀──────────────────────┘
│(per-q) │ │(search)│ │  (LLM)   │
└────────┘ └────────┘ └──────────┘
```

## 2. Component Responsibilities

| Component | Responsibility |
|---|---|
| `app.py` | Routing between Live Run / Dashboard; owns `st.session_state` (thread_id, pending_resume); caches the compiled graph via `@st.cache_resource` |
| `src/graph/` | LangGraph state, node functions, graph assembly, checkpointer |
| `src/providers/` | Research provider interface + `TavilyProvider` (swappable) + **per-query cache** |
| `src/llm/` | Claude client wrapper (retries, JSON-repair) + prompt templates |
| `src/db/` | Supabase client + schema; per-stage persistence; account-collision lookup |
| `src/edges/` | Deterministic edge-flag checks (freshness, funding, role tenure, no_signal) |
| `src/ui/` | Live-run renderer, dashboard, **Seller Profile settings page**, reusable components (status/flag badges, signal cards), theme |
| `src/config.py` | Env/secrets, tunables (windows, query count, model IDs, cache dir) |

## 3. The #1 Risk — Streamlit Rerun vs. LangGraph Pause/Resume (SOLVED)

**Why it's solved:** LangGraph's **checkpointer stores graph state outside the Python call stack**, keyed by a `thread_id`. A Streamlit rerun then becomes "read current checkpoint → render"; the graph only advances on an explicit resume. The three load-bearing pieces:

1. **Cache the compiled graph** so its checkpointer survives reruns (the one real trap — rebuilding the graph each rerun rebuilds an empty checkpointer):
```python
@st.cache_resource
def get_graph():
    return build_graph()          # compiled with a checkpointer (MemorySaver for MVP)
```
2. **`thread_id` in `st.session_state`** so each session points at its saved state.
3. **Guard the first invoke; resume with `Command`:**
```python
cfg = {"configurable": {"thread_id": st.session_state.thread_id}}
snap = graph.get_state(cfg)
if snap.next:                                       # paused at interrupt()
    payload = snap.tasks[0].interrupts[0].value     # what to show the human
    # ...render review UI...
    if user_acted:
        graph.invoke(Command(resume=user_choice), cfg)   # resumes; does NOT replay nodes
        st.rerun()
elif not st.session_state.get("started"):
    st.session_state.started = True
    graph.invoke(initial_state, cfg)                # first run only
```
Use `graph.stream()` for the automatic segments so the live-run view paints each stage as it completes. **Durability:** `MemorySaver` is in-process (fine for a single-sitting demo; all artifacts also persist to Supabase). Swap → `PostgresSaver` on Supabase if in-flight runs must survive a Cloud restart. *(Pin the exact `Interrupt`/`get_state` field access to your installed `langgraph` version — the concept is stable, attribute names moved across 0.2.x.)*

**Zero-interrupt fallback:** if interrupts get fiddly, drive the pipeline stage-by-stage from Streamlit (`st.stop()` between human steps, state in `session_state` + Supabase). Same demo, same explainability, no stack change.

## 4. Run State Schema

Edge conditions are **orthogonal flags**, not a single enum — many can be active at once.

```python
# src/graph/state.py
from typing import TypedDict, Literal, Optional
EdgeFlag = Literal["funding_round","new_role","ambiguous_name","no_signal",
                   "sensitive_news","stale_signals","account_collision"]

class RunState(TypedDict, total=False):
    run_id: str
    # Stage 1 — input (company required, person optional)
    prospect_name: Optional[str]
    company: str
    company_key: str                 # normalized for history match
    mode: Literal["personalized","account"]
    product_description: Optional[str]   # from Seller Profile (set once), per-run overridable
    outreach_goal: Optional[str]
    extra_context: Optional[str]
    # Account awareness (pre-research)
    account_contacts: list[dict]     # prior same-company runs: {name,role,hook,run_id}
    # Stage 2 — research
    research: list[dict]             # [{category,title,url,snippet,published_date,age_days}]
    research_categories_done: list[str]
    research_from_cache: bool
    # Edge flags (orthogonal)
    flags: list[EdgeFlag]
    signal_freshness: Literal["fresh","stale","very_stale"]
    candidate_identities: list[dict] # ambiguous_name
    company_level_only: bool         # no_signal / account mode
    edge_evidence: dict
    # Stage 3/4 — signals
    signals: list[dict]
    # Stage 5
    selected_signal_id: Optional[str]
    user_instructions: Optional[str]
    # Stage 6
    hook: Optional[dict]
    framing_directive: str           # built from flags; steers the draft
    # Stage 7
    drafts: dict                     # {"email":{...},"linkedin":{...}}
    # Stage 8/9
    human_edits: list[dict]
    approval_status: Literal["draft","approved"]
    status: str
    errors: list[dict]
```

## 5. LangGraph Nodes & Routing

```
START → ingest → account_check → research → extract → flag ──(ambiguous_name?)─┐
                                                                               │ yes
   ┌───────────────────────────────────────────────────────────────────────┘
   ▼
disambiguate(⏸) → research(re-scoped) → extract → flag
   │ (no → straight through)
   ▼
score → signal_review(⏸) → hook → draft → draft_review(⏸) → approve(⏸) → store → END
```

| Node | Reads | Writes | Notes |
|---|---|---|---|
| `ingest` | input | normalized prospect, `mode`, `company_key`, `run_id` | Account mode if no person; create `runs` row (status=`researching`) |
| `account_check` | company_key | `account_contacts`, maybe `account_collision` flag | Supabase lookup of prior same-company runs; decide cache reuse |
| `research` | prospect | `research`, `research_from_cache` | multi-query Tavily **via cache**; writes `research_sources` |
| `extract` | research | `signals` | Claude extraction (§8a); writes `signals` |
| `flag` | signals + research | `flags`, `signal_freshness`, `candidate_identities`, `edge_evidence` | **deterministic checks + LLM classify** (§5.1) |
| `disambiguate` | candidates | resolved identity | **interrupt** — only if `ambiguous_name` |
| `score` | signals | scored `signals` | Claude scoring (§8b); sets `is_sensitive` |
| `signal_review` | scored signals + flags | `selected_signal_id`, `user_instructions` | **interrupt** (required HITL) |
| `hook` | selected signal + flags | `hook`, `framing_directive` | Claude hook (§8c); applies flag rules (§5.2) |
| `draft` | hook + prospect + framing | `drafts` | Claude email+LinkedIn (§8d) using `framing_directive` |
| `draft_review` | drafts | `human_edits` | **interrupt** — edit/re-tone/regenerate/change-signal |
| `approve` | final draft | `approval_status=approved` | **interrupt** (required HITL) |
| `store` | full state | — | finalize run; status=`completed` |

### 5.1 Edge detection split (the `flag` node)

**Deterministic (code in `src/edges/` — never ask the LLM to do date math or DB lookups):**
- `account_collision` → set in `account_check` if ≥1 prior run for `company_key`.
- `funding_round` → any signal with `type=funding` AND `age_days ≤ 60`.
- `new_role` → any signal `type∈{new_role,leadership_hire}` AND `age_days ≤ 90`.
- `signal_freshness` → `min(age_days over signals)`: ≤90 `fresh`, 91–180 `stale`, >180 `very_stale`. Set `stale_signals` flag when not `fresh`.
- `no_signal` → 0 usable signals after extraction (also forced by Account mode).

**LLM judgment (§8e classifier + scoring):**
- `ambiguous_name` → results describe ≥2 distinct people; collect `candidate_identities`.
- `sensitive_news` → set per-signal `is_sensitive` during scoring (§8b).

### 5.2 How flags change hook + draft

`framing_directive` is composed from active flags (priority top-down):

| Active flag | Hook rule | `framing_directive` added to draft |
|---|---|---|
| `funding_round` | **Elevate** funding signal to the hook | "High-intent: lead with the round; be direct/action-oriented; reference the post-raise build-out window." |
| `new_role` | Person-centric new-role hook | "Open with genuine congratulations on the move; speak to early-tenure priorities." |
| `sensitive_news` | **Never** auto-pick a sensitive signal; recommend alternative | "Avoid the sensitive topic entirely; lead with the safe angle." |
| `stale_signals` | Stale signal = context, **not** the opener | "Most recent signal is N months old — use forward-looking, hedged framing ('given where you were heading, I imagine you're now focused on…'); do NOT cite stale specifics as if fresh." |
| `account_collision` | Differentiate hook by role | "Person {n} of {m} at this account. Emphasize the angle for their function ({role}); do NOT reuse these prior hooks: {prior_hooks}." |
| `no_signal` / account mode | Company-level hook | "Limited/no personal info — keep it company-level and honest; don't imply personal research." |

## 6. Per-Stage Data Contracts

**Signal object (canonical):**
```json
{
  "id": "sig_01",
  "type": "funding | hiring | product_launch | exec_interview | partnership | expansion | leadership_hire | new_role | challenge | other",
  "description": "One–two sentence factual summary.",
  "source_url": "https://…",
  "source_title": "TechCrunch — …",
  "published_date": "2026-05-20",
  "age_days": 17,
  "funding_meta": {"round": "Series B", "amount": "$40M"},   // when type=funding
  "scores": {"recency": 9, "specificity": 7, "actionability": 8, "confidence": 8},
  "total_score": 8.0,
  "reasoning": "Why these scores.",
  "is_sensitive": false,
  "hook_sentence": "One-sentence angle this signal enables."
}
```

**Flags payload (from `flag` node):**
```json
{"flags": ["funding_round","account_collision"], "signal_freshness": "fresh",
 "candidate_identities": [], "edge_evidence": {"funding_round": "Series B $40M, 17d ago",
 "account_collision": "2 prior runs for acme.com"}}
```

**Hook object:**
```json
{"signal_id":"sig_01","hook_text":"…","why_it_matters":"…","why_chosen":"…",
 "why_alternatives_rejected":["sig_03 too generic","sig_02 sensitive"]}
```

**Draft object (per channel):**
```json
{"channel":"email","subject":"…","body":"…","tone":"consultative","version":1,"grounded_in":["source_url"]}
```

## 7. Research Query Strategy + Caching

Six core templates with `{prospect_name}` / `{company_name}` placeholders ([instruction_set.md §8](instruction_set.md)). In **Account mode** (no person), drop person-specific queries 1 & 5.

```python
QUERIES = [
  '"{prospect_name}" {company_name}',                                  # 1 prospect+company
  '{company_name} news 2026',                                          # 2 company news
  '{company_name} funding OR raised OR Series',                        # 3 funding
  '{company_name} hiring OR "is hiring" OR open roles',                # 4 hiring
  '"{prospect_name}" interview OR podcast OR keynote',                 # 5 exec interviews
  '{company_name} announcement OR launch OR partnership press release',# 6 press/announcements
]
```

**Caching (load-bearing):** wrap every Tavily/Claude call in a read-through cache keyed by a hash of the query/prompt → `cache/<sha>.json`. This (a) reuses sources on `account_collision`, (b) speeds builds, and (c) makes the demo deterministic/offline-capable.
```python
def cached(key, fn):
    p = CACHE_DIR / f"{sha(key)}.json"
    if p.exists(): return json.loads(p.read_text())
    res = fn(); p.write_text(json.dumps(res)); return res
```

- **All queries empty →** trip `no_signal` (do not fabricate); surface company-level fallback.
- **Name collision →** always pair name with `{company_name}`/role; if results map to clearly different companies/roles for the same name, set `ambiguous_name` + collect `candidate_identities`.
- **Rate limits / timeouts →** exponential backoff (1s,2s,4s; max 3); serialize or bound concurrency; proceed with partial results and log `errors`.

## 8. Prompt Templates

> Store in `src/llm/prompts.py`. All return **strict JSON**; the Claude wrapper validates + runs one JSON-repair retry on parse failure.

### (a) Signal Extraction
```
You are a B2B sales-research analyst. From the raw web results below, extract
discrete, factual SIGNALS about the prospect or their company. Do not invent
anything not present in the results. Ignore marketing fluff.

Prospect: {prospect_name_or_"(none — account mode)"}   Company: {company_name}
Context (optional): {extra_context}
RAW RESULTS (JSON): {research_json}

Return ONLY JSON:
{"signals":[{"type":"funding|hiring|product_launch|exec_interview|partnership|
expansion|leadership_hire|new_role|challenge|other","description":"<=2 factual
sentences","source_url":"...","source_title":"...","published_date":"YYYY-MM-DD
or null","funding_meta":{"round":"...","amount":"..."} (only if funding, else null),
"hook_sentence":"one sentence this could open with"}]}
If no real signals exist, return {"signals":[]}.
```

### (b) Signal Scoring
```
Score each signal for cold-outreach usefulness. Be a skeptical analyst.
Signals (JSON): {signals_json}
Today: {today}   Prospect: {prospect_name} ({role_if_known}) @ {company_name}

For EACH signal score 1–10 on: recency (use published_date vs today),
specificity (ties to THIS prospect/role > generic company > industry),
actionability (how naturally it opens a relevant conversation),
confidence (tier-1 press/official > blog/aggregator).
Set is_sensitive=true for layoffs, lawsuits, scandal, financial distress.

Return ONLY JSON: {"signals":[{"id":"...","scores":{"recency":n,"specificity":n,
"actionability":n,"confidence":n},"total_score":avg,"reasoning":"1–2 sentences",
"is_sensitive":bool}]}
```

### (c) Hook Selection + Justification
```
Choose the single best outreach angle. Selected signal: {selected_signal_json}
Other available signals: {other_signals_json}
Active flags + rules: {flag_rules}            # from §5.2
User instructions (OVERRIDE defaults if present): {user_instructions}
Prospect: {prospect_name} @ {company_name}. Goal: {outreach_goal}

Rules: never use an is_sensitive signal as the hook unless the user explicitly asks;
if funding_round is active, it is the hook; if the chosen signal is stale (>90d),
use it as context, not a literal "I saw you just…" opener.

Return ONLY JSON: {"hook_text":"angle, not a full email","why_it_matters":"...",
"why_chosen":"...","why_alternatives_rejected":["sig: reason", ...]}
```

### (d) Draft Generation
```
Write outreach grounded ONLY in the hook and facts below. No invented details,
no fake familiarity, no unsupported claims. Sound human, specific, brief.

Hook: {hook_json}
Prospect: {prospect_name}, {role_if_known} @ {company_name}
What we offer: {product_description}   Goal: {outreach_goal}
Framing directive (FOLLOW THIS): {framing_directive}    # from §5.2
Tone/length instructions (optional): {user_instructions}

Return ONLY JSON: {"email":{"subject":"...","body":"3 short paragraphs, 1 clear
CTA"},"linkedin":{"body":"<=400 chars, conversational, no subject"}}
```

### (e) Edge Classifier (LLM-judgment items only — run in `flag` node)
```
Decide ONLY whether the research describes multiple different people (ambiguity)
or no usable info. Date/funding/role/account flags are handled in code — ignore them.

Prospect: {prospect_name}  Company: {company_name}
Raw results (JSON): {research_json}

Return ONLY JSON: {"ambiguous_name":bool,"no_signal":bool,
"candidate_identities":[{"name":"...","company":"...","role":"...","source_url":"..."}],
"evidence":"1–2 sentences"}   (candidate_identities only when ambiguous_name=true)
```

## 9. Edge-Flag Specs (detection · pipeline change · user output · test case)

### (a) `funding_round` — high-intent window
- **Detect (code):** signal `type=funding` AND `age_days ≤ 60` (FUNDING_WINDOW_DAYS).
- **Pipeline:** elevate above all signals → becomes the hook; `framing_directive` = urgency/action-oriented.
- **User sees:** "🟢 High intent window" badge; selected signal shows round/amount/date; draft opens on the round.
- **Test (validate live):** any company that raised in the last ~30 days (TechCrunch/Crunchbase), run their VP/Head of Eng or Ops.

### (b) `new_role` — best buying trigger
- **Detect (code):** signal `type∈{new_role,leadership_hire}` AND `age_days ≤ 90`.
- **Pipeline:** boost person-centric signal; congrats/early-tenure framing; verify start date in evidence.
- **User sees:** "🆕 Started new role ~N weeks ago"; congratulatory hook.
- **Test (validate live):** a newly appointed CxO from the last ~2 months.

### (c) `ambiguous_name`
- **Detect (LLM §8e):** results describe ≥2 distinct people for the name.
- **Pipeline:** `disambiguate` **interrupt** → user picks → re-scope research → continue.
- **User sees:** "We found multiple people named X — which one?" + candidate cards (name/company/role/source).
- **Test:** a common name + large org (e.g. **"Michael Chen" @ a FAANG-scale company**); confirm ≥2 distinct profiles before demo.

### (d) `no_signal` (ghost / Account mode)
- **Detect (code):** 0 usable signals after extraction, OR all queries empty, OR no person given (Account mode).
- **Pipeline:** `company_level_only=True`; cap confidence; company-angle draft + honest framing.
- **User sees:** banner "Limited public info — using company-level signals; confidence lowered." Drafts don't imply personal research.
- **Test:** a junior IC at a tiny pre-seed/private company (or run **company only** to trigger Account mode).

### (e) `sensitive_news`
- **Detect (LLM §8b):** any signal `is_sensitive=true` (layoffs/lawsuit/scandal/distress < 6mo).
- **Pipeline:** exclude sensitive from auto-hook; recommend a non-sensitive alternative; if none, advise pausing outreach.
- **User sees:** "⚠️ Sensitive context detected — we won't lead with this. Recommended safe angle: …" Sensitive signals shown but locked unless user overrides.
- **Test (validate live):** a company with recent public layoffs/litigation (check a layoffs tracker the day before; don't hard-code).

### (f) `stale_signals` — freshness honesty
- **Detect (code):** `min(age_days)` > 90 → `stale`; > 180 → `very_stale`.
- **Pipeline:** stale signal becomes context, not opener; `framing_directive` = forward-looking/hedged.
- **User sees:** per-signal freshness indicator color-coded by age; banner "Most recent signal is N months old — draft uses forward-looking framing." SDR can still proceed.
- **Test:** a mid-market company in a non-trending industry with no recent news; show freshness flags + hedged draft.

### (g) `account_collision` — account-based selling
- **Detect (code):** ≥1 prior run for `company_key` in Supabase (checked in `account_check`).
- **Pipeline:** reuse research cache (skip re-query); `framing_directive` = "person N of M, differentiate by role, avoid prior hooks."
- **User sees:** badge "N other contacts from {company} in history" + the prior hooks so the SDR confirms no overlap.
- **Test:** run two people at the same company back-to-back (e.g., a CEO then a CTO); dashboard flags the shared account; drafts show differentiated hooks.

## 10. Happy-Path Demo Prospects (real, high-signal — re-validate live)

> News is time-sensitive: run each through Tavily right before recording/interview and pick the 2 with the strongest fresh signals.

1. **Aravind Srinivas — CEO, Perplexity AI**  2. **Winston Weinberg — CEO, Harvey AI**
3. **Eric Glyman — CEO, Ramp**  4. **Ivan Zhao — CEO, Notion**

## 11. Data Model (Supabase)

```sql
create table seller_profile (             -- single row; what we sell (set once, reused per run)
  id int primary key default 1,
  product_description text, value_prop text,
  default_tone text, updated_at timestamptz default now()
);
create table runs (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz default now(),
  prospect_name text, company text not null, company_key text not null,
  mode text default 'personalized',
  product_description text, outreach_goal text, extra_context text,
  status text, flags jsonb default '[]', signal_freshness text,
  chosen_signal_id uuid, approval_status text default 'draft'
);
create index on runs (company_key);          -- powers account_collision
create table research_sources (
  id uuid primary key default gen_random_uuid(), run_id uuid references runs(id),
  query_hash text, category text, title text, url text, snippet text,
  published_date date, age_days int, raw jsonb, created_at timestamptz default now()
);
create table signals (
  id uuid primary key default gen_random_uuid(), run_id uuid references runs(id),
  type text, description text, source_url text, published_date date, age_days int,
  funding_meta jsonb, recency int, specificity int, actionability int, confidence int,
  total_score numeric, reasoning text, is_sensitive bool default false,
  hook_sentence text, created_at timestamptz default now()
);
create table hooks (
  id uuid primary key default gen_random_uuid(), run_id uuid references runs(id),
  signal_id uuid references signals(id), hook_text text, why_it_matters text,
  why_chosen text, why_alternatives_rejected jsonb, created_at timestamptz default now()
);
create table drafts (
  id uuid primary key default gen_random_uuid(), run_id uuid references runs(id),
  channel text, version int default 1, subject text, body text, tone text,
  is_approved bool default false, created_at timestamptz default now()
);
create table human_actions (
  id uuid primary key default gen_random_uuid(), run_id uuid references runs(id),
  stage text, action text, payload jsonb, created_at timestamptz default now()
);
```

## 12. Failure-Handling Matrix

| Failure | Detection | Response | User sees |
|---|---|---|---|
| Tavily 0 results | empty across all queries | route to `no_signal` fallback | "No public signal — company-level fallback, lower confidence" |
| Claude malformed JSON | parse error | one repair-retry, then degrade to raw + flag | "Re-formatting model output…"; never crash |
| No web/LinkedIn presence | 0 person-level signals | `no_signal` company-level mode | honest limitation banner |
| API timeout | exception/timeout | backoff ×3, then partial + log `errors` | per-stage "retrying… / partial results" |
| **Same person** run twice | match name+company in `runs` | surface prior run; offer view/run-fresh | "You've researched this person before — open previous run?" |
| **Same company**, new person | `company_key` match, different person | `account_collision` (NOT a dup) | "N other contacts at this account — differentiating angle" |
| Rate limit (429) | status code | backoff; serialize; serve cache | "waiting on rate limit" |

## 13. Repo Structure

```
gtm/
├── app.py
├── requirements.txt
├── .env.example
├── .streamlit/{config.toml, secrets.toml(gitignored)}
├── cache/                       # per-query Tavily/Claude cache (demo-safe)
├── src/
│   ├── config.py
│   ├── graph/{state.py, build.py, nodes/*.py}
│   ├── edges/checks.py          # deterministic flag logic
│   ├── providers/{base.py, tavily_provider.py, cache.py}
│   ├── llm/{client.py, prompts.py}
│   ├── db/{supabase_client.py, schema.sql}
│   └── ui/{live_run.py, dashboard.py, components.py, styles.css}
└── tests/fixtures/              # cached responses for offline demo fallback
```

## 14. Models & Config

- **LLM (Claude):** default `claude-sonnet-4-6` for extraction/scoring/draft; consider `claude-opus-4-8` for **hook selection** (showcase reasoning); `claude-haiku-4-5-20251001` for the lightweight classifier. Finalize in Phase 3 (consult the `claude-api` skill for current params/pricing).
- **Tunables (`config.py`):** `FRESH_DAYS=90`, `VERY_STALE_DAYS=180`, `FUNDING_WINDOW_DAYS=60`, `NEW_ROLE_DAYS=90`, `SENSITIVE_WINDOW_DAYS=180`, `NUM_QUERIES=6`, `MAX_SIGNALS_SHOWN=5`, `CACHE_DIR`, retry/backoff settings.

## 15. What Breaks First (build defensively here)

1. **Streamlit/LangGraph state across reruns** → prove §3 (`@st.cache_resource` + thread_id + a 2-node toy interrupt) before any UI polish.
2. **Claude JSON adherence** → strict-JSON + repair-retry from day one.
3. **Live API flakiness in the demo** → the per-query cache (§7) makes rehearsed runs deterministic/offline.
4. **Stale demo news** → validate all test prospects live the day before; caching freezes the validated run.
