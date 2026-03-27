import os
import streamlit as st
import httpx
import pandas as pd

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

st.set_page_config(page_title="Admin — Law Firm AI", page_icon="⚙️", layout="wide")

# Auth guard
if not st.session_state.get("token"):
    st.warning("Please sign in first.")
    st.stop()

# Admin-only
if st.session_state.get("role") != "admin":
    st.error("🚫 Admin access required.")
    st.stop()

headers = {"Authorization": f"Bearer {st.session_state.token}"}


# ── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(f"**{st.session_state.get('full_name') or st.session_state.get('email', '')}**")
    st.caption("Role: admin")
    st.divider()
    if st.button("🚪 Sign Out", use_container_width=True):
        for key in ("token", "role", "email", "full_name"):
            st.session_state[key] = None
        st.rerun()


# ── Main ─────────────────────────────────────────────────────────────────────
st.title("⚙️ Admin Panel")

tab_matters, tab_users, tab_audit = st.tabs(["🗂️ Matters", "👥 Users", "📋 Audit Log"])


# ── Matters Tab ───────────────────────────────────────────────────────────────
with tab_matters:
    st.subheader("Create New Matter")
    with st.form("create_matter"):
        col1, col2, col3 = st.columns(3)
        with col1:
            matter_number = st.text_input("Matter Number *", placeholder="2024-001")
        with col2:
            matter_name = st.text_input("Matter Name *", placeholder="Smith v. Jones")
        with col3:
            client_name = st.text_input("Client Name", placeholder="John Smith")
        submitted = st.form_submit_button("Create Matter", type="primary")

    if submitted:
        if not matter_number or not matter_name:
            st.error("Matter number and name are required.")
        else:
            try:
                resp = httpx.post(
                    f"{BACKEND_URL}/matters/",
                    headers=headers,
                    json={"matter_number": matter_number, "matter_name": matter_name, "client_name": client_name},
                    timeout=10,
                )
                if resp.status_code == 200:
                    st.success(f"✅ Matter '{matter_number}' created")
                    st.rerun()
                else:
                    st.error(resp.json().get("detail", "Failed to create matter"))
            except Exception as exc:
                st.error(str(exc))

    st.divider()
    st.subheader("All Matters")

    try:
        resp = httpx.get(f"{BACKEND_URL}/matters/", headers=headers, timeout=10)
        matters = resp.json() if resp.status_code == 200 else []
    except Exception:
        matters = []

    if matters:
        for m in matters:
            status_icon = "🟢" if m["status"] == "open" else "🔴"
            with st.container(border=True):
                col1, col2, col3, col4 = st.columns([3, 2, 1, 2])
                with col1:
                    st.markdown(f"**{m['matter_number']}** — {m['matter_name']}")
                    if m.get("client_name"):
                        st.caption(f"Client: {m['client_name']}")
                with col2:
                    st.markdown(f"{status_icon} {m['status'].capitalize()}")
                    st.caption(f"{m['doc_count']} documents")
                with col3:
                    # Toggle open/closed
                    new_status = "closed" if m["status"] == "open" else "open"
                    if st.button(
                        f"Mark {new_status.capitalize()}",
                        key=f"toggle_{m['id']}",
                    ):
                        httpx.put(
                            f"{BACKEND_URL}/matters/{m['id']}",
                            headers=headers,
                            json={"status": new_status},
                            timeout=10,
                        )
                        st.rerun()
                with col4:
                    confirm_key = f"confirm_del_matter_{m['id']}"
                    if not st.session_state.get(confirm_key):
                        if st.button("🗑️ Delete Matter", key=f"del_matter_{m['id']}"):
                            st.session_state[confirm_key] = True
                            st.rerun()
                    else:
                        st.warning(f"Delete all {m['doc_count']} docs?")
                        col_y, col_n = st.columns(2)
                        with col_y:
                            if st.button("✅ Yes", key=f"yes_{m['id']}"):
                                httpx.delete(
                                    f"{BACKEND_URL}/matters/{m['id']}",
                                    headers=headers,
                                    timeout=30,
                                )
                                st.session_state.pop(confirm_key, None)
                                st.rerun()
                        with col_n:
                            if st.button("❌ No", key=f"no_{m['id']}"):
                                st.session_state.pop(confirm_key, None)
                                st.rerun()
    else:
        st.info("No matters yet.")


