import streamlit as st

from auth_ui import current_user, render_logout
from db import authenticate_user
from theme import apply_theme

st.set_page_config(page_title="Academic Audit Analytics", page_icon="📘", layout="wide")
apply_theme()

st.title("Academic Audit Analytics")
st.caption("A clear view of student progress, class performance, and academic support needs.")

user = current_user()
if user is None:
    left, center, right = st.columns([1, 1.2, 1])
    with center:
        with st.container(border=True):
            st.subheader("Sign in")
            st.caption("Accounts are provisioned by an administrator.")
            with st.form("login_form"):
                username = st.text_input("Username", key="login_username")
                password = st.text_input("Password", type="password", key="login_password")
                submitted = st.form_submit_button("Sign in", width="stretch")
            if submitted:
                authenticated = authenticate_user(username, password)
                if authenticated:
                    st.session_state["user"] = authenticated
                    st.session_state["role"] = authenticated["role"]
                    st.session_state["_route_after_login"] = True
                    st.rerun()
                else:
                    st.error("Invalid username or password")
else:
    render_logout(user)
    st.success(f"Signed in as {user['username']} · {user['role'].title()}")
    st.write("Open your role dashboard, or log out to switch accounts.")
    if st.button(f"Open {user['role'].title()} dashboard", icon=":material/dashboard:"):
        st.session_state["_route_to_dashboard"] = True
        st.rerun()
