"""Live Run view (instruction_set.md §9, architecture.md §3).

Stage-by-stage pipeline visibility with 4 HITL interrupt panels:
  disambiguate -> signal_review -> draft_review -> approve
"""
from __future__ import annotations

import uuid

import streamlit as st
from langgraph.types import Command

from src import config
from src.db import supabase_client as db
from src.ui.components import (
    flag_badge,
    freshness_badge,
    inject_css,
    render_signal_card,
)


# ── Session helpers ──────────────────────────────────────────────────────────

def _reset_session() -> None:
    st.session_state.thread_id  = str(uuid.uuid4())
    st.session_state.run_started = False
    st.session_state.pop("run_error", None)


def _get_interrupt_payload(snap) -> dict:
    try:
        return snap.tasks[0].interrupts[0].value
    except (IndexError, AttributeError):
        return {}


# ── Top-level entry point ────────────────────────────────────────────────────

def render(graph) -> None:
    inject_css()

    if "thread_id" not in st.session_state:
        _reset_session()

    col_title, col_new = st.columns([5, 1])
    with col_title:
        st.subheader("Live Run")
    with col_new:
        if st.button("+ New Run", width='stretch'):
            _reset_session()
            st.rerun()

    cfg = {"configurable": {"thread_id": st.session_state.thread_id}}

    if st.session_state.get("run_error"):
        st.error(f"Pipeline error — {st.session_state.run_error}")
        if st.button("Reset"):
            _reset_session()
            st.rerun()
        return

    if not st.session_state.get("run_started"):
        _render_input_form(graph, cfg)
    else:
        _render_run_view(graph, cfg)


# ── Input form ───────────────────────────────────────────────────────────────

def _render_input_form(graph, cfg: dict) -> None:
    st.markdown(
        "Enter prospect details below. **Company is required** — person name is optional "
        "(omit for Account-mode company-level outreach)."
    )

    profile = db.get_seller_profile() or {}

    with st.form("prospect_form"):
        company = st.text_input(
            "Company *",
            placeholder="e.g. Perplexity AI",
        )
        col1, col2 = st.columns(2)
        with col1:
            prospect = st.text_input(
                "Prospect name",
                placeholder="e.g. Aravind Srinivas   (blank = Account mode)",
            )
        with col2:
            role = st.text_input(
                "Role / Title",
                placeholder="e.g. CEO & Co-founder",
            )

        goal = st.text_input(
            "Outreach goal",
            value="book a 20-minute discovery call",
        )
        context = st.text_area(
            "Extra context  (optional)",
            placeholder="e.g. Met at SaaStr; they mentioned scaling ops headcount",
            height=70,
        )

        st.markdown("---")
        st.caption("Product context — pre-filled from Seller Profile. Override per-run if needed.")
        product_override = st.text_area(
            "What you sell",
            value=profile.get("product_description", ""),
            placeholder="Configure once in Settings > Seller Profile",
            height=80,
        )

        submitted = st.form_submit_button(
            "Start Research Run", type="primary", width='stretch'
        )

    if submitted:
        if not company.strip():
            st.error("Company is required.")
            return

        initial_state = {
            "company":             company.strip(),
            "prospect_name":       prospect.strip() or None,
            "role":                role.strip() or None,
            "outreach_goal":       goal.strip() or None,
            "extra_context":       context.strip() or None,
            "product_description": product_override.strip() or None,
        }

        mode_label = "Account mode" if not prospect.strip() else f"Personalized — {prospect.strip()}"
        with st.spinner(f"Running pipeline ({mode_label}) — research + extract + score…"):
            try:
                graph.invoke(initial_state, config=cfg)
                st.session_state.run_started = True
            except Exception as exc:  # noqa: BLE001
                st.session_state.run_error = str(exc)
        st.rerun()


# ── Run view (after first invoke) ────────────────────────────────────────────

def _render_run_view(graph, cfg: dict) -> None:
    snap  = graph.get_state(cfg)
    state = snap.values

    _render_pipeline_summary(state)
    st.markdown("---")

    if not snap.next:
        if state.get("status") == "completed":
            _render_completed(state)
        else:
            st.info("Pipeline did not complete. Check the error above or start a new run.")
        return

    node    = snap.next[0]
    payload = _get_interrupt_payload(snap)

    if node == "disambiguate":
        _render_disambiguate(payload, state, graph, cfg)
    elif node == "signal_review":
        _render_signal_review(payload, state, graph, cfg)
    elif node == "draft_review":
        _render_draft_review(payload, state, graph, cfg)
    elif node == "approve":
        _render_approve(payload, state, graph, cfg)
    else:
        # Graph is checkpointed mid-pipeline at a non-interrupt node (e.g. after a
        # quota error in score/hook/draft). Offer a retry that re-enters from the
        # last checkpoint without re-running earlier nodes.
        st.warning(
            f"Pipeline stalled at `{node}` — usually caused by an API quota error. "
            "Click **Retry** to resume from the checkpoint (quota must be available)."
        )
        if st.button("Retry pipeline", type="primary"):
            with st.spinner(f"Resuming from `{node}`…"):
                try:
                    graph.invoke(None, config=cfg)
                except Exception as exc:  # noqa: BLE001
                    st.session_state.run_error = str(exc)
            st.rerun()


