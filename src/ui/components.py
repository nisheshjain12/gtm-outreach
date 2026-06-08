"""Reusable UI components (architecture.md §2, Phase 5)."""
from __future__ import annotations

from pathlib import Path

import streamlit as st

# ── Badge configs ────────────────────────────────────────────────────────────

_FLAG_META: dict[str, tuple[str, str, str]] = {
    "funding_round":     ("High intent window",  "#16a34a", "#dcfce7"),
    "new_role":          ("New role",            "#2563eb", "#dbeafe"),
    "account_collision": ("Account collision",   "#7c3aed", "#ede9fe"),
    "sensitive_news":    ("Sensitive context",   "#dc2626", "#fee2e2"),
    "stale_signals":     ("Stale signals",       "#d97706", "#fef3c7"),
    "no_signal":         ("No signal",           "#6b7280", "#f3f4f6"),
    "ambiguous_name":    ("Ambiguous name",      "#b45309", "#fef3c7"),
}

_FRESHNESS_META: dict[str, tuple[str, str, str]] = {
    "fresh":      ("Fresh",      "#16a34a", "#dcfce7"),
    "stale":      ("Stale",      "#d97706", "#fef3c7"),
    "very_stale": ("Very stale", "#dc2626", "#fee2e2"),
}

_STATUS_META: dict[str, tuple[str, str]] = {
    "completed":   ("#16a34a", "#dcfce7"),
    "approved":    ("#16a34a", "#dcfce7"),
    "researching": ("#2563eb", "#dbeafe"),
    "running":     ("#2563eb", "#dbeafe"),
    "failed":      ("#dc2626", "#fee2e2"),
    "error":       ("#dc2626", "#fee2e2"),
}


# ── CSS injection ────────────────────────────────────────────────────────────

def inject_css() -> None:
    css_path = Path(__file__).parent / "styles.css"
    st.markdown(f"<style>{css_path.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)


# ── Badge helpers ────────────────────────────────────────────────────────────

def _badge(label: str, color: str, bg: str) -> str:
    return (
        f'<span style="background:{bg};color:{color};padding:2px 10px;'
        f'border-radius:999px;font-size:12px;font-weight:600;margin-right:4px;">'
        f'{label}</span>'
    )


def flag_badge(flag: str) -> str:
    label, color, bg = _FLAG_META.get(flag, (flag.replace("_", " ").title(), "#6b7280", "#f3f4f6"))
    return _badge(label, color, bg)


def freshness_badge(freshness: str) -> str:
    label, color, bg = _FRESHNESS_META.get(freshness, (freshness, "#6b7280", "#f3f4f6"))
    return _badge(label, color, bg)


def status_badge(status: str) -> str:
    color, bg = _STATUS_META.get(status, ("#6b7280", "#f3f4f6"))
    return _badge(status.replace("_", " ").title(), color, bg)


# ── Signal card ──────────────────────────────────────────────────────────────

def render_signal_card(sig: dict) -> None:
    """Render a full-detail signal card (scores + source + freshness)."""
    scores     = sig.get("scores") or {}
    total      = sig.get("total_score") or 0
    age        = sig.get("age_days")
    sensitive  = sig.get("is_sensitive", False)
    type_label = sig.get("type", "signal").replace("_", " ").title()
    desc       = sig.get("description", "")
    url        = sig.get("source_url", "")
    title_src  = sig.get("source_title") or (url[:60] if url else "")

    border = "#dc2626" if sensitive else "#4f46e5"
    bg     = "#fff5f5" if sensitive else "#f8faff"
    sens_tag = (
        '&nbsp;<span style="color:#dc2626;font-size:11px;font-weight:700;">SENSITIVE</span>'
        if sensitive else ""
    )
    src_link = (
        f'<br><a href="{url}" target="_blank" style="font-size:11px;color:#6366f1;">'
        f'{title_src}</a>'
        if url else ""
    )

    hook_sentence = sig.get("hook_sentence") or ""
    hook_html = (
        f'<br><span style="color:#4f46e5;font-size:13px;font-style:italic;">'
        f'&#8220;{hook_sentence}&#8221;</span>'
        if hook_sentence else ""
    )

    st.markdown(
        f'<div style="border-left:3px solid {border};background:{bg};'
        f'padding:12px 16px;border-radius:4px;margin:6px 0;">'
        f'<b>{type_label}</b>{sens_tag}'
        f'<br><span style="color:#374151;font-size:14px;">{desc}</span>'
        f'{hook_html}'
        f'{src_link}</div>',
        unsafe_allow_html=True,
    )

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Score",        f"{total:.1f}")
    c2.metric("Recency",      scores.get("recency", "-"))
    c3.metric("Specificity",  scores.get("specificity", "-"))
    c4.metric("Actionability", scores.get("actionability", "-"))
    c5.metric("Confidence",   scores.get("confidence", "-"))

    if age is not None:
        freshness = "fresh" if age <= 90 else ("stale" if age <= 180 else "very_stale")
        st.markdown(
            freshness_badge(freshness) + f"&nbsp;&nbsp;{age} days ago",
            unsafe_allow_html=True,
        )

    if sig.get("reasoning"):
        st.caption(f"Reasoning: {sig['reasoning']}")
