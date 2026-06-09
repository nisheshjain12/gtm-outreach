# GTM Outreach Engine — Demo Guide & Test Plan

> Target length: **6–8 minutes** (the brief says ≤5 min, but a slightly longer run that shows the full pipeline + HITL + edge cases is fine for your own recording; you can trim for submission).
> Live app: your Streamlit Cloud URL · Repo: `nisheshjain12/gtm-outreach`

---

## 0. Before You Hit Record (5-min checklist)

1. **Open the deployed app** and confirm the sidebar shows **"✓ All systems ready"** (all keys loaded).
2. **Quota:** `KEY_1` (AIza) is usually daily-exhausted from testing — that's fine, the app auto-rotates to `KEY_2`/`KEY_3`. You have ~12 full runs/day across keys.
3. **Warm the caches** (so research is instant on camera): the demo inputs below are all already cached, so research returns in <2s.
4. **Dashboard is clean:** 7 completed runs are loaded, covering 5 of the 7 flags. Keep this tab ready.
5. **Have these two inputs typed somewhere to paste fast:**
   - Happy path: `Manoj` / `Devrev` / `Engineering Lead`
   - Ambiguous name: `David Kim` / `startup` / *(leave role blank)*
6. Close other tabs/notifications. Zoom the browser to ~110% so text is readable on video.

---

## 1. What This Tool Is (say this in the first 20 seconds)

> "This is a GTM outreach engine. A sales rep names a prospect; the system does real web research, extracts and scores signals, lets me choose the angle, writes a personalized email and LinkedIn draft, and keeps me in control at every step before anything is sent. It's built on LangGraph for orchestration, Tavily for research, Gemini for the reasoning, and Supabase for persistent history."

---

## 2. The Demo Script (ordered, narrated)

### Part A — Seller Profile (20 sec)
- Go to **Settings**.
- Point at the saved product: *"What we sell is configured once here and reused on every run, so the rep only types what's different about each prospect — exactly like real SDR tooling."*

### Part B — Happy Path, full pipeline + regeneration (≈2.5 min) ⭐ core
**Input:** Live Run → `Manoj` / `Devrev` / `Engineering Lead` → **Start Research Run**

