# Progress Tracker — Living Log

> Update this as work happens. It is the running record of **status, decisions, assumptions, and blockers** — and the source for the live-pitch "here's what I decided and why" narrative. Backlog: [build_tracker.md](build_tracker.md).

**Last updated:** 2026-06-07 · **Target submission:** 2026-06-08 · **Current focus:** Phase 5 done (Live Run UI live at :8501) → next: Phase 6 (Dashboard)

---

## 1. Phase Status

| Phase | Day | Status | Notes |
|---|---|---|---|
| Planning docs | — | ✅ Done | overview, instruction_set, architecture, trackers created |
| 0 · Setup & accounts | 1 | 🟡 In progress | Tavily + Supabase keys in `.env` & verified; **Anthropic key still needed** |
| 1 · Data layer | 1 | ✅ Done | Schema applied (RLS on); `supabase_client.py` verified end-to-end (seller_profile + runs round-trip) |
| 2 · Research layer | 1 | ✅ Done | `TavilyProvider`: 6 queries, account-mode drop, backoff, cache; 12 tests pass; live smoke test: 30 sources |
| 3 · LLM layer | 1 | ✅ Done | Gemini (not Anthropic — D14); `gemini-2.5-flash` + `gemini-2.5-flash-lite`; call_json + 5 helpers; smoke test passes |
| 4 · Orchestration | 1 | ✅ Done | **Happy-path milestone achieved** — 13 nodes, 4 interrupts (disambiguate/signal_review/draft_review/approve), full headless run verified in Supabase |
| 5 · Live run view | 2 | ✅ Done | Input form, pipeline summary strip, all 4 interrupt panels (disambiguate/signal_review/draft_review/approve), completed view, Settings/Seller Profile, app routing with `@st.cache_resource` |
| 6 · Dashboard | 2 | ✅ Done | Summary metrics, filters (status/mode/search), run expanders with 5 tabs (Overview/Signals/Hook/Drafts/Actions), lazy child-record loading, Refresh clears cache |
| 7 · Edge cases (×7) | 2 | ⬜ Not started | order: no_signal/Account → funding → stale → account_collision → new_role → sensitive → ambiguous |
| 8 · Polish | 3 | ⬜ Not started | |
| 9 · Deploy | 3 | ⬜ Not started | |
| 10 · Demo prep | 3 | ⬜ Not started | |

Legend: ⬜ not started · 🟡 in progress · ✅ done · 🔴 blocked

---

## 2. Decision Log

| # | Date | Decision | Rationale |
|---|---|---|---|
| D1 | 2026-06-06 | **UI = Streamlit + custom theming** | Single codebase + speed; theming because UI is explicitly graded; avoids 2x cost of a React frontend on a 3-day clock |
| D2 | 2026-06-06 | **Build all 4 edge cases** (`new_role`, `ambiguous_name`, `no_signal`, `sensitive_news`) — *superseded by D10 → 7 flags* | Reconciles the two source briefs; distinct behaviors best demonstrate judgment (assessment allows 2–4) |
| D3 | 2026-06-06 | **Stack locked:** Streamlit · LangGraph · Claude · Tavily · Supabase · Streamlit Cloud | Matches brief; each layer maps to a graded capability |
| D4 | 2026-06-06 | **3-day aggressive build** w/ Claude Code as build partner | User availability; ignore the "one week" framing |
| D5 | 2026-06-06 | **LangGraph checkpointer (transient run state) separated from Supabase (durable history)** | Survives Streamlit Cloud's ephemeral filesystem; clean audit trail |
| D6 | 2026-06-06 | **Public information only** (no private LinkedIn scraping) | Tavily capability + ethics/scope; "LinkedIn signal" = public/indexed content |
| D7 | 2026-06-06 | **Two draft channels: Email + LinkedIn** | Per brief; shows the same hook adapts across formats |
| D8 | 2026-06-06 | **Headless end-to-end first, UI second** | De-risks the #1 issue (Streamlit↔LangGraph state) before polish |
| D9 | 2026-06-06 | **Account mode: Company required, Person optional** | Company is the anchor for research/disambiguation/fallback; person drives personalization. Company-only degrades transparently (reuses `no_signal` path) instead of erroring. Deliberate deviation from the "both required" brief |
| D10 | 2026-06-06 | **Edge model = orthogonal flags (7), not one enum; deterministic-first detection** | A run can be e.g. `funding_round` + `account_collision` at once. Date/funding/role/account checks are code (LLM does no date math); only `ambiguous_name`/`sensitive` use LLM judgment |
| D11 | 2026-06-06 | **Per-query research cache layer** | Load-bearing for `account_collision` (reuse sources); also makes demos deterministic/offline and kills API-flakiness risk |
| D12 | 2026-06-07 | **Seller Profile — product set once, reused per run** | What we sell is constant across prospects; configured once in Settings, auto-applied. Per-run form only captures what differs (company/person/role/goal/context). Optional per-run override. Mirrors real SDR tooling |
| D13 | 2026-06-07 | **Supabase: RLS enabled + server uses secret key** | RLS on locks tables from the public/anon key; the server-side `sb_secret_` key bypasses RLS, so no policies needed. Cleaner security story than RLS-off. Key lives in `.env` (gitignored) / Streamlit secrets on deploy |
| D14 | 2026-06-07 | **LLM = Gemini (google-genai SDK) instead of Anthropic** | User has Claude Pro subscription (chat-only, no API); Gemini free tier via AI Studio is the best free alternative with comparable JSON output quality. Models: `gemini-2.5-flash` (main) + `gemini-2.5-flash-lite` (classifier). Prompts unchanged — model-agnostic. |

