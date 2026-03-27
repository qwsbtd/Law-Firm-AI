import os
import streamlit as st
import httpx

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

st.set_page_config(page_title="Documents — Law Firm AI", page_icon="📁", layout="wide")

# Auth guard
if not st.session_state.get("token"):
    st.warning("Please sign in first.")
    st.stop()

headers = {"Authorization": f"Bearer {st.session_state.token}"}
is_admin = st.session_state.get("role") == "admin"


# ── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(f"**{st.session_state.get('full_name') or st.session_state.get('email', '')}**")
    st.caption(f"Role: {st.session_state.get('role', '')}")
    st.divider()

    with st.expander("💡 Tips for Best Results"):
        st.markdown(
            """
- **Select a matter first** before uploading — all documents must belong to a case
- Upload the **most recent version** of a document; ask an admin to remove older ones
- Supported formats: **PDF, DOCX, TXT** (up to 500 MB)
- After upload, wait for **Ready** status before chatting
- Be specific in questions: *"What are the payment terms?"* beats *"tell me about money"*
- AI answers are a **starting point** — always verify against the source document
- For long contracts, request a **summary first**, then drill into specific clauses
"""
        )

    st.divider()
    if st.button("🚪 Sign Out", use_container_width=True):
        for key in ("token", "role", "email", "full_name"):
            st.session_state[key] = None
        st.rerun()


# ── Main ─────────────────────────────────────────────────────────────────────
st.title("📁 Document Management")

# Load matters
try:
    matters_resp = httpx.get(f"{BACKEND_URL}/matters/", headers=headers, timeout=10)
    matters = matters_resp.json() if matters_resp.status_code == 200 else []
except Exception:
    matters = []

if not matters:
    st.warning(
        "No matters found. An attorney or admin must create a matter before uploading documents."
    )
    if is_admin or st.session_state.get("role") == "attorney":
        st.info("Go to the **Admin** page to create a matter.")
    st.stop()

matter_options = {f"{m['matter_number']} — {m['matter_name']}": m for m in matters}
selected_label = st.selectbox("Select Matter", list(matter_options.keys()))
selected_matter = matter_options[selected_label]
selected_matter_id = selected_matter["id"]

st.divider()

# ── Upload Section ───────────────────────────────────────────────────────────
st.subheader("📤 Upload Documents")
uploaded_files = st.file_uploader(
    "Drag & drop files here",
    type=["pdf", "docx", "txt"],
    accept_multiple_files=True,
    help="Supported: PDF, DOCX, TXT — Max 500 MB per file",
)

if uploaded_files:
    if st.button(f"Upload {len(uploaded_files)} file(s) to **{selected_label}**", type="primary"):
        for uf in uploaded_files:
            with st.spinner(f"Uploading {uf.name}…"):
                try:
                    resp = httpx.post(
                        f"{BACKEND_URL}/documents/upload",
                        headers=headers,
                        files={"file": (uf.name, uf.getvalue(), uf.type or "application/octet-stream")},
                        data={"matter_id": str(selected_matter_id)},
                        timeout=120,
                    )
                    if resp.status_code == 200:
                        st.success(f"✅ {uf.name} uploaded — processing in background")
                    else:
                        st.error(f"❌ {uf.name}: {resp.json().get('detail', 'Upload failed')}")
                except Exception as exc:
                    st.error(f"❌ {uf.name}: {exc}")
        st.rerun()

st.divider()

# ── Document List ─────────────────────────────────────────────────────────────
st.subheader(f"📋 Documents in {selected_label}")

col_refresh, _ = st.columns([1, 5])
with col_refresh:
    if st.button("🔄 Refresh"):
        st.rerun()

try:
    docs_resp = httpx.get(
        f"{BACKEND_URL}/documents/",
        headers=headers,
        params={"matter_id": selected_matter_id},
        timeout=10,
    )
    docs = docs_resp.json() if docs_resp.status_code == 200 else []
except Exception:
    docs = []

if not docs:
    st.info("No documents uploaded for this matter yet.")
else:
    for doc in docs:
        status = doc["status"]
        status_badge = {"processing": "🟡 Processing", "ready": "🟢 Ready", "failed": "🔴 Failed"}.get(
            status, status
        )
        size_mb = round(doc["file_size"] / (1024 * 1024), 2) if doc["file_size"] else 0

        with st.container(border=True):
            col1, col2, col3, col4 = st.columns([4, 2, 2, 2])
            with col1:
                st.markdown(f"**{doc['original_filename']}**")
                st.caption(
                    f"{size_mb} MB · {doc['page_count']} pages · {doc['chunk_count']} chunks"
                )
            with col2:
                st.markdown(status_badge)
                if doc.get("upload_time"):
                    st.caption(doc["upload_time"][:10])
            with col3:
                if status == "ready":
                    if st.button("📝 Summarize", key=f"sum_{doc['id']}"):
                        with st.spinner("Generating summary…"):
                            try:
                                sr = httpx.post(
                                    f"{BACKEND_URL}/chat/summarize/{doc['id']}",
                                    headers=headers,
                                    timeout=120,
                                )
                                if sr.status_code == 200:
                                    st.session_state[f"summary_{doc['id']}"] = sr.json()["summary"]
                                else:
                                    st.error("Summary failed")
                            except Exception as exc:
                                st.error(str(exc))
            with col4:
                if is_admin:
                    confirm_key = f"confirm_delete_{doc['id']}"
                    if not st.session_state.get(confirm_key):
                        if st.button("🗑️ Delete", key=f"del_{doc['id']}"):
                            st.session_state[confirm_key] = True
                            st.rerun()
                    else:
                        st.warning("Are you sure?")
                        if st.button("✅ Confirm", key=f"conf_{doc['id']}"):
                            try:
                                dr = httpx.delete(
                                    f"{BACKEND_URL}/documents/{doc['id']}",
                                    headers=headers,
                                    timeout=30,
                                )
                                if dr.status_code == 200:
                                    st.success("Deleted")
                                    st.session_state.pop(confirm_key, None)
                                    st.rerun()
                                else:
                                    st.error(dr.json().get("detail", "Delete failed"))
                            except Exception as exc:
                                st.error(str(exc))
                        if st.button("❌ Cancel", key=f"cancel_{doc['id']}"):
                            st.session_state.pop(confirm_key, None)
                            st.rerun()

            # Error message
            if status == "failed" and doc.get("error_message"):
                st.error(f"Error: {doc['error_message']}")

            # Summary expander
            summary_text = st.session_state.get(f"summary_{doc['id']}")
            if not summary_text and doc.get("summary_preview"):
                summary_text = None  # Show summary button only
            if summary_text:
                with st.expander("📝 Summary"):
                    st.markdown(summary_text)
