"""Dashboard — Phase 6 (instruction_set.md §10).

History table with expandable per-run detail:
  Overview / Signals / Hook / Drafts / Actions tabs.
"""
from __future__ import annotations

import json
from datetime import datetime

import streamlit as st

from src.db import supabase_client as db
from src.ui.components import (
    flag_badge,
    freshness_badge,
    inject_css,
    render_signal_card,
    status_badge,
)

# ── Cached loaders ────────────────────────────────────────────────────────────

@st.cache_data(ttl=60)
def _load_runs() -> list[dict]:
    return db.list_runs(limit=200)


@st.cache_data(ttl=120)
def _load_run_detail(run_id: str) -> dict:
    return {
        "signals": db.get_signals(run_id),
        "hooks":   db.get_hooks(run_id),
        "drafts":  db.get_drafts(run_id),
        "actions": db.get_actions(run_id),
        "sources": db.get_sources(run_id),
    }


# ── Formatting helpers ────────────────────────────────────────────────────────

def _fmt_date(iso: str) -> str:
    if not iso:
        return "—"
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.strftime("%b %d %Y, %H:%M")
    except Exception:
        return iso[:16]


def _coerce_flags(raw) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except Exception:
            return [raw]
    return []


def _sig_for_card(sig: dict) -> dict:
    """Reshape flat DB signal row into render_signal_card expected format."""
    return {
        **sig,
        "scores": {
            "recency":       sig.get("recency"),
            "specificity":   sig.get("specificity"),
            "actionability": sig.get("actionability"),
            "confidence":    sig.get("confidence"),
        },
        "source_title": (sig.get("source_url") or "")[:60],
    }


# ── Summary metrics ───────────────────────────────────────────────────────────

def _render_summary_metrics(runs: list[dict]) -> None:
    total     = len(runs)
    completed = sum(1 for r in runs if r.get("status") == "completed")
    approved  = sum(1 for r in runs if r.get("approval_status") == "approved")
    flagged   = sum(1 for r in runs if _coerce_flags(r.get("flags")))

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Runs",   total)
    c2.metric("Completed",    completed)
    c3.metric("Approved",     approved)
    c4.metric("Flagged Runs", flagged)


# ── Filters ───────────────────────────────────────────────────────────────────

def _apply_filters(runs: list[dict]) -> list[dict]:
    c1, c2, c3 = st.columns([2, 2, 3])
    with c1:
        status_f = st.selectbox(
            "Status",
            ["All", "completed", "researching", "running", "error"],
            key="dash_status",
        )
    with c2:
        mode_f = st.selectbox(
            "Mode", ["All", "personalized", "account"],
            key="dash_mode",
        )
    with c3:
        search = st.text_input(
            "Search", placeholder="Prospect or company...",
            key="dash_search",
        )

    out = runs
    if status_f != "All":
        out = [r for r in out if r.get("status") == status_f]
    if mode_f != "All":
        out = [r for r in out if r.get("mode") == mode_f]
    if search:
        s = search.lower()
        out = [
            r for r in out
            if s in (r.get("prospect_name") or "").lower()
            or s in (r.get("company") or "").lower()
        ]
    return out


# ── Per-run detail tabs ───────────────────────────────────────────────────────

def _render_overview(run: dict) -> None:
    flags = _coerce_flags(run.get("flags"))

    cl, cr = st.columns(2)
    with cl:
        st.markdown(f"**Prospect:** {run.get('prospect_name') or '*(Account mode)*'}")
        st.markdown(f"**Company:** {run.get('company') or '—'}")
        st.markdown(f"**Mode:** {run.get('mode', '—').title()}")
        st.markdown(f"**Status:** {run.get('status', '—').title()}")
        st.markdown(f"**Approval:** {run.get('approval_status') or 'pending'}")
    with cr:
        st.markdown(f"**Goal:** {run.get('outreach_goal') or '—'}")
        st.markdown(f"**Signal freshness:** {run.get('signal_freshness') or '—'}")
        product = run.get("product_description") or ""
        if product:
            st.markdown(
                f"**Product:** {product[:140]}{'...' if len(product) > 140 else ''}"
            )
        if run.get("extra_context"):
            st.markdown(f"**Context:** {run['extra_context']}")
        st.caption(f"Created: {_fmt_date(run.get('created_at', ''))}")

    if flags:
        st.markdown("**Flags:**")
        st.markdown(" ".join(flag_badge(f) for f in flags), unsafe_allow_html=True)


