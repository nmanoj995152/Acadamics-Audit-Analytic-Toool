import pandas as pd
import streamlit as st

from auth_ui import require_page_access
from db import get_all_records, has_permission
from theme import apply_theme

st.set_page_config(page_title="Lecturer Dashboard", page_icon="📘", layout="wide")
user = require_page_access("lecturer")
apply_theme()

st.title("Lecturer dashboard")
st.caption("Class performance, subject outcomes, and practical tools for academic support.")

records = get_all_records(actor=user)
if records:
    frame = pd.DataFrame(records)
    frame["percentage"] = frame["marks_obtained"] / frame["max_marks"] * 100
    metric_cols = st.columns(4)
    metric_cols[0].metric("Class average", f"{frame['percentage'].mean():.1f}%")
    metric_cols[1].metric("Students", f"{frame['student_name'].nunique():,}")
    metric_cols[2].metric("Subjects", f"{frame['subject'].nunique():,}")
    metric_cols[3].metric("Below 50%", f"{int((frame['percentage'] < 50).sum()):,}")
else:
    st.info("No academic records are available yet.")

with st.container(border=True):
    st.subheader("Teaching tools")
    st.write("Review subject and class analytics, at-risk students, student profiles, and downloadable reports.")
    st.page_link("pages/2_Admin.py", label="Open class and subject analytics", icon=":material/analytics:")
    if has_permission(user["role"], "manage_records", can_edit_marks=user.get("can_edit_marks", False)):
        st.page_link("pages/1_Registrar.py", label="Enter or edit marks", icon=":material/edit:")
    else:
        st.caption("Mark entry and editing are disabled for this account. An administrator can grant that permission.")
