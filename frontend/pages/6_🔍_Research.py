import os
import streamlit as st
import httpx

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

st.set_page_config(page_title="AI Research — Law Firm AI", page_icon="🔍", layout="wide")

# Auth guard
if not st.session_state.get("token"):
    st.warning("Please sign in first.")
    st.stop()

headers = {"Authorization": f"Bearer {st.session_state.token}"}


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(f"**{st.session_state.get('full_name') or st.session_state.get('email', '')}**")
    st.caption(f"Role: {st.session_state.get('role', '')}")
    st.divider()

    with st.expander("💡 Research Tips"):
        st.markdown(
            """
- Ask **specific legal questions** for best results
- Searches **web** (SearXNG) + **AI knowledge** + **internal docs**
- SearXNG aggregates Google, Bing, Brave & Presearch privately
- Confidence **≥ 0.85** = high reliability answer
- Scores below threshold trigger **automatic retries**
- Each retry expands all three search sources
- Optionally **link a matter** to include its documents
- All queries are logged for compliance
"""
        )

    st.divider()
    if st.button("🚪 Sign Out", use_container_width=True):
        for key in ("token", "role", "email", "full_name"):
            st.session_state[key] = None
        st.rerun()


# ── Main ──────────────────────────────────────────────────────────────────────
st.title("🔍 AI Research Assistant")
st.caption(
    "Predictive analytics engine — automatically searches web + internal documents, "
    "scores confidence, and retries until the threshold is reached."
)

# Fetch matters for optional context
try:
    matters_resp = httpx.get(f"{BACKEND_URL}/matters/", headers=headers, timeout=10)
    matters = matters_resp.json() if matters_resp.status_code == 200 else []
except Exception:
    matters = []

# ── Input ─────────────────────────────────────────────────────────────────────
question = st.text_area(
    "Research Question",
    placeholder="e.g. What are the elements required to prove breach of fiduciary duty in Texas?",
    height=110,
    label_visibility="collapsed",
)

opt1, opt2, opt3 = st.columns([3, 2, 2])
with opt1:
    matter_options = {"No specific matter": None}
    for m in matters:
        matter_options[f"{m['matter_number']} — {m['matter_name']}"] = m["id"]
    selected_label = st.selectbox("Matter context (optional)", list(matter_options.keys()))
    selected_matter_id = matter_options[selected_label]

with opt2:
    confidence_threshold = st.slider(
        "Confidence threshold", min_value=0.50, max_value=1.00,
        value=0.85, step=0.05,
        help="Retries until this score is reached",
    )

with opt3:
    max_retries = st.selectbox("Max retries", [1, 2, 3, 4, 5], index=2)

run_btn = st.button("🔍 Research", type="primary", use_container_width=True)

