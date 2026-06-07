# Build Tracker — Phased Task Plan

> The **what-to-build** backlog. Check items off as you go; record status/notes in [progress_tracker.md](progress_tracker.md). Design reference: [architecture.md](architecture.md). Spec: [instruction_set.md](instruction_set.md).
>
> **Timeline:** ~3 working days. Day 1 = 2026-06-06 · Day 2 = 2026-06-07 · Day 3 = 2026-06-08.
> **Golden rule (from the assessment):** get the happy path running end-to-end *before* any edge case or polish.

---

## Day 1 — Foundations + Happy Path (headless)

### Phase 0 — Setup & Accounts
- [ ] Create **Anthropic (Claude) API** key + add billing/credits
- [ ] Create **Tavily** account + API key (note free-tier limits)
- [ ] Create **Supabase** project; grab URL + anon/service keys
- [ ] Create **Streamlit Community Cloud** account (deploy later)
- [ ] Scaffold repo per [architecture.md](architecture.md) §13; `python -m venv`, `requirements.txt`
- [ ] `requirements.txt`: `streamlit langgraph langchain-core anthropic tavily-python supabase python-dotenv`
- [ ] `.env.example` + `.streamlit/secrets.toml` (gitignored); `config.py` loads keys
- [ ] `git init`; first commit; `.gitignore` (secrets, venv, fixtures cache if large)
- **Done when:** repo runs `streamlit run app.py` showing a placeholder; all 3 keys load via `config.py`.

### Phase 1 — Data Layer (Supabase)
- [ ] Run `src/db/schema.sql` in Supabase (7 tables incl. `seller_profile`, [architecture.md](architecture.md) §11)
- [ ] `supabase_client.py` + helpers: `create_run`, `save_sources`, `save_signals`, `save_hook`, `save_drafts`, `log_action`, `list_runs`, `get_run`, `find_runs_by_company` (powers `account_collision`), `get_seller_profile`/`save_seller_profile`
- [ ] Index on `runs.company_key`
- [ ] Smoke test: insert + read a dummy run
- **Done when:** a dummy run round-trips to Supabase and back.

### Phase 2 — Research Layer (Tavily)
- [ ] `providers/base.py` interface (`search(prospect, company) -> list[Source]`)
- [ ] `providers/cache.py`: per-query read-through cache ([architecture.md](architecture.md) §7) — reused on `account_collision` + makes demos deterministic/offline
- [ ] `tavily_provider.py`: 6 query templates, backoff, partial-failure handling; drop person-queries in Account mode
- [ ] Normalize results → `{category,title,url,snippet,published_date,age_days}`
- [ ] Smoke test on 1 real prospect; eyeball signal richness; confirm cache hit on 2nd run
- **Done when:** one prospect returns deduped, categorized sources, and a repeat query is served from cache.

### Phase 3 — LLM Layer (Claude)
- [ ] `llm/client.py`: Claude wrapper with strict-JSON parse + one repair-retry + timeout/backoff
- [ ] `llm/prompts.py`: extraction, scoring, hook, draft, edge-classifier ([architecture.md](architecture.md) §8)
- [ ] Unit-test each prompt against saved Tavily output → valid JSON
- [ ] Finalize model IDs (consult `claude-api` skill)
- **Done when:** raw research → signals → scores → hook → drafts as valid JSON in a script.

### Phase 4 — Orchestration (LangGraph)
- [ ] **De-risk spike first:** 2-node toy graph with one `interrupt()`, driven from Streamlit, `@st.cache_resource` graph + thread_id — prove pause→render→resume ([architecture.md](architecture.md) §3)
- [ ] `graph/state.py` (`RunState` with **flags list + `signal_freshness` + `mode`**)
- [ ] `edges/checks.py`: deterministic flag logic (freshness, funding<60d, role tenure, no_signal)
- [ ] `graph/nodes/*`: ingest (Account mode + `company_key`), account_check, research, extract, **flag**, score, hook (applies flag rules), draft (uses `framing_directive`), store
- [ ] `graph/build.py`: assemble graph + **checkpointer** + thread_id
- [ ] Wire Supabase writes into each node
- [ ] **Headless end-to-end run** (no UI) via a script with `interrupt()`s auto-resumed
- **Done when:** `python -m scripts.run_once "Aravind Srinivas" "Perplexity"` completes a full run and persists it. ✅ **HAPPY PATH MILESTONE**

