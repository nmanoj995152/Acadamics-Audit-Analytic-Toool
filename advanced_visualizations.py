"""Reusable, defensive Plotly views for the Admin academic dashboard.

Each factory accepts the dashboard's already-filtered long-form records.  A
factory returns ``None`` when the available data cannot support the insight,
allowing the page to show a useful empty-state instead of raising an error.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


PASS_THRESHOLD = 50
GOOD_THRESHOLD = 75


def clean_analytics_data(records: pd.DataFrame) -> pd.DataFrame:
    """Return valid records with a calculated percentage, without mutating input."""
    required = {"student_name", "subject", "marks_obtained", "max_marks"}
    if records.empty or not required.issubset(records.columns):
        return pd.DataFrame()
    data = records.copy()
    data["marks_obtained"] = pd.to_numeric(data["marks_obtained"], errors="coerce")
    data["max_marks"] = pd.to_numeric(data["max_marks"], errors="coerce")
    data = data[data["max_marks"] > 0].dropna(subset=["student_name", "subject", "marks_obtained", "max_marks"])
    data["student_name"] = data["student_name"].astype(str).str.strip()
    data["subject"] = data["subject"].astype(str).str.strip()
    data = data[(data["student_name"] != "") & (data["subject"] != "")]
    data["percentage"] = (data["marks_obtained"] / data["max_marks"] * 100).round(2)
    return data


def create_performance_distribution(data: pd.DataFrame) -> Optional[go.Figure]:
    """Show the spread of record-level percentages and the app's 50/75% bands.

    This uses calculated percentages from the filtered records to reveal where
    performance clusters, rather than another category-count chart.
    """
    if data.empty or data["percentage"].dropna().empty:
        return None
    fig = px.histogram(data, x="percentage", nbins=min(20, max(5, len(data))),
                       title="Performance Distribution", labels={"percentage": "Percentage", "count": "Records"},
                       color_discrete_sequence=["#2563eb"])
    fig.add_vrect(x0=0, x1=PASS_THRESHOLD, fillcolor="#ef4444", opacity=0.09, line_width=0,
                  annotation_text="Poor", annotation_position="top left")
    fig.add_vrect(x0=PASS_THRESHOLD, x1=GOOD_THRESHOLD, fillcolor="#f59e0b", opacity=0.09, line_width=0,
                  annotation_text="Average", annotation_position="top left")
    fig.add_vrect(x0=GOOD_THRESHOLD, x1=100, fillcolor="#22c55e", opacity=0.09, line_width=0,
                  annotation_text="Good", annotation_position="top left")
    fig.update_layout(bargap=0.08, showlegend=False)
    return fig


def create_subject_boxplot(data: pd.DataFrame) -> Optional[go.Figure]:
    """Compare subject medians, variability, and outliers using percentages.

    Values are the filtered records' calculated percentages, aggregated visually
    by subject; two or more subjects are needed for a meaningful comparison.
    """
    if data.empty or data["subject"].nunique() < 2:
        return None
    fig = px.box(data, x="subject", y="percentage", points="outliers", color="subject",
                 title="Subject Performance Variability", labels={"subject": "Subject", "percentage": "Percentage"})
    fig.update_layout(showlegend=False, xaxis_tickangle=-30)
    return fig


def create_performance_heatmap(data: pd.DataFrame, max_students: int = 20) -> Optional[go.Figure]:
    """Map each selected student's subject percentages to expose uneven strengths.

    It averages duplicate student-subject rows from filtered data and limits the
    display to the lowest-average students so a large cohort remains readable.
    """
    if data.empty or data["student_name"].nunique() < 2 or data["subject"].nunique() < 2:
        return None
    matrix = data.pivot_table(index="student_name", columns="subject", values="percentage", aggfunc="mean")
    matrix = matrix.loc[matrix.mean(axis=1).sort_values().head(max_students).index]
    if matrix.empty:
        return None
    fig = px.imshow(matrix, aspect="auto", color_continuous_scale="RdYlGn", zmin=0, zmax=100,
                    title=f"Student–Subject Performance Heatmap (up to {max_students} students)",
                    labels={"x": "Subject", "y": "Student", "color": "Percentage"})
    fig.update_xaxes(side="bottom", tickangle=-30)
    return fig


def create_subject_risk_matrix(data: pd.DataFrame) -> Optional[go.Figure]:
    """Identify difficult subjects by mean score and share below the 50% threshold.

    Each point summarizes one subject from filtered records: x is mean percentage,
    y is the percentage of its records classified as Poor by the existing cutoff.
    """
    if data.empty or data["subject"].nunique() < 2:
        return None
    summary = data.groupby("subject", as_index=False).agg(
        average_percentage=("percentage", "mean"),
        at_risk_share=("percentage", lambda values: (values < PASS_THRESHOLD).mean() * 100),
        records=("percentage", "size"),
    )
    fig = px.scatter(summary, x="average_percentage", y="at_risk_share", size="records", color="at_risk_share",
                     text="subject", color_continuous_scale="RdYlGn_r", range_x=[0, 100], range_y=[0, 100],
                     title="Subject Difficulty / Risk Matrix",
                     labels={"average_percentage": "Average percentage", "at_risk_share": "Below 50% (%)"},
                     hover_data={"records": True, "average_percentage": ":.1f", "at_risk_share": ":.1f"})
    fig.update_traces(textposition="top center")
    fig.add_vline(x=PASS_THRESHOLD, line_dash="dash", line_color="#ef4444")
    return fig


def create_student_profile(data: pd.DataFrame, student_name: str) -> Optional[go.Figure]:
    """Show one student's subject-level percentage profile from filtered records.

    Duplicate rows for the chosen student and subject are averaged, giving an
    administrator a compact view of strengths and weak subjects.
    """
    profile = data[data["student_name"] == student_name].groupby("subject", as_index=False)["percentage"].mean()
    if profile.empty:
        return None
    fig = px.bar(profile.sort_values("percentage"), x="subject", y="percentage", color="percentage",
                 range_y=[0, 100], color_continuous_scale="RdYlGn",
                 title=f"Student Performance Profile: {student_name}",
                 labels={"subject": "Subject", "percentage": "Average percentage"})
    fig.add_hline(y=PASS_THRESHOLD, line_dash="dash", line_color="#ef4444", annotation_text="50% threshold")
    fig.update_layout(xaxis_tickangle=-30, coloraxis_showscale=False)
    return fig
