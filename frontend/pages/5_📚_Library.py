import os
import streamlit as st
import httpx

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

st.set_page_config(page_title="Law Library — Law Firm AI", page_icon="📚", layout="wide")

# Auth guard
if not st.session_state.get("token"):
    st.warning("Please sign in first.")
    st.stop()

headers = {"Authorization": f"Bearer {st.session_state.token}"}
is_admin = st.session_state.get("role") == "admin"

DOCUMENT_TYPES = ["case_file", "statute", "case_law", "template", "court_record"]
CATEGORIES = ["contract", "tort", "ip", "criminal", "family", "corporate", "real_estate", "other"]
JURISDICTIONS = ["federal", "state", "local"]

# CourtListener jurisdiction options (court IDs)
CL_JURISDICTIONS = {
    "All Courts": "all",
    "U.S. Supreme Court": "scotus",
    "1st Circuit": "ca1",
    "2nd Circuit": "ca2",
    "3rd Circuit": "ca3",
    "4th Circuit": "ca4",
    "5th Circuit": "ca5",
    "6th Circuit": "ca6",
    "7th Circuit": "ca7",
    "8th Circuit": "ca8",
    "9th Circuit": "ca9",
    "10th Circuit": "ca10",
    "11th Circuit": "ca11",
    "D.C. Circuit": "cadc",
    "Federal Circuit": "cafc",
}


# ── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(f"**{st.session_state.get('full_name') or st.session_state.get('email', '')}**")
    st.caption(f"Role: {st.session_state.get('role', '')}")
    st.divider()

    # CourtListener public records search
    st.subheader("🏛️ Public Court Records")
    st.caption("Search & import US court opinions via CourtListener")

    court_query = st.text_input(
        "Search public records",
        placeholder="e.g. breach of contract damages",
        key="cl_query",
    )
    cl_jur_label = st.selectbox("Court", list(CL_JURISDICTIONS.keys()), key="cl_jur")
    cl_jur_val = CL_JURISDICTIONS[cl_jur_label]

    if st.button("🔍 Search Public Records", use_container_width=True) and court_query.strip():
        with st.spinner("Searching CourtListener…"):
            try:
                resp = httpx.post(
                    f"{BACKEND_URL}/library/court-search",
                    headers=headers,
                    json={"query": court_query, "jurisdiction": cl_jur_val},
                    timeout=20,
                )
                if resp.status_code == 200:
                    st.session_state["court_results"] = resp.json().get("results", [])
                else:
                    st.error(resp.json().get("detail", "Search failed"))
                    st.session_state["court_results"] = []
            except Exception as exc:
                st.error(f"Connection error: {exc}")
                st.session_state["court_results"] = []

    court_results = st.session_state.get("court_results", [])
    if court_results:
        st.caption(f"{len(court_results)} result(s) — click Import to add to library")
        for idx, cr in enumerate(court_results):
            with st.container(border=True):
                st.markdown(f"**{cr['case_name']}**")
                if cr.get("citation"):
                    st.caption(f"📎 {cr['citation']}")
                meta = " · ".join(
                    p for p in [cr.get("court", ""), cr.get("date_filed", "")] if p
                )
                if meta:
                    st.caption(meta)
                if cr.get("snippet"):
                    st.caption(f"> {cr['snippet'][:150]}…")
                imp_key = f"import_{idx}_{cr['opinion_id']}"
                if st.button("⬇️ Import to Library", key=imp_key, use_container_width=True):
                    with st.spinner(f"Importing {cr['case_name'][:40]}…"):
                        try:
                            ir = httpx.post(
                                f"{BACKEND_URL}/library/court-import/{cr['opinion_id']}",
                                headers=headers,
                                timeout=60,
                            )
                            if ir.status_code == 200:
                                st.success("Imported — processing in background")
                            elif ir.status_code == 409:
                                st.info("Already in library")
                            else:
                                st.error(ir.json().get("detail", "Import failed"))
                        except Exception as exc:
                            st.error(str(exc))

    st.divider()

    with st.expander("💡 Library Tips"):
        st.markdown(
            """
- Upload **statutes, templates, and past case files** for firm-wide reference
- Search is **semantic** — not just keyword matching
- **Import** court opinions directly from CourtListener sidebar
- Library search is **separate** from active matter chat
- Admins can delete; all staff can upload and search
- Use the **Browse** tab to filter by type, category, or jurisdiction
"""
        )

    st.divider()
    if st.button("🚪 Sign Out", use_container_width=True):
        for key in ("token", "role", "email", "full_name"):
            st.session_state[key] = None
        st.rerun()


# ── Main ─────────────────────────────────────────────────────────────────────
st.title("📚 Law Library")
st.caption("Firm-wide legal reference repository — statutes, case law, templates, and past cases")