def _render_signals_tab(signals: list[dict]) -> None:
    if not signals:
        st.info("No signals recorded for this run.")
        return

    sensitive_count = sum(1 for s in signals if s.get("is_sensitive"))
    st.caption(
        f"{len(signals)} signal{'s' if len(signals) != 1 else ''}  "
        f"·  {sensitive_count} sensitive  ·  sorted by score"
    )
    for sig in signals:
        render_signal_card(_sig_for_card(sig))
        st.markdown("---")


def _render_hook_tab(hooks: list[dict]) -> None:
    if not hooks:
        st.info("No hook recorded for this run.")
        return

    hook = hooks[0]
    st.markdown(
        f'<div style="background:#f0f9ff;border-left:4px solid #0ea5e9;'
        f'padding:14px 18px;border-radius:4px;font-size:15px;line-height:1.6;">'
        f'<b>Hook</b><br><br>{hook.get("hook_text", "—")}</div>',
        unsafe_allow_html=True,
    )
    st.markdown("")

    if hook.get("why_it_matters"):
        st.markdown(f"**Why it matters:** {hook['why_it_matters']}")
    if hook.get("why_chosen"):
        st.markdown(f"**Why chosen:** {hook['why_chosen']}")

    alts = hook.get("why_alternatives_rejected")
    if alts:
        if isinstance(alts, str):
            try:
                alts = json.loads(alts)
            except Exception:
                alts = [alts]
        with st.expander("Alternatives considered"):
            if isinstance(alts, list):
                for i, a in enumerate(alts, 1):
                    if isinstance(a, dict):
                        label = a.get("signal") or a.get("hook") or f"Option {i}"
                        reason = a.get("reason") or a.get("why_rejected") or ""
                        st.markdown(f"**{i}. {label}** — {reason}")
                    else:
                        st.markdown(f"- {a}")
            else:
                st.write(alts)


def _render_drafts_tab(drafts: list[dict]) -> None:
    if not drafts:
        st.info("No drafts recorded for this run.")
        return

    email    = next((d for d in drafts if d.get("channel") == "email"), None)
    linkedin = next((d for d in drafts if d.get("channel") == "linkedin"), None)

    tab_labels, tab_drafts = [], []
    if email:
        tab_labels.append("Email")
        tab_drafts.append(email)
    if linkedin:
        tab_labels.append("LinkedIn")
        tab_drafts.append(linkedin)

    if not tab_labels:
        st.info("No drafts recorded for this run.")
        return

    tabs = st.tabs(tab_labels)
    for tab, draft in zip(tabs, tab_drafts):
        with tab:
            approved_html = ""
            if draft.get("is_approved"):
                approved_html = (
                    '&nbsp;<span style="color:#16a34a;font-size:11px;'
                    'font-weight:700;">APPROVED</span>'
                )
            if draft.get("subject"):
                st.markdown(
                    f'**Subject:** {draft["subject"]}{approved_html}',
                    unsafe_allow_html=True,
                )
            st.markdown(
                f'<div style="background:#f9fafb;border:1px solid #e5e7eb;'
                f'padding:16px;border-radius:6px;white-space:pre-wrap;'
                f'font-size:14px;line-height:1.6;">'
                f'{draft.get("body", "")}</div>',
                unsafe_allow_html=True,
            )
            st.caption(
                f"Tone: {draft.get('tone') or '—'}  ·  "
                f"Version: {draft.get('version', 1)}  ·  "
                f"Channel: {draft.get('channel', '—')}"
            )


