import streamlit as st

from src import config
from src.graph.build import build_graph
from src.ui import dashboard, live_run, settings
from src.ui.components import inject_css

st.set_page_config(
    page_title="GTM Outreach Engine",
    page_icon="✉️",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_css()  # load custom styles on every page

# ────── Sidebar ────── #

st.sidebar.markdown(
    '<div class="gtm-brand">'
    "<h2>GTM Outreach Engine</h2>"
    "<p>AI-powered B2B personalized outreach</p>"
    "</div>",
    unsafe_allow_html=True,
)

# Honour redirect requests from other pages (e.g. Dashboard Re-run button).
# Must run BEFORE the radio renders — widget keys can't be set after render.
if "nav_redirect" in st.session_state:
    st.session_state["nav_page"] = st.session_state.pop("nav_redirect")

page = st.sidebar.radio("Navigation", ["Live Run", "Dashboard", "Settings"],
                        label_visibility="collapsed", key="nav_page")
st.sidebar.markdown("---")

missing = config.missing_keys()
if missing:
    st.sidebar.warning("⚠ Missing keys: " + ", ".join(missing))
else:
    st.sidebar.success("✓ All systems ready")

st.sidebar.markdown("---")
st.sidebar.caption(f"Thread: `{st.session_state.get('thread_id', 'none')[:8]}`")


# ── Graph (cached — checkpointer survives Streamlit reruns) ──────────────────

@st.cache_resource
def get_graph():
    return build_graph()


graph = get_graph()

# ── Routing ──────────────────────────────────────────────────────────────────

if page == "Live Run":
    live_run.render(graph)
elif page == "Dashboard":
    dashboard.render()
else:
    settings.render()