# ── Pipeline summary strip ────────────────────────────────────────────────────

def _render_pipeline_summary(state: dict) -> None:
    flags     = state.get("flags", [])
    freshness = state.get("signal_freshness")
    signals   = state.get("signals", [])
    research  = state.get("research", [])
    contacts  = state.get("account_contacts", [])
    mode      = state.get("mode", "—")
    prospect  = state.get("prospect_name") or "(Account mode)"
    company   = state.get("company", "")

    with st.expander(f"Pipeline — {prospect} @ {company}", expanded=True):
        # Stage progress row
        scored   = any(s.get("total_score") is not None for s in signals)
        stages = [
            ("Research",  bool(research)),
            ("Extract",   bool(signals)),
            ("Score",     scored),
            ("Hook",      bool(state.get("hook"))),
            ("Draft",     bool(state.get("drafts"))),
            ("Approved",  state.get("approval_status") == "approved"),
        ]
        parts = []
        active_set = False
        for name, done in stages:
            if done:
                parts.append(f'<span class="stage-done">&#10003; {name}</span>')
            elif not active_set:
                parts.append(f'<span class="stage-active">&#9654; {name}</span>')
                active_set = True
            else:
                parts.append(f'<span class="stage-wait">{name}</span>')
        arrow = '<span class="stage-arrow">&#8594;</span>'
        st.markdown(
            f'<div class="stage-progress">{arrow.join(parts)}</div>',
            unsafe_allow_html=True,
        )

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Sources found",  len(research))
        c2.metric("Signals",        len(signals))
        c3.metric("Mode",           mode.title())
        c4.metric("Freshness",      freshness or "—")

        if flags:
            badges = " ".join(flag_badge(f) for f in flags)
            st.markdown(f"**Flags:** {badges}", unsafe_allow_html=True)

        if freshness and freshness != "fresh":
            badge = freshness_badge(freshness)
            msg = (
                "Most recent signal is over 90 days old — draft will use forward-looking, hedged framing."
                if freshness == "stale"
                else "Most recent signal is over 180 days old — very stale; proceed with caution."
            )
            st.markdown(f"{badge} &nbsp;{msg}", unsafe_allow_html=True)

        if contacts:
            names = ", ".join(c.get("name") or "?" for c in contacts)
            st.info(
                f"**Account collision** — {len(contacts)} prior contact(s) at this company: {names}. "
                "Hook will be differentiated by role."
            )

        if mode == "account":
            st.warning(
                "**Account mode** — no person name given. "
                "Outreach will be company-level; confidence is lowered."
            )


# ── Disambiguate interrupt ────────────────────────────────────────────────────

def _render_disambiguate(payload: dict, state: dict, graph, cfg: dict) -> None:
    st.markdown("### Clarify Prospect Identity")
    candidates = payload.get("candidates", [])
    name = state.get("prospect_name", "this person")

    if not candidates:
        st.info(f"Could not find multiple profiles for **{name}**. Continuing with original.")
        if st.button("Continue", type="primary"):
            with st.spinner("Continuing…"):
                try:
                    graph.invoke(Command(resume={}), config=cfg)
                except Exception as exc:
                    st.session_state.run_error = str(exc)
            st.rerun()
        return

    st.markdown(
        f"We found **{len(candidates)} different people** matching **{name}**. "
        "Please select the correct one:"
    )

    def _fmt(idx: int) -> str:
        c = candidates[idx]
        return f"{c.get('name', '?')} — {c.get('role', '?')} @ {c.get('company', '?')}"

    idx = st.radio(
        "Select person:",
        options=list(range(len(candidates))),
        format_func=_fmt,
    )

    for i, c in enumerate(candidates):
        if c.get("source_url"):
            st.caption(f"[{i}] Source: {c['source_url'][:80]}")

    if st.button("Select & Continue", type="primary"):
        with st.spinner("Continuing pipeline…"):
            try:
                graph.invoke(Command(resume=candidates[idx]), config=cfg)
            except Exception as exc:
                st.session_state.run_error = str(exc)
        st.rerun()


