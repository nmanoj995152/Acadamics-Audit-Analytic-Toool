import pandas as pd
import streamlit as st

from db import get_student_records
from theme import apply_theme
from utils import classify, recommendation_for
from auth_ui import require_page_access

st.set_page_config(page_title="My Academic Progress", page_icon="📘", layout="wide")
user = require_page_access("student")

apply_theme()
st.title("My Academic Progress")
st.caption("Your marks, subject performance, and practical next steps.")
records = get_student_records(user)
if not records:
    st.info("No academic records are linked to this account yet. Legacy records remain private until an administrator verifies your roll or enrollment number and future records are imported with that identifier.")
    st.stop()

df = pd.DataFrame(records)
df["percentage"] = (df["marks_obtained"] / df["max_marks"] * 100).round(1)
df["performance"] = df["percentage"].map(lambda pct: classify(pct, 100))
one, two, three = st.columns(3)
one.metric("Overall average", f"{df['percentage'].mean():.1f}%")
two.metric("Assessments", str(len(df)))
three.metric("Subjects", str(df["subject"].nunique()))
st.subheader("Subject results")
st.dataframe(df[["subject", "year", "marks_obtained", "max_marks", "percentage", "performance"]], width="stretch", hide_index=True)
st.download_button("Download my results", df.to_csv(index=False).encode("utf-8"), "my_academic_results.csv", "text/csv")
st.subheader("Improvement suggestions")
for _, row in df.sort_values("percentage").iterrows():
    band = row["performance"]
    with st.container(border=True):
        st.markdown(f"**{row['subject']} · {row['percentage']:.1f}% · {band}**")
        st.write(recommendation_for(band))
