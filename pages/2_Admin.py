import pandas as pd
import plotly.express as px
import streamlit as st

from advanced_visualizations import (
    clean_analytics_data,
    create_performance_distribution,
    create_performance_heatmap,
    create_student_profile,
    create_subject_boxplot,
    create_subject_risk_matrix,
)
from db import get_all_records, get_options
from utils import classify, recommendation_for

st.set_page_config(page_title="Admin Dashboard", layout="wide", initial_sidebar_state="expanded")

if "user" not in st.session_state or st.session_state.user is None:
    st.warning("Please log in first")
    st.stop()

if st.session_state.user["role"] != "admin":
    st.error("Only administrators can access this page")
    st.stop()

st.title("Admin Analytics Dashboard")

st.markdown(
    """
    <style>
    html, body {
        height: 100%;
        margin: 0;
    }
    [data-testid="stAppViewContainer"] {
        background-image: linear-gradient(rgba(255,255,255,0.55), rgba(255,255,255,0.55)),
                          url("https://dfhe5ze0n4pxu.cloudfront.net/College/Background-Images/Background-Image-1767169969170.jpeg");
        background-size: cover;
        background-position: center center;
        background-repeat: no-repeat;
        background-attachment: scroll;
        min-height: 100vh;
    }
    .stApp { background: transparent !important; }
    .st-bd, .st-cf { border-radius: 10px; }
    </style>
    """,
    unsafe_allow_html=True,
)

with st.container(border=True):
    st.subheader("Filters")
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        section_filter = st.selectbox("Section", ["All"] + get_options("sections"), key="admin_section")
    with col2:
        branch_filter = st.selectbox("Branch", ["All"] + get_options("branches"), key="admin_branch")
    with col3:
        year_filter = st.selectbox("Year", ["All"] + get_options("years"), key="admin_year")
    with col4:
        subject_filter = st.selectbox("Subject", ["All"] + get_options("subjects"), key="admin_subject")
    with col5:
        student_filter = st.text_input("Student Name")

    if st.button("Get Analysis"):
        filters = {}
        for field, value in {"section": section_filter, "branch": branch_filter, "year": year_filter, "subject": subject_filter}.items():
            if value != "All":
                filters[field] = value
        if student_filter.strip():
            filters["student_name"] = student_filter.strip()
        records = get_all_records(filters)
        if not records:
            st.info("No records match the selected filters")
            st.stop()

        df = pd.DataFrame(records)
        if df.empty:
            st.info("No records found")
            st.stop()

        df["percentage"] = (df["marks_obtained"] / df["max_marks"] * 100).round(2)
        df["classification"] = df["percentage"].apply(lambda value: classify(value, 100))
        avg_pct = round(df["percentage"].mean(), 2)
        count = len(df)
        counts = df["classification"].value_counts().to_dict()
        good_count = counts.get("Good", 0)
        avg_count = counts.get("Average", 0)
        poor_count = counts.get("Poor", 0)

        metric_col1, metric_col2, metric_col3, metric_col4 = st.columns(4)
        metric_col1.metric("Average %", f"{avg_pct}%")
        metric_col2.metric("Students", count)
        metric_col3.metric("Good", good_count)
        metric_col4.metric("Poor", poor_count)

        chart_col1, chart_col2 = st.columns(2)
        group_column = "subject" if section_filter != "All" or branch_filter != "All" or year_filter != "All" else "section"
        if student_filter.strip():
            group_column = "subject"
        grouped = df.groupby(group_column)["percentage"].mean().reset_index()
        bar_fig = px.bar(grouped, x=group_column, y="percentage", title=f"Average Marks by {group_column.title()}", color_discrete_sequence=["#2563eb"])
        chart_col1.plotly_chart(bar_fig, use_container_width=True)

        pie_df = df["classification"].value_counts().reset_index()
        pie_df.columns = ["classification", "count"]
        pie_fig = px.pie(pie_df, names="classification", values="count", title="Distribution")
        chart_col2.plotly_chart(pie_fig, use_container_width=True)

        poor_df = df[df["classification"] == "Poor"].copy()
        st.subheader("Poor Performers")
        st.dataframe(poor_df[["student_name", "section", "branch", "year", "subject", "percentage"]], use_container_width=True)

        if poor_count:
            share = round((poor_count / count) * 100, 1)
            suggestion = f"{share}% of the selected group are in the Poor band. Suggested action: {recommendation_for('Poor')}"
        else:
            suggestion = "No immediate remediation required for the current filtered set."
        with st.container(border=True):
            st.subheader("Suggestions")
            st.info(suggestion)

        # The charts below reuse the records selected by the existing filters.
        # The profile selector is necessary because a profile needs one known,
        # currently matching student rather than another broad dashboard filter.
        analytics_df = clean_analytics_data(df)
        st.divider()
        st.subheader("Advanced Academic Analytics")
        if analytics_df.empty:
            st.info("No sufficient data available for the advanced visualizations.")
        else:
            advanced_col1, advanced_col2 = st.columns(2)
            distribution_fig = create_performance_distribution(analytics_df)
            boxplot_fig = create_subject_boxplot(analytics_df)
            with advanced_col1:
                if distribution_fig is not None:
                    st.plotly_chart(distribution_fig, use_container_width=True)
                else:
                    st.info("No sufficient data available for the performance distribution.")
            with advanced_col2:
                if boxplot_fig is not None:
                    st.plotly_chart(boxplot_fig, use_container_width=True)
                else:
                    st.info("No sufficient data available to compare subject variability.")

            heatmap_fig = create_performance_heatmap(analytics_df)
            if heatmap_fig is not None:
                st.plotly_chart(heatmap_fig, use_container_width=True)
            else:
                st.info("No sufficient data available for the student-subject heatmap.")

            risk_fig = create_subject_risk_matrix(analytics_df)
            if risk_fig is not None:
                st.plotly_chart(risk_fig, use_container_width=True)
            else:
                st.info("No sufficient data available for the subject risk matrix.")

            profile_students = sorted(analytics_df["student_name"].unique())
            if profile_students:
                selected_profile_student = st.selectbox(
                    "Student profile",
                    profile_students,
                    key="advanced_student_profile",
                )
                profile_fig = create_student_profile(analytics_df, selected_profile_student)
                if profile_fig is not None:
                    st.plotly_chart(profile_fig, use_container_width=True)
                else:
                    st.info("No sufficient data available for this student profile.")

st.divider()
if st.button("Logout", key="admin_logout"):
    st.session_state.user = None
    st.session_state.role = None
    st.rerun()