# ── Signal review interrupt ───────────────────────────────────────────────────

def _render_signal_review(payload: dict, state: dict, graph, cfg: dict) -> None:
    st.markdown("### Choose a Signal")
    st.caption(
        "These are the top signals discovered and scored. Select one to use as the "
        "outreach hook. Add optional instructions to steer the draft."
    )

    signals      = payload.get("signals") or state.get("signals", [])
    pre_selected = payload.get("pre_selected")
    flags        = payload.get("flags") or state.get("flags", [])

    if flags:
        badges = " ".join(flag_badge(f) for f in flags)
        st.markdown(f"**Active flags:** {badges}", unsafe_allow_html=True)
        st.markdown("")

    if not signals:
        st.warning("No signals found — pipeline will use company-level fallback.")
        if st.button("Continue with company-level outreach", type="primary"):
            graph.invoke(Command(resume={"signal_id": None, "instructions": ""}), config=cfg)
            st.rerun()
        return

    # Sort: sensitive last, then by score descending
    sorted_sigs = sorted(
        signals,
        key=lambda s: (s.get("is_sensitive", False), -(s.get("total_score") or 0)),
    )
    sig_ids = [s["id"] for s in sorted_sigs]
    pre_idx = sig_ids.index(pre_selected) if pre_selected in sig_ids else 0

    def _fmt(sid: str) -> str:
        s    = next((x for x in sorted_sigs if x["id"] == sid), {})
        sens = " [SENSITIVE]" if s.get("is_sensitive") else ""
        age  = s.get("age_days")
        age_s = f" · {age}d ago" if age is not None else ""
        score = s.get("total_score") or 0
        t    = s.get("type", "signal").replace("_", " ").title()
        desc = (s.get("description") or "")[:65]
        return f"{t}{sens}{age_s} · Score {score:.1f}  —  {desc}"

    selected_id = st.radio(
        "Select a signal:",
        options=sig_ids,
        format_func=_fmt,
        index=pre_idx,
    )

    # Detail card for the selected signal
    selected = next((s for s in sorted_sigs if s["id"] == selected_id), None)
    if selected:
        render_signal_card(selected)

    st.markdown("")
    instructions = st.text_input(
        "Optional instructions for the hook/draft",
        placeholder=(
            "e.g. 'Focus on operational challenges', 'More concise', "
            "'Use the hiring signal instead', 'Executive tone'"
        ),
    )

    if st.button("Select Signal & Generate Draft", type="primary", width='stretch'):
        with st.spinner("Generating hook and draft…"):
            try:
                graph.invoke(
                    Command(resume={"signal_id": selected_id, "instructions": instructions}),
                    config=cfg,
                )
            except Exception as exc:  # noqa: BLE001
                st.session_state.run_error = str(exc)
        st.rerun()


# ── Draft review interrupt ────────────────────────────────────────────────────

def _render_draft_review(payload: dict, state: dict, graph, cfg: dict) -> None:
    st.markdown("### Review & Edit Drafts")
    st.caption("Edit either draft inline. When happy, click Approve to continue.")

    hook   = payload.get("hook")   or state.get("hook", {})
    drafts = payload.get("drafts") or state.get("drafts", {})
    flags  = payload.get("flags")  or state.get("flags", [])

    if flags:
        badges = " ".join(flag_badge(f) for f in flags)
        st.markdown(f"**Flags in effect:** {badges}", unsafe_allow_html=True)
        st.markdown("")

    # Hook explainability box
    if hook:
        with st.expander("Hook — why this angle was chosen", expanded=True):
            st.markdown(f"**{hook.get('hook_text', '')}**")
            if hook.get("why_it_matters"):
                st.markdown(f"*{hook['why_it_matters']}*")
            if hook.get("why_chosen"):
                st.caption(f"Why chosen: {hook['why_chosen']}")
            rejected = hook.get("why_alternatives_rejected") or []
            if rejected:
                with st.expander("Why alternatives were rejected"):
                    for item in rejected:
                        st.caption(f"- {item}")

    email    = drafts.get("email", {})
    linkedin = drafts.get("linkedin", {})

    tab_email, tab_li = st.tabs(["Email", "LinkedIn"])

    with tab_email:
        new_subject = st.text_input("Subject line", value=email.get("subject", ""))
        new_body    = st.text_area("Body", value=email.get("body", ""), height=260)

    with tab_li:
        new_li = st.text_area(
            "LinkedIn message (400 chars max)",
            value=linkedin.get("body", ""),
            height=160,
            max_chars=400,
        )

    st.markdown("")
    col_approve, col_regen = st.columns([2, 2])

    with col_approve:
        if st.button("Approve Drafts & Continue", type="primary", width='stretch'):
            updated = {
                "email":    {"subject": new_subject, "body": new_body},
                "linkedin": {"body": new_li},
            }
            graph.invoke(
                Command(resume={"action": "approve", "updated_drafts": updated}),
                config=cfg,
            )
            st.rerun()

    with col_regen:
        regen_note = st.text_input(
            "Regenerate with different instructions",
            placeholder="e.g. 'More concise', 'Executive tone', 'Focus on cost savings'",
        )
        if st.button("Regenerate Draft", width='stretch'):
            if regen_note.strip():
                updated = {
                    "email":    {"subject": new_subject, "body": new_body},
                    "linkedin": {"body": new_li},
                }
                with st.spinner("Regenerating…"):
                    try:
                        graph.invoke(
                            Command(resume={
                                "action":         "edit",
                                "updated_drafts": updated,
                                "edits":          {"instructions": regen_note.strip()},
                            }),
                            config=cfg,
                        )
                    except Exception as exc:  # noqa: BLE001
                        st.session_state.run_error = str(exc)
                st.rerun()
            else:
                st.warning("Enter instructions before regenerating.")


