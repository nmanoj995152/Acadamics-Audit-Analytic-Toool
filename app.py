"""Entrypoint and role-aware navigation for the Academic Audit app."""
import streamlit as st

from auth_ui import DASHBOARD_PATHS, DASHBOARD_TITLES, current_user
from db import initialize_db
from theme import apply_theme

initialize_db()
st.set_page_config(page_title="Academic Audit Analytics", page_icon="📘", layout="wide")
apply_theme()

user = current_user()
route_after_login = bool(st.session_state.pop("_route_after_login", False))
route_from_home = bool(st.session_state.pop("_route_to_dashboard", False))
route_to_dashboard = route_after_login or route_from_home

# Streamlit only renders pages registered with st.navigation. Keep all four
# dashboard destinations visible, while each page's require_page_access guard
# remains authoritative for access to its data and actions.
role_pages = {
    role: st.Page(
        path,
        title=DASHBOARD_TITLES[role],
        icon=":material/dashboard:",
        default=bool(route_to_dashboard and user and user["role"] == role),
    )
    for role, path in DASHBOARD_PATHS.items()
}
pages = {
    "": [st.Page(
        "pages/0_Home.py",
        title="Academic Audit Analytics",
        icon=":material/home:",
        default=not route_to_dashboard,
    )],
    "Dashboard Navigation": list(role_pages.values()),
}

navigation = st.navigation(pages, position="sidebar")
if user and route_to_dashboard and user["role"] in role_pages:
    st.switch_page(role_pages[user["role"]])
navigation.run()