---

## 3. Assumptions (referenceable in the live pitch)

| # | Assumption | If wrong… |
|---|---|---|
| A1 | "LinkedIn activity" = publicly indexed content via Tavily, not private API | Would need a LinkedIn provider (future enhancement) |
| A2 | Test inputs are real public companies/people (per assessment FAQ for PS-3) | Swap to fabricated-but-plausible inputs |
| A3 | `new_role` window = 90 days; `sensitive_news` window = ~180 days | Tunable in `config.py` |
| A4 | Single-user tool; no auth/multi-tenancy in MVP | Add auth later |
| A5 | Same **person** re-run surfaces prior run; same **company** triggers `account_collision` (not a dup) | Adjust dedupe/collision policy |
| A6 | Claude returns strict JSON with a repair-retry safety net | Tighten prompts / add schema validation |
| A7 | Freshness windows: `stale` > 90d, `very_stale` > 180d | Tune in `config.py` |
| A8 | Funding "high-intent window" = 60 days | Tune in `config.py` |
| A9 | Account collisions keyed by normalized company name/domain | Refine matching (legal entity vs brand) |

---

## 4. Blockers / Open Questions
- _None open._ (Add as they arise: blocker · impact · what's needed to unblock.)

---

## 5. Demo-Prep Checklist (fill on Day 3)
- [ ] Happy-path prospect #1 validated live: ____________________
- [ ] Happy-path prospect #2 validated live: ____________________
- [ ] `funding_round` input confirmed (raised < 60d): ____________________
- [ ] `account_collision` pair confirmed (2 people, same company): ____________________
- [ ] `stale_signals` input confirmed (mid-market, no recent news): ____________________
- [ ] `no_signal` / Account-mode input confirmed (or company-only): ____________________
- [ ] `new_role` input confirmed (started < 90d): ____________________
- [ ] `sensitive_news` input confirmed (recent layoffs/litigation): ____________________
- [ ] `ambiguous_name` input confirmed (≥2 distinct matches): ____________________
- [ ] Run order locked & rehearsed
- [ ] Offline/fixture fallback tested
- [ ] ≤5-min video recorded
- [ ] Live URL + video submitted to hiring coordinator

---

## 6. Changelog
- **2026-06-06 (1)** — Analyzed `assessment.txt` + both instruction files; resolved edge-case conflict (3 vs 4 → 4) and UI choice (Streamlit+theming). Created `project_overview.md`, `instruction_set.md`, `architecture.md`, `build_tracker.md`, `progress_tracker.md`. Consolidated `instruction-set.md` + `instruction.md` into the single `instruction_set.md` (originals removed; `assessment.txt` kept as canonical brief).
- **2026-06-06 (2)** — Added 3 edge cases (`stale_signals`, `account_collision`, `funding_round`) → **7 total**, modeled as orthogonal flags (D10). Adopted **Account mode** (D9: company required, person optional). Added **per-query cache layer** (D11). Updated all 5 docs: instruction_set §7/§7.1/§11/§14; architecture §4/§5/§5.1/§5.2/§8/§9/§11/§12; overview §6; build_tracker phases 1/2/4/5/6/7.
- **2026-06-07** — Added **Seller Profile** (D12): product/value-prop set once in Settings, reused per run; removed product from per-run required fields. Updated instruction_set §7/§7.1/§7.2/§13; architecture §2/§4/§11 (`seller_profile` table); build_tracker phases 1/5. Final consistency sweep done — **plan ready; cleared to start Phase 0.**
- **2026-06-07 — Scaffold + spike shipped.** Repo structure created (`app.py`, `src/{config,graph,edges,providers,llm,db,ui}`, `db/schema.sql`, `.streamlit/`, `requirements.txt`). Implemented real logic: `edges/checks.py` (deterministic flags) + `providers/cache.py` (read-through cache). **De-risk spike (`spike/`) proves LangGraph interrupt→checkpoint→resume** — the #1 risk. venv built (langgraph 1.2.4, streamlit 1.58); **14/14 tests pass**; apps compile; config reports keys missing as expected.
- **2026-06-07 — Supabase live (Phase 1 done).** Tavily + Supabase keys in `.env`. Schema applied via SQL editor with **RLS enabled** (D13); switched `SUPABASE_KEY` to the `sb_secret_` key (bypasses RLS). Implemented real `src/db/supabase_client.py` (client + seller_profile + runs + child-record helpers); `scripts/check_supabase.py` round-trip **passes**; test row cleaned. **Remaining for Phase 0: Anthropic key.** Next: Phase 2 (Tavily research layer).
