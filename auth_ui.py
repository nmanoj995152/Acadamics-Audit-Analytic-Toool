"""Shared Streamlit authentication state and role-aware navigation helpers."""
from typing import Any, MutableMapping

import streamlit as st

from db import get_user_by_id, has_permission

DASHBOARD_PATHS = {
    "student": "pages/3_Student.py",
    "lecturer": "pages/4_Lecturer.py",
    "registrar": "pages/1_Registrar.py",
    "admin": "pages/2_Admin.py",
}
DASHBOARD_TITLES = {
    "admin": "Admin Dashboard",
    "registrar": "Registrar Dashboard",
    "lecturer": "Lecturer Dashboard",
    "student": "Student Dashboard",
}
PAGE_PERMISSIONS = {
    "analytics": "view_analytics",
    "marks": "manage_records",
    "student": "view_own_records",
}
AUTH_STATE_KEYS = {
    "user", "role", "authenticated", "authenticated_user", "current_user",
    "auth_user_id", "auth_username", "auth_role", "login_username", "login_password",
    "_route_after_login", "_route_to_dashboard",
}


def dashboard_path(role: str) -> str:
    """Map an authenticated role to its own dashboard page."""
    try:
        return DASHBOARD_PATHS[role]
    except KeyError as error:
        raise ValueError("Unsupported account role") from error


def can_access_page(user: dict[str, Any] | None, page: str) -> bool:
    if not user:
        return False
    if page == "lecturer":
        return user.get("role") == "lecturer"
    if page == "analytics":
        return user.get("role") in {"admin", "lecturer"}
    permission = PAGE_PERMISSIONS.get(page)
    if permission is None:
        return False
    return has_permission(
        user.get("role", ""), permission,
        can_edit_marks=bool(user.get("can_edit_marks")),
    )


def clear_auth_state(state: MutableMapping[str, Any]) -> None:
    """Remove all identity and login-form state before account switching."""
    for key in AUTH_STATE_KEYS:
        state.pop(key, None)


def current_user() -> dict[str, Any] | None:
    """Refresh role and identifier from SQLite instead of trusting stale state."""
    saved = st.session_state.get("user")
    if not isinstance(saved, dict) or saved.get("id") is None:
        st.session_state.pop("role", None)
        return None
    user = get_user_by_id(int(saved["id"]))
    if user is None:
        clear_auth_state(st.session_state)
        return None
    st.session_state["user"] = user
    st.session_state["role"] = user["role"]
    return user


def _logout_and_return_to_login() -> None:
    clear_auth_state(st.session_state)
    st.rerun()


def render_logout(user: dict[str, Any]) -> None:
    """Render a consistent, visible logout action in the app sidebar."""
    with st.sidebar:
        st.markdown(f"**Signed in:** {user['username']}")
        st.caption(user["role"].title())
        st.button(
            "Log out",
            key="global_logout",
            icon=":material/logout:",
            width="stretch",
            on_click=_logout_and_return_to_login,
        )


def require_page_access(page: str) -> dict[str, Any]:
    """Gate a dashboard and route unauthorized sessions to login/their home."""
    user = current_user()
    if user is None:
        st.warning("Sign in is required to view this page.")
        st.page_link("pages/0_Home.py", label="Go to sign in", icon=":material/login:")
        st.stop()
    if not can_access_page(user, page):
        st.warning("This page is not available to your account role.")
        st.page_link(dashboard_path(user["role"]), label="Go to your dashboard", icon=":material/dashboard:")
        st.stop()
    render_logout(user)
    return user
