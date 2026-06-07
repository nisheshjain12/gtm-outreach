"""Settings — Seller Profile (D12, instruction_set.md §7.2).

Product/value-prop set once and auto-applied to every run.
"""
from __future__ import annotations

import streamlit as st

from src.db import supabase_client as db
from src.ui.components import inject_css

_TONES = ["consultative", "direct", "friendly", "executive"]


def render() -> None:
    inject_css()

    st.subheader("Seller Profile")
    st.caption(
        "Configure what you sell once here — it is automatically applied to every run. "
        "You can still override it per-run in the Live Run form."
    )

    profile = db.get_seller_profile() or {}

    with st.form("seller_profile_form"):
        product = st.text_area(
            "What you sell *",
            value=profile.get("product_description", ""),
            placeholder="e.g. AP automation software that cuts invoice processing time by 70%",
            height=120,
        )
        value_prop = st.text_area(
            "Value proposition",
            value=profile.get("value_prop", ""),
            placeholder="e.g. Helps AP teams eliminate ~10 hrs/week of manual invoice work",
            height=80,
        )
        default_tone = profile.get("default_tone", "consultative")
        tone_idx = _TONES.index(default_tone) if default_tone in _TONES else 0
        tone = st.selectbox("Default tone", _TONES, index=tone_idx)

        submitted = st.form_submit_button(
            "Save Seller Profile", type="primary", width='stretch'
        )

    if submitted:
        if not product.strip():
            st.error("Product description is required.")
        else:
            db.save_seller_profile({
                "product_description": product.strip(),
                "value_prop":          value_prop.strip(),
                "default_tone":        tone,
            })
            st.success("Seller Profile saved.")

    # Show current saved profile
    if profile.get("product_description"):
        st.markdown("---")
        st.caption("Currently saved profile:")
        st.markdown(f"**Product:** {profile['product_description']}")
        if profile.get("value_prop"):
            st.markdown(f"**Value prop:** {profile['value_prop']}")
        st.markdown(f"**Tone:** {profile.get('default_tone', '—')}")