# ── Users Tab ─────────────────────────────────────────────────────────────────
with tab_users:
    st.subheader("Create New User")
    with st.form("create_user"):
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            new_email = st.text_input("Email *")
        with col2:
            new_name = st.text_input("Full Name")
        with col3:
            new_password = st.text_input("Password *", type="password")
        with col4:
            new_role = st.selectbox("Role", ["paralegal", "attorney", "admin"])
        submitted_user = st.form_submit_button("Create User", type="primary")

    if submitted_user:
        if not new_email or not new_password:
            st.error("Email and password are required.")
        else:
            try:
                resp = httpx.post(
                    f"{BACKEND_URL}/auth/register",
                    headers=headers,
                    json={"email": new_email, "full_name": new_name, "password": new_password, "role": new_role},
                    timeout=10,
                )
                if resp.status_code == 200:
                    st.success(f"✅ User {new_email} created as {new_role}")
                    st.rerun()
                else:
                    st.error(resp.json().get("detail", "Failed to create user"))
            except Exception as exc:
                st.error(str(exc))

    st.divider()
    st.subheader("All Users")

    try:
        resp = httpx.get(f"{BACKEND_URL}/auth/users", headers=headers, timeout=10)
        users = resp.json() if resp.status_code == 200 else []
    except Exception:
        users = []

    if users:
        df = pd.DataFrame(users)[["email", "full_name", "role", "is_active", "created_at"]]
        df["created_at"] = pd.to_datetime(df["created_at"]).dt.strftime("%Y-%m-%d")
        df.columns = ["Email", "Full Name", "Role", "Active", "Created"]
        st.dataframe(df, use_container_width=True, hide_index=True)

        st.divider()
        st.subheader("Activate / Deactivate User")
        user_emails = [u["email"] for u in users if u["email"] != st.session_state.get("email")]
        if user_emails:
            target_email = st.selectbox("Select user", user_emails)
            target_user = next((u for u in users if u["email"] == target_email), None)
            if target_user:
                action_label = "Deactivate" if target_user["is_active"] else "Activate"
                if st.button(f"{action_label} {target_email}"):
                    try:
                        httpx.patch(
                            f"{BACKEND_URL}/auth/users/{target_user['id']}/deactivate",
                            headers=headers,
                            timeout=10,
                        )
                        st.rerun()
                    except Exception as exc:
                        st.error(str(exc))
    else:
        st.info("No users found.")


# ── Audit Log Tab ─────────────────────────────────────────────────────────────
with tab_audit:
    st.subheader("Audit Log")

    col1, col2 = st.columns([1, 5])
    with col1:
        page = st.number_input("Page", min_value=1, value=1, step=1)

    try:
        resp = httpx.get(
            f"{BACKEND_URL}/analytics/audit-log",
            headers=headers,
            params={"page": page, "limit": 50},
            timeout=10,
        )
        if resp.status_code == 200:
            result = resp.json()
            logs = result.get("logs", [])
            total = result.get("total", 0)
            st.caption(f"Showing page {page} of {(total // 50) + 1} ({total} total entries)")
            if logs:
                df = pd.DataFrame(logs)[
                    ["timestamp", "user_email", "action", "resource_type", "detail", "ip_address", "success"]
                ]
                df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.strftime("%Y-%m-%d %H:%M:%S")
                df.columns = ["Timestamp", "User", "Action", "Resource", "Detail", "IP", "Success"]
                st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                st.info("No audit log entries yet.")
        else:
            st.error("Failed to load audit log.")
    except Exception as exc:
        st.error(f"Connection error: {exc}")
