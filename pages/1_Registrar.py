import pandas as pd
import streamlit as st

from db import add_audit_log, add_option, get_all_records, get_options, get_recent_activity, insert_record, update_record, delete_record
from marksheet_parser import candidate_sheets, load_file, parse_dataframe

st.set_page_config(page_title="Registrar Dashboard", layout="wide", initial_sidebar_state="expanded")

if "user" not in st.session_state or st.session_state.user is None:
    st.warning("Please log in first")
    st.stop()

if st.session_state.user["role"] != "registrar":
    st.error("Only registrars can access this page")
    st.stop()

st.title("Registrar Dashboard")

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
    st.subheader("Manual Entry")
    with st.form("manual_form"):
        col1, col2 = st.columns(2)
        with col1:
            student_name = st.text_input("Student Name")
            marks_obtained = st.number_input("Marks Obtained", min_value=0.0, step=1.0)
            max_marks = st.number_input("Max Marks", min_value=0.0, step=1.0, value=100.0)
        with col2:
            section = st.selectbox("Section", options=["All"] + get_options("sections") + ["+ Add new..."], index=0)
            branch = st.selectbox("Branch", options=["All"] + get_options("branches") + ["+ Add new..."], index=0)
            year = st.selectbox("Year", options=["All"] + get_options("years") + ["+ Add new..."], index=0)
            subject = st.selectbox("Subject", options=["All"] + get_options("subjects") + ["+ Add new..."], index=0)

        new_section_value = st.text_input("New Section") if section == "+ Add new..." else ""
        new_branch_value = st.text_input("New Branch") if branch == "+ Add new..." else ""
        new_year_value = st.text_input("New Year") if year == "+ Add new..." else ""
        new_subject_value = st.text_input("New Subject") if subject == "+ Add new..." else ""

        submitted = st.form_submit_button("Save Record")

    if submitted:
        if not student_name.strip() or not marks_obtained or not max_marks:
            st.error("Please fill all fields")
        else:
            selected_section = new_section_value if section == "+ Add new..." and new_section_value else section if section != "All" else ""
            selected_branch = new_branch_value if branch == "+ Add new..." and new_branch_value else branch if branch != "All" else ""
            selected_year = new_year_value if year == "+ Add new..." and new_year_value else year if year != "All" else ""
            selected_subject = new_subject_value if subject == "+ Add new..." and new_subject_value else subject if subject != "All" else ""
            if selected_section:
                add_option("sections", selected_section)
            if selected_branch:
                add_option("branches", selected_branch)
            if selected_year:
                add_option("years", selected_year)
            if selected_subject:
                add_option("subjects", selected_subject)
            insert_record(student_name.strip(), selected_section, selected_branch, selected_year, selected_subject, float(marks_obtained), float(max_marks), st.session_state.user["username"])
            add_audit_log(st.session_state.user["id"], "manual_entry", {"student_name": student_name.strip(), "subject": selected_subject})
            st.success("Record saved")

