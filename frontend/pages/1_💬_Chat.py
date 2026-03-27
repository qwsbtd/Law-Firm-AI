import os
import streamlit as st
import httpx

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

st.set_page_config(page_title="Chat — Law Firm AI", page_icon="💬", layout="wide")

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

    # Matter selector
    st.subheader("🗂️ Scope by Matter")
    try:
        matters_resp = httpx.get(f"{BACKEND_URL}/matters/", headers=headers, timeout=10)
        matters = matters_resp.json() if matters_resp.status_code == 200 else []
    except Exception:
        matters = []

    matter_options = {"All Matters": None}
    for m in matters:
        label = f"{m['matter_number']} — {m['matter_name']}"
        matter_options[label] = m["id"]

    selected_matter_label = st.selectbox(
        "Filter by matter", list(matter_options.keys()), index=0
    )
    selected_matter_id = matter_options[selected_matter_label]

    st.divider()

    # Tips
    with st.expander("💡 How to Ask Good Questions"):
        st.markdown(
            """
- **Select a matter** above to focus answers on a specific case
- Ask about **specific clauses, dates, parties, or obligations**
- Try: *"Summarize the key risks in this contract"*
- Try: *"What deadlines are mentioned in the filing?"*
- Try: *"Who are the parties in the Smith agreement?"*
- **Always verify** AI answers against the original document
- AI responses are a starting point — not legal advice
"""
        )

    st.divider()
    if st.button("🚪 Sign Out", use_container_width=True):
        for key in ("token", "role", "email", "full_name"):
            st.session_state[key] = None
        st.rerun()


# ── Main ─────────────────────────────────────────────────────────────────────
st.title("💬 Chat with Your Documents")

if selected_matter_id:
    st.caption(f"Scoped to: **{selected_matter_label}**")
else:
    st.caption("Searching across **all matters**")

# Initialize message history per matter scope
history_key = f"messages_{selected_matter_id}"
if history_key not in st.session_state:
    st.session_state[history_key] = []

messages = st.session_state[history_key]

# Clear button
col1, col2 = st.columns([6, 1])
with col2:
    if st.button("🗑️ Clear", help="Clear conversation history"):
        st.session_state[history_key] = []
        st.rerun()

# Render conversation history
for msg in messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg["role"] == "assistant" and msg.get("sources"):
            with st.expander(f"📎 Sources ({len(msg['sources'])})"):
                for src in msg["sources"]:
                    score_str = f" — score: {src['score']}" if src.get("score") else ""
                    matter_str = f" [{src.get('matter_number', '')}]" if src.get("matter_number") else ""
                    st.markdown(f"**{src['filename']}**{matter_str}{score_str}")
                    if src.get("text_preview"):
                        st.caption(f"> {src['text_preview']}…")

# Chat input
if prompt := st.chat_input("Ask a question about your legal documents…"):
    messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Searching documents…"):
            try:
                resp = httpx.post(
                    f"{BACKEND_URL}/chat/query",
                    headers=headers,
                    json={"question": prompt, "matter_id": selected_matter_id},
                    timeout=60,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    answer = data["answer"]
                    sources = data.get("sources", [])
                    response_ms = data.get("response_ms", 0)
                else:
                    answer = f"Error: {resp.json().get('detail', 'Request failed')}"
                    sources = []
                    response_ms = 0
            except Exception as exc:
                answer = f"Connection error: {exc}"
                sources = []
                response_ms = 0

        st.markdown(answer)
        if sources:
            with st.expander(f"📎 Sources ({len(sources)})"):
                for src in sources:
                    score_str = f" — score: {src['score']}" if src.get("score") else ""
                    matter_str = f" [{src.get('matter_number', '')}]" if src.get("matter_number") else ""
                    st.markdown(f"**{src['filename']}**{matter_str}{score_str}")
                    if src.get("text_preview"):
                        st.caption(f"> {src['text_preview']}…")
        if response_ms:
            st.caption(f"⏱ {response_ms}ms")

    messages.append(
        {"role": "assistant", "content": answer, "sources": sources}
    )
    st.session_state[history_key] = messages
