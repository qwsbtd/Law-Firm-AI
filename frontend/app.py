import os
import streamlit as st
import httpx

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

st.set_page_config(
    page_title="Law Firm AI",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Initialize session state
for key in ("token", "role", "email", "full_name"):
    if key not in st.session_state:
        st.session_state[key] = None


def show_login():
    st.title("⚖️ Law Firm AI Assistant")
    st.markdown("*Private • Secure • Compliant*")
    st.divider()

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("login_form"):
            st.subheader("Sign In")
            email = st.text_input("Email", placeholder="you@lawfirm.com")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Sign In", use_container_width=True)

        if submitted:
            if not email or not password:
                st.error("Please enter your email and password.")
            else:
                try:
                    resp = httpx.post(
                        f"{BACKEND_URL}/auth/login",
                        data={"username": email, "password": password},
                        timeout=15,
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        st.session_state.token = data["access_token"]
                        st.session_state.role = data["role"]
                        st.session_state.email = data["email"]
                        st.session_state.full_name = data.get("full_name", "")
                        st.rerun()
                    else:
                        detail = resp.json().get("detail", "Login failed")
                        st.error(f"❌ {detail}")
                except Exception as exc:
                    st.error(f"Could not connect to server: {exc}")


def show_app():
    # Sidebar user info + logout
    with st.sidebar:
        st.markdown(f"**{st.session_state.full_name or st.session_state.email}**")
        st.caption(f"Role: {st.session_state.role}")
        st.caption(f"{st.session_state.email}")
        st.divider()
        if st.button("🚪 Sign Out", use_container_width=True):
            for key in ("token", "role", "email", "full_name"):
                st.session_state[key] = None
            st.rerun()

    st.title("⚖️ Law Firm AI Assistant")
    st.markdown(
        "Use the **sidebar** to navigate between Chat, Documents, Analytics, and Admin pages."
    )

    col1, col2, col3 = st.columns(3)
    with col1:
        st.info("💬 **Chat** — Ask questions against your case documents")
    with col2:
        st.info("📁 **Documents** — Upload and manage files by matter")
    with col3:
        st.info("📊 **Analytics** — Usage stats and audit dashboards")


if st.session_state.token:
    show_app()
else:
    show_login()