# ── Execute ────────────────────────────────────────────────────────────────────
if run_btn:
    if not question.strip():
        st.warning("Please enter a research question.")
        st.stop()

    status_box = st.empty()
    status_box.info("🌐 Searching web and internal documents…")

    try:
        resp = httpx.post(
            f"{BACKEND_URL}/research/query",
            headers=headers,
            json={
                "question":             question,
                "matter_id":            selected_matter_id,
                "confidence_threshold": confidence_threshold,
                "max_retries":          max_retries,
            },
            timeout=180,
        )
        status_box.empty()

        if resp.status_code != 200:
            st.error(resp.json().get("detail", "Research failed"))
            st.stop()

        data = resp.json()

    except Exception as exc:
        status_box.empty()
        st.error(f"Connection error: {exc}")
        st.stop()

    # ── Metrics row ───────────────────────────────────────────────────────────
    confidence      = data.get("confidence", 0.0)
    threshold_met   = data.get("threshold_met", False)
    total_attempts  = data.get("total_attempts", 1)
    elapsed_ms      = data.get("response_ms", 0)
    attempt_history = data.get("attempt_history", [])

    if confidence >= 0.85:
        conf_icon, conf_label = "🟢", "High Confidence"
    elif confidence >= 0.70:
        conf_icon, conf_label = "🟡", "Moderate Confidence"
    else:
        conf_icon, conf_label = "🔴", "Low Confidence"

    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("Confidence Score", f"{conf_icon} {confidence:.3f}", help=conf_label)
    with m2:
        st.metric("Threshold Met", "✅ Yes" if threshold_met else f"⚠️ No (threshold {confidence_threshold})")
    with m3:
        st.metric("Attempts Made", f"{total_attempts} / {max_retries}")
    with m4:
        st.metric("Total Time", f"{elapsed_ms / 1000:.1f}s")

    # Confidence bar — color via CSS hack
    bar_color = "#28a745" if confidence >= 0.85 else ("#ffc107" if confidence >= 0.70 else "#dc3545")
    st.markdown(
        f"""
        <div style="background:#e9ecef;border-radius:4px;height:14px;margin-bottom:6px">
          <div style="background:{bar_color};width:{confidence*100:.1f}%;height:14px;border-radius:4px"></div>
        </div>
        <p style="font-size:0.78rem;color:#6c757d;margin:0">
          {conf_label} — {confidence*100:.1f}%
        </p>
        """,
        unsafe_allow_html=True,
    )

    if data.get("confidence_reasoning"):
        st.caption(f"**Confidence basis:** {data['confidence_reasoning']}")

    # ── Retry history ──────────────────────────────────────────────────────────
    if len(attempt_history) > 1:
        with st.expander(f"🔄 Retry History ({len(attempt_history)} attempts)"):
            for h in attempt_history:
                icon = "✅" if h["confidence"] >= confidence_threshold else "🔄"
                bar_w = int(h["confidence"] * 100)
                st.markdown(
                    f"{icon} **Attempt {h['attempt']}** — confidence `{h['confidence']:.3f}`"
                )

    st.divider()

    # ── Answer ─────────────────────────────────────────────────────────────────
    st.markdown("### Answer")
    st.markdown(data.get("answer", "No answer returned."))

    # ── Key Findings ───────────────────────────────────────────────────────────
    findings = data.get("key_findings", [])
    if findings:
        with st.expander(f"🎯 Key Findings ({len(findings)})"):
            for f in findings:
                st.markdown(f"- {f}")

    # ── Information Gaps ────────────────────────────────────────────────────────
    if data.get("gaps"):
        with st.expander("⚠️ Information Gaps / Caveats"):
            st.markdown(data["gaps"])

    # ── Sources ────────────────────────────────────────────────────────────────
    web_sources      = data.get("web_sources", [])
    hf_sources       = data.get("hf_sources", [])
    internal_sources = data.get("internal_sources", [])

    total_sources = len(web_sources) + len(hf_sources) + len(internal_sources)
    if total_sources:
        with st.expander(
            f"📎 Sources — {len(web_sources)} web · {len(hf_sources)} AI knowledge · {len(internal_sources)} internal"
        ):
            if internal_sources:
                st.markdown("**Internal Firm Documents**")
                for s in internal_sources:
                    icon   = "📚" if s.get("source") == "library" else "📁"
                    label  = s.get("citation") or s.get("title", "Document")
                    score  = f" · relevance {s['score']:.3f}" if s.get("score") else ""
                    matter = f" · {s['matter']}" if s.get("matter") else ""
                    st.markdown(f"{icon} **{label}**{matter}{score}")

            if hf_sources:
                if internal_sources:
                    st.divider()
                st.markdown("**AI Legal Knowledge**")
                for s in hf_sources:
                    model_name = s.get("model", "").split("/")[-1] or "AI"
                    icon = "🤗" if s.get("source") == "hf_model" else "🧠"
                    st.markdown(f"{icon} **{model_name}** — {s.get('title', 'AI-generated legal knowledge')}")
                    if s.get("snippet"):
                        st.caption(s["snippet"][:400] + ("…" if len(s["snippet"]) > 400 else ""))

            if web_sources:
                if internal_sources or hf_sources:
                    st.divider()
                st.markdown("**🔍 Live Web Search (SearXNG — private)**")
                for s in web_sources:
                    engines = f" · {s['engine']}" if s.get("engine") else ""
                    st.markdown(f"🌐 [{s['title']}]({s['url']}){engines}")
                    if s.get("snippet"):
                        st.caption(f"> {s['snippet'][:150]}…")