tab_search, tab_browse, tab_upload = st.tabs(["🔍 Search", "📋 Browse", "📤 Upload"])


# ── Tab 1: Search ─────────────────────────────────────────────────────────────
with tab_search:
    st.subheader("Semantic Legal Research")

    search_q = st.text_input(
        "Research question",
        placeholder="Ask a legal research question…",
        label_visibility="collapsed",
    )

    with st.expander("🔧 Filters (optional)"):
        fc1, fc2, fc3 = st.columns(3)
        with fc1:
            f_dtype = st.selectbox("Document Type", ["Any"] + DOCUMENT_TYPES, key="s_dtype")
        with fc2:
            f_cat = st.selectbox("Category", ["Any"] + CATEGORIES, key="s_cat")
        with fc3:
            f_jur = st.selectbox("Jurisdiction", ["Any"] + JURISDICTIONS, key="s_jur")

    if st.button("Search Library", type="primary") and search_q.strip():
        payload = {
            "question": search_q,
            "document_type": None if f_dtype == "Any" else f_dtype,
            "category":      None if f_cat  == "Any" else f_cat,
            "jurisdiction":  None if f_jur  == "Any" else f_jur,
        }
        with st.spinner("Searching library…"):
            try:
                resp = httpx.post(
                    f"{BACKEND_URL}/library/search",
                    headers=headers,
                    json=payload,
                    timeout=60,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    st.markdown("### Answer")
                    st.markdown(data["answer"])
                    sources = data.get("sources", [])
                    if sources:
                        with st.expander(f"📎 Sources ({len(sources)})"):
                            for src in sources:
                                label = src.get("citation") or src.get("title") or src.get("filename", "")
                                badge = src.get("document_type", "")
                                jur = src.get("jurisdiction", "")
                                score = src.get("score")
                                score_str = f" · score: {score}" if score else ""
                                st.markdown(f"**{label}** `{badge}` `{jur}`{score_str}")
                    st.caption(f"⏱ {data.get('response_ms', 0)}ms")
                else:
                    st.error(resp.json().get("detail", "Search failed"))
            except Exception as exc:
                st.error(f"Connection error: {exc}")


# ── Tab 2: Browse ─────────────────────────────────────────────────────────────
with tab_browse:
    st.subheader("Browse Library Documents")

    bc1, bc2, bc3, bc4 = st.columns(4)
    with bc1:
        b_dtype = st.selectbox("Type", ["All"] + DOCUMENT_TYPES, key="b_dtype")
    with bc2:
        b_cat = st.selectbox("Category", ["All"] + CATEGORIES, key="b_cat")
    with bc3:
        b_jur = st.selectbox("Jurisdiction", ["All"] + JURISDICTIONS, key="b_jur")
    with bc4:
        if st.button("🔄 Refresh", key="browse_refresh"):
            st.rerun()

    try:
        params = {}
        if b_dtype != "All": params["document_type"] = b_dtype
        if b_cat   != "All": params["category"]      = b_cat
        if b_jur   != "All": params["jurisdiction"]  = b_jur
        docs_resp = httpx.get(
            f"{BACKEND_URL}/library/",
            headers=headers,
            params=params,
            timeout=15,
        )
        lib_docs = docs_resp.json() if docs_resp.status_code == 200 else []
    except Exception:
        lib_docs = []

    if not lib_docs:
        st.info("No library documents match the selected filters.")
    else:
        st.caption(f"{len(lib_docs)} document(s)")
        for doc in lib_docs:
            status_badge = {
                "processing": "🟡 Processing",
                "ready":      "🟢 Ready",
                "failed":     "🔴 Failed",
            }.get(doc["status"], doc["status"])

            size_mb = round(doc["file_size"] / (1024 * 1024), 2) if doc["file_size"] else 0

            with st.container(border=True):
                c1, c2, c3, c4 = st.columns([4, 2, 2, 2])
                with c1:
                    st.markdown(f"**{doc['title']}**")
                    meta_parts = [
                        doc.get("document_type", ""),
                        doc.get("category", ""),
                        doc.get("jurisdiction", ""),
                        doc.get("jurisdiction_detail", ""),
                    ]
                    st.caption(" · ".join(p for p in meta_parts if p))
                    if doc.get("citation"):
                        st.caption(f"📎 {doc['citation']}")
                    if doc.get("court_name"):
                        st.caption(f"🏛️ {doc['court_name']}")
                with c2:
                    st.markdown(status_badge)
                    st.caption(f"{size_mb} MB · {doc.get('page_count', 0)} pages")
                    if doc.get("upload_time"):
                        st.caption(doc["upload_time"][:10])
                with c3:
                    if doc["status"] == "ready":
                        if st.button("📝 Summarize", key=f"libsum_{doc['id']}"):
                            with st.spinner("Generating summary…"):
                                try:
                                    sr = httpx.post(
                                        f"{BACKEND_URL}/library/{doc['id']}/summarize",
                                        headers=headers,
                                        timeout=120,
                                    )
                                    if sr.status_code == 200:
                                        st.session_state[f"libsummary_{doc['id']}"] = sr.json()["summary"]
                                    else:
                                        st.error("Summary failed")
                                except Exception as exc:
                                    st.error(str(exc))
                with c4:
                    if is_admin:
                        confirm_key = f"confirm_libdel_{doc['id']}"
                        if not st.session_state.get(confirm_key):
                            if st.button("🗑️ Delete", key=f"libdel_{doc['id']}"):
                                st.session_state[confirm_key] = True
                                st.rerun()
                        else:
                            st.warning("Are you sure?")
                            cy, cn = st.columns(2)
                            with cy:
                                if st.button("✅ Yes", key=f"libdelyes_{doc['id']}"):
                                    try:
                                        dr = httpx.delete(
                                            f"{BACKEND_URL}/library/{doc['id']}",
                                            headers=headers,
                                            timeout=30,
                                        )
                                        if dr.status_code == 200:
                                            st.session_state.pop(confirm_key, None)
                                            st.rerun()
                                        else:
                                            st.error(dr.json().get("detail", "Delete failed"))
                                    except Exception as exc:
                                        st.error(str(exc))
                            with cn:
                                if st.button("❌ No", key=f"libdelno_{doc['id']}"):
                                    st.session_state.pop(confirm_key, None)
                                    st.rerun()

                if doc["status"] == "failed" and doc.get("error_message"):
                    st.error(f"Error: {doc['error_message']}")

                summary_text = st.session_state.get(f"libsummary_{doc['id']}")
                if summary_text:
                    with st.expander("📝 Summary"):
                        st.markdown(summary_text)


# ── Tab 3: Upload ─────────────────────────────────────────────────────────────
with tab_upload:
    st.subheader("Upload to Law Library")
    st.caption("All staff can upload. Supported: PDF, DOCX, TXT — max 500 MB.")

    with st.form("library_upload_form"):
        title = st.text_input("Title *", placeholder="Smith v. Jones (2023)")
        uploaded_file = st.file_uploader("File *", type=["pdf", "docx", "txt"])

        col_a, col_b = st.columns(2)
        with col_a:
            doc_type = st.selectbox("Document Type *", DOCUMENT_TYPES)
            jurisdiction = st.selectbox("Jurisdiction *", JURISDICTIONS)
        with col_b:
            category = st.selectbox("Category *", CATEGORIES)
            jurisdiction_detail = st.text_input(
                "Jurisdiction Detail",
                placeholder="e.g. Texas, 9th Circuit, City of Austin",
            )

        citation = st.text_input(
            "Citation / Reference",
            placeholder="123 F.3d 456 (9th Cir. 1999)",
        )
        court_name = st.text_input(
            "Court Name",
            placeholder="U.S. Court of Appeals, 9th Circuit",
        )
        case_date = st.date_input("Case / Effective Date", value=None)
        notes = st.text_area("Notes", height=80, placeholder="Optional notes about this document…")

        submitted = st.form_submit_button("📤 Upload to Library", type="primary")

    if submitted:
        if not title.strip():
            st.error("Title is required.")
        elif not uploaded_file:
            st.error("Please select a file.")
        else:
            with st.spinner(f"Uploading {uploaded_file.name}…"):
                try:
                    form_data = {
                        "title":               title,
                        "document_type":       doc_type,
                        "category":            category,
                        "jurisdiction":        jurisdiction,
                        "jurisdiction_detail": jurisdiction_detail or "",
                        "citation":            citation or "",
                        "court_name":          court_name or "",
                        "case_date":           case_date.isoformat() if case_date else "",
                        "notes":               notes or "",
                    }
                    resp = httpx.post(
                        f"{BACKEND_URL}/library/upload",
                        headers=headers,
                        files={
                            "file": (
                                uploaded_file.name,
                                uploaded_file.getvalue(),
                                uploaded_file.type or "application/octet-stream",
                            )
                        },
                        data=form_data,
                        timeout=120,
                    )
                    if resp.status_code == 200:
                        st.success(
                            f"✅ '{title}' uploaded successfully — processing in background. "
                            "Check the Browse tab for status."
                        )
                    else:
                        st.error(resp.json().get("detail", "Upload failed"))
                except Exception as exc:
                    st.error(f"Connection error: {exc}")
