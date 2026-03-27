import os
import streamlit as st
import httpx
import plotly.express as px
import pandas as pd

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

st.set_page_config(page_title="Analytics — Law Firm AI", page_icon="📊", layout="wide")

# Auth guard
if not st.session_state.get("token"):
    st.warning("Please sign in first.")
    st.stop()

headers = {"Authorization": f"Bearer {st.session_state.token}"}


# ── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(f"**{st.session_state.get('full_name') or st.session_state.get('email', '')}**")
    st.caption(f"Role: {st.session_state.get('role', '')}")
    st.divider()
    if st.button("🚪 Sign Out", use_container_width=True):
        for key in ("token", "role", "email", "full_name"):
            st.session_state[key] = None
        st.rerun()


# ── Main ─────────────────────────────────────────────────────────────────────
st.title("📊 Usage Analytics")
st.caption("Last 30 days — refreshes on page load")

if st.button("🔄 Refresh"):
    st.rerun()

try:
    resp = httpx.get(f"{BACKEND_URL}/analytics/stats", headers=headers, timeout=15)
    if resp.status_code != 200:
        st.error("Failed to load analytics data.")
        st.stop()
    data = resp.json()
except Exception as exc:
    st.error(f"Connection error: {exc}")
    st.stop()

# ── KPI Cards ─────────────────────────────────────────────────────────────────
col1, col2, col3, col4, col5 = st.columns(5)
totals = data.get("totals", {})
rt = data.get("response_time", {})

with col1:
    st.metric("📄 Total Documents", totals.get("documents", 0))
with col2:
    st.metric("❓ Total Queries", totals.get("queries", 0))
with col3:
    st.metric("🗂️ Total Matters", totals.get("matters", 0))
with col4:
    st.metric("⚡ P50 Response", f"{rt.get('p50_ms', 0)}ms")
with col5:
    st.metric("🐢 P95 Response", f"{rt.get('p95_ms', 0)}ms")

st.divider()

# ── Charts Row 1 ──────────────────────────────────────────────────────────────
col_left, col_right = st.columns(2)

with col_left:
    st.subheader("Queries Per Day")
    qpd = data.get("queries_by_day", [])
    if qpd:
        df = pd.DataFrame(qpd)
        df["date"] = pd.to_datetime(df["date"])
        fig = px.line(df, x="date", y="count", markers=True, labels={"count": "Queries", "date": "Date"})
        fig.update_layout(margin=dict(l=0, r=0, t=10, b=0))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No query data yet.")

with col_right:
    st.subheader("Documents by Status")
    doc_status = data.get("doc_status", [])
    if doc_status:
        df = pd.DataFrame(doc_status)
        color_map = {"ready": "#2ecc71", "processing": "#f39c12", "failed": "#e74c3c"}
        fig = px.pie(
            df, names="status", values="count",
            color="status", color_discrete_map=color_map,
            hole=0.4,
        )
        fig.update_layout(margin=dict(l=0, r=0, t=10, b=0))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No documents uploaded yet.")

# ── Charts Row 2 ──────────────────────────────────────────────────────────────
col_left2, col_right2 = st.columns(2)

with col_left2:
    st.subheader("Top Queried Documents")
    top_docs = data.get("top_docs", [])
    if top_docs:
        df = pd.DataFrame(top_docs)
        fig = px.bar(
            df, x="query_count", y="filename", orientation="h",
            labels={"query_count": "Queries", "filename": "Document"},
        )
        fig.update_layout(margin=dict(l=0, r=0, t=10, b=0), yaxis={"categoryorder": "total ascending"})
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No query data yet.")

with col_right2:
    st.subheader("Most Active Matters")
    top_matters = data.get("top_matters", [])
    if top_matters:
        df = pd.DataFrame(top_matters)
        df["label"] = df["matter_number"] + " — " + df["matter_name"]
        fig = px.bar(
            df, x="query_count", y="label", orientation="h",
            labels={"query_count": "Queries", "label": "Matter"},
        )
        fig.update_layout(margin=dict(l=0, r=0, t=10, b=0), yaxis={"categoryorder": "total ascending"})
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No matter query data yet.")