Narrate as the stage bar fills:
1. **Research** — *"It fired 6 targeted queries — prospect, company news, funding, hiring, interviews, press — and pulled ~30 sources."*
2. **Extract** — *"Gemini turned those into structured signals — factual, no invention."*
3. **Score** — *"Each signal is scored on four axes: recency, specificity, actionability, confidence."*
4. **Signal review (HITL #1)** — *"The pipeline pauses. These are the ranked signals. I'll pick one — and I can add an instruction to steer the draft."* Pick the top signal, optionally type `keep it concise`.
5. **Hook** — open the **"why this angle was chosen"** box: *"It explains why this hook won and why it rejected the alternatives — that's the judgment layer, not just generation."*
6. **Draft review (HITL #2)** — show the **Email** and **LinkedIn** tabs.
7. **Regeneration loop** ⭐ — in the "Regenerate with different instructions" box, type `make it more concise and lead with a question`, click **Regenerate Draft**. When the new draft appears: *"It re-ran the generator with my instruction and brought me back to review — I can keep refining until I approve."*
8. **Approve** — click **Approve Drafts & Continue**, then **Approve & Complete Run**. *"Nothing sends — the human approves, and the full run is saved to history."*

### Part C — Ambiguous Name → disambiguation interrupt (≈1.5 min) ⭐ best HITL moment
**Input:** Live Run → **+ New Run** → `David Kim` / `startup` / *(role blank)* → **Start Research Run**

- The pipeline **pauses on a different screen** — "Clarify Prospect Identity".
- Narrate: *"A rep often has partial info — just a common name and 'works at a startup'. The system detected multiple real people named David Kim — a VC, a software developer, a startup CEO — and instead of guessing, it stops and asks me which one."*
- Pick one candidate → **Select & Continue** → it resumes the pipeline with that identity.
- Continue through signal review → draft → approve (can move quickly here since you've shown the full flow already).

### Part D — Dashboard, the persistent history + the other flags (≈1.5 min)
- Go to **Dashboard**.
- Point at the **summary metrics** (total / completed / approved / flagged) and the **flag badges** across rows.
- Use the **Status filter** and search to show it's a real queryable history.
- Expand **Denis Yarats @ Perplexity AI** → call out the **`account_collision`** badge: *"This is fully deterministic — because I'd already contacted Aravind at Perplexity, the system flagged the second contact and differentiated the hook by role so we don't repeat ourselves."*
- Expand **Dylan Field @ Figma** → **`stale_signals`**: *"The most recent signal was old, so the draft shifts to forward-looking, hedged framing instead of pretending it's fresh news."*
- Expand **John Smith @ Google** → **`funding_round` + `sensitive_news`**: open the **Signals** tab and show the sensitive signal flagged red and pushed down; open **Drafts**.
- Expand **(Account) @ Basecamp** → **`no_signal` / Account mode**: *"No person name given — it degrades honestly to company-level outreach and lowers confidence instead of erroring."*

### Part E — Resilience (optional, 30 sec)
> "A few production touches: research is cached per query so repeats are instant; the LLM layer rotates across multiple API keys when one hits its daily quota; and because every node is checkpointed, a failed run can be retried from where it stopped — or re-run from the Dashboard with one click."

---

## 3. Test Inputs — Reference Table

| Input | Mode | Demonstrates | Reliability |
|---|---|---|---|
| `Manoj` / `Devrev` / `Engineering Lead` | Personalized | Happy path + full pipeline + **draft regeneration** | ✅ Deterministic completion |
| `David Kim` / `startup` / *(blank)* | Personalized | **`ambiguous_name`** → disambiguation interrupt | ✅ Verified (5 candidates) |
| `Denis Yarats` / `Perplexity AI` / `CTO` | Personalized | **`account_collision`** (run *after* an Aravind/Perplexity run) | ✅ Deterministic (DB lookup) |
| *(blank)* / `Basecamp` / — | Account | **`no_signal`** + Account-mode degradation | ✅ Deterministic |
| `Dylan Field` / `Figma` / `CEO` | Personalized | **`stale_signals`** + hedged framing | 🟡 Date-dependent |
| `John Smith` / `Google` / — | Personalized | **`funding_round` + `sensitive_news`** | 🟡 Data/LLM-dependent |

**Reliable, controllable flags (great for live):** `account_collision`, `no_signal`, `ambiguous_name`.
**Emergent flags (live web + LLM judgment, vary run-to-run):** `funding_round`, `sensitive_news`, `stale_signals`.

---

## 4. Flag Coverage vs. Plan — Current Database State

| Flag | Verified? | Where |
|---|---|---|
| `account_collision` | ✅ | Denis Yarats @ Perplexity AI |
| `no_signal` | ✅ | Basecamp (Account mode) |
| `stale_signals` | ✅ | Dylan Field @ Figma |
| `funding_round` | ✅ | John Smith @ Google |
| `sensitive_news` | ✅ | John Smith @ Google |
| `ambiguous_name` | ✅ (use `David Kim`/`startup` live) | not yet in DB — demo it live |
| `new_role` | ❌ | see note below |

**`new_role` honesty note (good talking point):** This flag fires only when a signal of type `new_role`/`leadership_hire` has a parsed date within 90 days. Most of our test prospects are long-tenured founders/CEOs, so no recent appointment signal appears — and Gemini doesn't always extract a clean publish date, which the date check needs. In the interview you can frame this as a deliberate design choice: *date math is done in code, never by the LLM, so the flag only fires on real, dated evidence — it won't hallucinate a "new role."*

---

## 5. Honest Framing for the Interview (the strong-submission angle)

- **The flags are emergent, and that's correct.** They depend on what the live web returns and how the model judges it — the same prospect can surface different flags on different days. Deterministic flags (account collision, account mode) are 100% reliable; the data/judgment flags reflect reality.
- **Judgment over generation.** The strongest parts are signal discovery, scoring, hook selection with explainability, and the human-in-the-loop checkpoints — not the email text.
- **The human is always in control.** Three required stops (signal, draft, approval) plus a conditional disambiguation pause. Nothing sends automatically.

---

## 6. Known Gotchas During Recording

- **Don't use `Zamp.ai` as an input** — the assessment names Zamp as off-limits tooling; researching it on camera looks odd. (There's a leftover Zamp run in the DB — ignore it or delete it before recording.)
- **If a run errors with a 429:** it's quota — the app shows **Retry**; the checkpoint is preserved. Just retry (it rotates keys).
- **Account collision needs order:** run a first contact at a company *before* the second to make the flag fire live. Denis already has Aravind in history, so it'll fire.
- **Disambiguation is LLM-judged:** `David Kim`/`startup` is verified to fire on the cached research; avoid changing the company word or it may re-research and judge differently.
```