# ── Approve interrupt ─────────────────────────────────────────────────────────

def _render_approve(payload: dict, state: dict, graph, cfg: dict) -> None:
    st.markdown("### Final Approval")
    st.caption("One last look before completing the run and saving to history.")

    drafts = payload.get("drafts") or state.get("drafts", {})
    hook   = payload.get("hook")   or state.get("hook", {})

    if hook.get("hook_text"):
        st.markdown(
            f'<div style="background:#f0fdf4;border-left:3px solid #16a34a;'
            f'padding:10px 14px;border-radius:4px;margin-bottom:12px;">'
            f'<b>Hook:</b> {hook["hook_text"]}</div>',
            unsafe_allow_html=True,
        )

    email    = drafts.get("email", {})
    linkedin = drafts.get("linkedin", {})

    tab_email, tab_li = st.tabs(["Email", "LinkedIn"])

    with tab_email:
        st.markdown(f"**Subject:** {email.get('subject', '')}")
        st.markdown("---")
        st.markdown(email.get("body", "").replace("\n", "\n\n"))

    with tab_li:
        st.markdown(linkedin.get("body", "").replace("\n", "\n\n"))

    st.markdown("")
    if st.button("Approve & Complete Run", type="primary", width='stretch'):
        with st.spinner("Finalising…"):
            try:
                graph.invoke(Command(resume={"action": "approve"}), config=cfg)
            except Exception as exc:  # noqa: BLE001
                st.session_state.run_error = str(exc)
        st.rerun()


# ── Completed view ────────────────────────────────────────────────────────────

def _render_completed(state: dict) -> None:
    st.success("Run completed and saved to history.")

    flags    = state.get("flags", [])
    drafts   = state.get("drafts", {})
    hook     = state.get("hook", {})
    signals  = state.get("signals", [])
    run_id   = state.get("run_id", "")
    freshness = state.get("signal_freshness", "—")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Signals found", len(signals))
    c2.metric("Freshness",     freshness)
    c3.metric("Flags",         len(flags))
    c4.metric("Run ID",        (run_id[:8] + "…") if run_id else "—")

    if flags:
        badges = " ".join(flag_badge(f) for f in flags)
        st.markdown(f"**Flags:** {badges}", unsafe_allow_html=True)

    st.markdown("")

    # Hook summary
    if hook.get("hook_text"):
        with st.expander("Hook used", expanded=False):
            st.markdown(f"**{hook['hook_text']}**")
            if hook.get("why_it_matters"):
                st.caption(hook["why_it_matters"])

    # Approved drafts
    st.markdown("### Approved Drafts")
    email    = drafts.get("email", {})
    linkedin = drafts.get("linkedin", {})

    tab_email, tab_li = st.tabs(["Email", "LinkedIn"])

    with tab_email:
        if email.get("subject"):
            st.markdown(f"**Subject:** {email['subject']}")
            st.markdown("---")
        st.text_area(
            "Email body",
            value=email.get("body", ""),
            height=280,
            disabled=True,
            label_visibility="collapsed",
        )

    with tab_li:
        st.text_area(
            "LinkedIn",
            value=linkedin.get("body", ""),
            height=160,
            disabled=True,
            label_visibility="collapsed",
        )

    # Top signals summary
    if signals:
        with st.expander(f"Signals ({len(signals)} found)", expanded=False):
            top = sorted(signals, key=lambda s: -(s.get("total_score") or 0))[:5]
            for sig in top:
                render_signal_card(sig)
