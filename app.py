"""GTM Personalized Outreach Engine — Streamlit entry point.

Run:  streamlit run app.py
"""
import streamlit as st

from src import config
from src.graph.build import build_graph
from src.ui import dashboard, live_run, settings

st.set_page_config(
    page_title="GTM Outreach Engine",
    page_icon="mail",
    layout="wide",
)

# ── Sidebar ──────────────────────────────────────────────────────────────────

missing = config.missing_keys()
if missing:
    st.sidebar.warning("Missing API keys: " + ", ".join(missing))
else:
    st.sidebar.success("All API keys loaded")

st.sidebar.markdown("---")
page = st.sidebar.radio("Navigate", ["Live Run", "Dashboard", "Settings"])
st.sidebar.markdown("---")
st.sidebar.caption(f"Thread: `{st.session_state.get('thread_id', 'none')[:8]}`")


# ── Graph (cached — checkpointer survives Streamlit reruns) ──────────────────

@st.cache_resource
def get_graph():
    return build_graph()


graph = get_graph()

# ── Routing ──────────────────────────────────────────────────────────────────

st.title("GTM Outreach Engine")

if page == "Live Run":
    live_run.render(graph)

elif page == "Dashboard":
    dashboard.render()

else:
    settings.render()