with st.container(border=True):
    st.subheader("Upload File")
    uploaded_file = st.file_uploader("Upload .xlsx or .csv", type=["xlsx", "csv"])
    if uploaded_file is not None:
        try:
            sheets = load_file(uploaded_file)
            candidates = candidate_sheets(sheets)
            if not candidates:
                st.error("No recognizable academic table was found. Check that the file has a header row and numeric marks columns.")
            else:
                default_sheet = candidates[0]
                if len(candidates) > 1:
                    st.info("Multiple worksheets appear to contain academic data. Choose the one to import.")
                selected_sheet = st.selectbox("Worksheet", candidates, index=candidates.index(default_sheet), key=f"sheet_{uploaded_file.name}")
                raw = sheets[selected_sheet]
                auto_result = parse_dataframe(raw)
                header_options = list(range(len(raw.index)))
                header_default = auto_result.detection.header_row if auto_result.detection.header_row in header_options else 0
                header_row = st.selectbox(
                    "Detected header row (change if needed)",
                    header_options,
                    index=header_options.index(header_default),
                    format_func=lambda row: f"Row {row + 1}",
                    key=f"header_{uploaded_file.name}_{selected_sheet}",
                )
                # Rebuild once with the chosen header to populate review controls.
                selected_result = parse_dataframe(raw, header_row=header_row)
                columns = selected_result.detection.columns
                no_column = "— Not detected —"

                def column_choice(label, current, key):
                    options = [no_column] + columns
                    return st.selectbox(label, options, index=options.index(current) if current in options else 0, key=key)

                st.markdown("#### Review Detected Structure")
                review_col1, review_col2 = st.columns(2)
                with review_col1:
                    student_column = column_choice("Student column", selected_result.detection.student_column, f"student_{uploaded_file.name}_{selected_sheet}")
                    identifier_column = column_choice("Identifier column (not stored)", selected_result.detection.identifier_column, f"identifier_{uploaded_file.name}_{selected_sheet}")
                    subject_column = column_choice("Subject column for long format", selected_result.detection.subject_column, f"subject_{uploaded_file.name}_{selected_sheet}")
                    marks_column = column_choice("Marks column for long format", selected_result.detection.marks_column, f"marks_{uploaded_file.name}_{selected_sheet}")
                with review_col2:
                    section_column = column_choice("Section column", selected_result.detection.metadata_columns.get("section"), f"section_{uploaded_file.name}_{selected_sheet}")
                    branch_column = column_choice("Branch/department column", selected_result.detection.metadata_columns.get("branch"), f"branch_{uploaded_file.name}_{selected_sheet}")
                    year_column = column_choice("Year/semester column", selected_result.detection.metadata_columns.get("year"), f"year_{uploaded_file.name}_{selected_sheet}")
                    max_column = column_choice("Maximum marks column", selected_result.detection.max_marks_column, f"max_{uploaded_file.name}_{selected_sheet}")
                subject_columns = st.multiselect(
                    "Subject columns for wide format",
                    columns,
                    default=selected_result.detection.subject_columns,
                    help="Choose arbitrary numeric subject columns. Leave this empty when using Subject + Marks long format.",
                    key=f"wide_subjects_{uploaded_file.name}_{selected_sheet}",
                )
                assessment_subject_name = ""
                override_assessment = False
                if selected_result.detection.assessment_structure:
                    st.info(
                        "Assessment structure: One subject with multiple assessment components. "
                        "The aggregate marks column will be used for subject-level analytics."
                    )
                    assessment_subject_name = st.text_input(
                        "Subject name (required)",
                        help="The source file has assessment components but no subject name. Enter the subject used for this aggregate mark.",
                        key=f"assessment_subject_{uploaded_file.name}_{selected_sheet}",
                    )
                    override_assessment = st.checkbox(
                        "Override this detection and treat selected columns as separate subjects",
                        help="Use only if the detected component columns are actually separate subjects.",
                        key=f"override_assessment_{uploaded_file.name}_{selected_sheet}",
                    )
                default_max_marks = st.number_input("Default maximum marks", min_value=0.01, value=100.0, step=1.0, help="Used only when the file has no maximum-marks column.", key=f"default_max_{uploaded_file.name}_{selected_sheet}")
                mapping = {
                    "student_column": None if student_column == no_column else student_column,
                    "identifier_column": None if identifier_column == no_column else identifier_column,
                    "subject_column": None if subject_column == no_column else subject_column,
                    "marks_column": None if marks_column == no_column else marks_column,
                    "max_marks_column": None if max_column == no_column else max_column,
                    "section": None if section_column == no_column else section_column,
                    "branch": None if branch_column == no_column else branch_column,
                    "year": None if year_column == no_column else year_column,
                    "subject_columns": subject_columns,
                    "assessment_subject_name": assessment_subject_name,
                    "disable_assessment_structure": override_assessment,
                }
                result = parse_dataframe(raw, header_row=header_row, mapping=mapping, default_max_marks=default_max_marks)
                detection = result.detection
                st.caption(f"Student identification confidence: {detection.student_confidence}. Format: {detection.format.title()}.")
                for warning in result.warnings:
                    st.warning(warning)
                st.success(f"{result.students} students, {result.subjects} subjects, {len(result.records)} valid normalized records detected.")
                if result.invalid_rows:
                    st.error(f"{len(result.invalid_rows)} row issue(s) must be reviewed; invalid rows will not be imported.")
                    st.dataframe(pd.DataFrame({"Issue": result.invalid_rows}), use_container_width=True, hide_index=True)
                if result.records:
                    preview = pd.DataFrame(result.records)
                    preview_columns = [field for field in ["student_name", "identifier", "section", "branch", "year", "subject", "marks_obtained", "max_marks", "assessment_components"] if field in preview]
                    st.markdown("#### Normalized Preview")
                    st.dataframe(preview[preview_columns], use_container_width=True, hide_index=True)
                    if st.button("Confirm Upload", key=f"confirm_{uploaded_file.name}_{selected_sheet}"):
                        for record in result.records:
                            for field in ["section", "branch", "year", "subject"]:
                                if record[field]:
                                    add_option({"section": "sections", "branch": "branches", "year": "years", "subject": "subjects"}[field], record[field])
                            insert_record(record["student_name"], record["section"], record["branch"], record["year"], record["subject"], float(record["marks_obtained"]), float(record["max_marks"]), st.session_state.user["username"])
                        add_audit_log(st.session_state.user["id"], "upload", {"rows": len(result.records), "sheet": selected_sheet})
                        st.success(f"Upload completed: {len(result.records)} records imported.")
                elif result.invalid_rows:
                    st.info("Correct the mapping or source data to create valid records.")
        except (ValueError, OSError, pd.errors.ParserError) as error:
            st.error(f"The file could not be parsed: {error}")