def _render_actions_tab(actions: list[dict]) -> None:
    if not actions:
        st.info("No human actions recorded for this run.")
        return

    for action in actions:
        payload = action.get("payload")
        payload_html = ""
        if payload:
            if isinstance(payload, str):
                try:
                    payload = json.loads(payload)
                except Exception:
                    pass
            if isinstance(payload, dict):
                parts = [
                    f"{k}={str(v)[:60]!r}"
                    for k, v in payload.items()
                    if v is not None
                ]
                payload_str = ", ".join(parts)[:200]
                if payload_str:
                    payload_html = (
                        f"<br><small style='color:#374151;'>{payload_str}</small>"
                    )
            elif payload:
                payload_html = (
                    f"<br><small style='color:#374151;'>{str(payload)[:200]}</small>"
                )

        st.markdown(
            f'<div style="border-left:3px solid #6366f1;padding:10px 16px;'
            f'margin:4px 0;background:#f5f3ff;border-radius:3px;">'
            f'<b>{action.get("stage", "—")}</b>'
            f' &rarr; <code style="background:#ede9fe;padding:1px 6px;border-radius:3px;">'
            f'{action.get("action", "—")}</code>'
            f'{payload_html}'
            f'<br><small style="color:#6b7280;">'
            f'{_fmt_date(action.get("created_at", ""))}</small>'
            f'</div>',
            unsafe_allow_html=True,
        )


# ── Run row ───────────────────────────────────────────────────────────────────

def _render_run_row(run: dict) -> None:
    run_id    = run.get("id", "")
    prospect  = run.get("prospect_name") or "(Account)"
    company   = run.get("company", "—")
    status    = run.get("status", "")
    approval  = run.get("approval_status") or ""
    flags     = _coerce_flags(run.get("flags"))
    freshness = run.get("signal_freshness") or ""
    mode      = run.get("mode", "")
    created   = _fmt_date(run.get("created_at", ""))

    flag_str = "  [" + ", ".join(flags) + "]" if flags else ""
    label    = f"{prospect}  @  {company}    {created}    {status.upper()}{flag_str}"

    with st.expander(label, expanded=False):
        # Badge strip
        badges = status_badge(status)
        if approval == "approved":
            badges += " " + status_badge("approved")
        if freshness:
            badges += " " + freshness_badge(freshness)
        if mode:
            mode_color = "#2563eb" if mode == "personalized" else "#7c3aed"
            badges += (
                f' <span style="background:#f0f0f0;color:{mode_color};'
                f'padding:2px 10px;border-radius:999px;font-size:12px;'
                f'font-weight:600;margin-right:4px;">{mode.title()}</span>'
            )
        for f in flags:
            badges += " " + flag_badge(f)
        st.markdown(badges, unsafe_allow_html=True)
        st.caption(
            f"Run ID: {run_id[:8]}...  ·  "
            f"Goal: {run.get('outreach_goal') or '—'}"
        )

        # Detail tabs — lazy-loaded inside expander keeps the list fast
        detail = _load_run_detail(run_id)

        t_ov, t_sig, t_hook, t_draft, t_act = st.tabs(
            ["Overview", "Signals", "Hook", "Drafts", "Actions"]
        )
        with t_ov:
            _render_overview(run)
        with t_sig:
            _render_signals_tab(detail["signals"])
        with t_hook:
            _render_hook_tab(detail["hooks"])
        with t_draft:
            _render_drafts_tab(detail["drafts"])
        with t_act:
            _render_actions_tab(detail["actions"])


# ── Entry point ───────────────────────────────────────────────────────────────

def render() -> None:
    inject_css()

    col_h, col_refresh, col_clean = st.columns([4, 1, 1])
    with col_h:
        st.subheader("Run History")
    with col_refresh:
        if st.button("Refresh", width='stretch', key="dash_refresh"):
            st.cache_data.clear()
            st.rerun()
    with col_clean:
        if st.button("Clean up", width='stretch', key="dash_cleanup",
                     help="Mark stuck 'Researching' runs (>15 min old) as Failed"):
            n = db.mark_stale_runs_failed()
            st.cache_data.clear()
            if n:
                st.success(f"Marked {n} stale run{'s' if n != 1 else ''} as Failed.")
            else:
                st.info("No stale runs found.")
            st.rerun()

    runs = _load_runs()
    if not runs:
        st.info("No runs yet. Start one in Live Run.")
        return

    _render_summary_metrics(runs)
    st.markdown("---")

    filtered = _apply_filters(runs)
    st.caption(
        f"Showing {len(filtered)} of {len(runs)} "
        f"run{'s' if len(runs) != 1 else ''} · newest first"
    )
    st.markdown("")

    if not filtered:
        st.info("No runs match the current filters.")
        return

    for run in filtered:
        _render_run_row(run)