---

## Day 2 — UI + Human-in-the-Loop + Edge Cases

### Phase 5 — Live Run View
- [ ] `app.py` routing (Live Run / Dashboard / **Settings**) + `session_state` (thread_id, pending_resume) + `@st.cache_resource` graph
- [ ] `ui/settings.py`: **Seller Profile** page — product/value-prop set once, persisted, reused per run
- [ ] Stage-1 input form: **Company required, Person optional** (Account-mode note); product pre-filled from Seller Profile (overridable)
- [ ] Implement the resume pattern ([architecture.md](architecture.md) §3)
- [ ] `ui/live_run.py`: stage list with status badges ([instruction_set.md](instruction_set.md) §9), flag/freshness badges, live data previews (sources, signals+scores, hook, drafts)
- [ ] HITL interrupts rendered: **signal review** (accept/select/regenerate/instructions), **draft review** (edit/tone/length/regenerate/change-signal), **approval**
- **Done when:** a full happy-path run is driven entirely from the UI, including the 3 human steps.

### Phase 6 — Dashboard
- [ ] `ui/dashboard.py`: table with columns Timestamp · Prospect · Company · Status · Chosen Signal · Signal Type · Approval · **Flags** ([instruction_set.md](instruction_set.md) §10)
- [ ] Expandable detail: research, signals, scores, hook, draft, human edits
- [ ] Reads live from Supabase; survives app restart
- **Done when:** completed runs appear in history and reopen with full detail.

### Phase 7 — Edge Cases (one at a time — deterministic first, interrupt last)
- [ ] **`no_signal` / Account mode** (simplest) — company-level mode + lowered confidence + banner; also handles company-only input
- [ ] **`funding_round`** — elevate above all signals; urgency framing; "high intent" badge (deterministic, <60d)
- [ ] **`stale_signals`** — freshness flag (90/180d) + forward-looking hedged draft + per-signal freshness indicator
- [ ] **`account_collision`** — history lookup → reuse cache + differentiate hook by role + show prior hooks
- [ ] **`new_role`** — boost person-centric signal + congrats framing (deterministic, <90d)
- [ ] **`sensitive_news`** — flag (LLM is_sensitive), exclude from auto-hook, recommend safe alternative
- [ ] **`ambiguous_name`** — disambiguation interrupt + candidate cards + resume (most complex)
- [ ] Each: detection → pipeline change → distinct user output ([architecture.md](architecture.md) §9). Confirm flags compose (e.g. `funding_round` + `account_collision`)
- **Done when:** each flag is reproducible from a known input and visibly behaves differently.

---

## Day 3 — Polish, Deploy, Demo

### Phase 8 — Theming & Polish
- [ ] `.streamlit/config.toml` theme + `ui/styles.css`; consistent cards/badges/spacing
- [ ] Loading/empty/error states everywhere; copy review pass
- [ ] `tests/fixtures/` cached responses + a "demo/offline" toggle as live-API fallback
- **Done when:** UI looks intentional and never shows a raw traceback.

### Phase 9 — Deploy
- [ ] Push to GitHub; deploy on Streamlit Community Cloud; add secrets
- [ ] Verify Supabase reachable from Cloud; run a full live run on the deployed URL
- **Done when:** the public URL completes a happy path + 1 edge case live.

### Phase 10 — Demo Prep
- [ ] **Validate all demo prospects live** (happy path + each edge case) — pick freshest
- [ ] Lock the run order; rehearse; prep fallback inputs
- [ ] Record ≤5-min video: happy path live + ≥1 edge case, narrated ([assessment.txt](assessment.txt))
- [ ] Finalize assumptions/decisions talking points from [progress_tracker.md](progress_tracker.md)
- [ ] Submit: live URL + video link to hiring coordinator
- **Done when:** both deliverables submitted; demo rehearsed end-to-end.

---

## Definition of Done (whole project)
Runs end-to-end on real input · real research · meaningful signals · explainable ranking · human in control · all 7 edge flags deliberate · history persists · every decision explainable live. (See [instruction_set.md](instruction_set.md) §15.)