with st.container(border=True):
    st.subheader("View / Edit Data")
    filter_col1, filter_col2, filter_col3, filter_col4 = st.columns(4)
    with filter_col1:
        section_filter = st.selectbox("Section Filter", options=["All"] + get_options("sections"), key="section_filter")
    with filter_col2:
        branch_filter = st.selectbox("Branch Filter", options=["All"] + get_options("branches"), key="branch_filter")
    with filter_col3:
        year_filter = st.selectbox("Year Filter", options=["All"] + get_options("years"), key="year_filter")
    with filter_col4:
        subject_filter = st.selectbox("Subject Filter", options=["All"] + get_options("subjects"), key="subject_filter")

    filters = {k: v for k, v in {"section": section_filter, "branch": branch_filter, "year": year_filter, "subject": subject_filter}.items() if v != "All"}
    records = get_all_records(filters)
    if records:
        edited_df = pd.DataFrame(records)
        edited_df["delete"] = False
        edited_df = edited_df[["id", "delete", "student_name", "section", "branch", "year", "subject", "marks_obtained", "max_marks", "entered_by", "created_at", "updated_at"]]
        edited = st.data_editor(
            edited_df,
            use_container_width=True,
            hide_index=True,
            disabled=["id", "entered_by", "created_at", "updated_at"],
            column_config={"delete": st.column_config.CheckboxColumn("Delete", help="Mark rows to delete")},
        )
        if st.button("Save Changes"):
            for _, row in edited.iterrows():
                if pd.notna(row["id"]):
                    if bool(row["delete"]):
                        delete_record(int(row["id"]))
                    else:
                        update_record(int(row["id"]), row["student_name"], row["section"], row["branch"], row["year"], row["subject"], float(row["marks_obtained"]), float(row["max_marks"]))
            st.success("Changes saved")
    else:
        st.info("No records found")

st.subheader("Recent Activity")
activity = get_recent_activity(10)
if activity:
    st.dataframe(pd.DataFrame(activity))
else:
    st.info("No activity yet")

st.divider()
if st.button("Logout", key="registrar_logout"):
    st.session_state.user = None
    st.session_state.role = None
    st.rerun()
