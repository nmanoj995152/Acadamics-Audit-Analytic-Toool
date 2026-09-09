"""Deterministic parsing and normalization for academic marksheets.

The parser deliberately returns the application's existing long-form record
shape.  It makes no database changes and can therefore be reviewed before
records are inserted by the UI.
"""

from __future__ import annotations

import io
import math
import re
from dataclasses import dataclass, field
from typing import Any, Iterable

import pandas as pd


CANONICAL_FIELDS = (
    "student_name",
    "section",
    "branch",
    "year",
    "subject",
    "marks_obtained",
    "max_marks",
)

SYNONYMS = {
    "student_name": {"student", "student name", "name", "candidate", "candidate name", "learner", "pupil"},
    "identifier": {"roll", "roll no", "roll number", "registration", "registration no", "registration number", "reg no", "reg number", "enrollment", "enrollment no", "enroll no", "enroll number", "admission no"},
    "section": {"section", "sec", "division"},
    "branch": {"branch", "department", "dept", "program", "programme", "course"},
    "year": {"year", "academic year", "class", "semester", "batch"},
    "subject": {"subject", "course name", "paper", "module"},
    "marks": {"marks", "marks obtained", "score", "scored", "obtained", "internal", "external", "theory", "practical"},
    "max_marks": {"max marks", "maximum", "maximum marks", "out of", "total marks", "max"},
}
IGNORED_HEADERS = {
    "s no", "serial no", "serial number", "total", "grand total", "percentage", "average", "grade", "rank", "result", "remarks", "remark",
}
ASSESSMENT_COMPONENT_PATTERN = re.compile(
    r"^(ncp|internal|ia|cat|test)\s+(?:\d+|i|ii|iii|iv|v|vi)$", re.IGNORECASE
)


def normalize_header(value: Any) -> str:
    """Return a comparable, display-independent header name."""
    text = "" if value is None else str(value)
    text = re.sub(r"^unnamed\s*:\s*\d+$", "", text.strip(), flags=re.I)
    text = text.replace("_", " ").replace("-", " ")
    text = re.sub(r"[^\w\s]", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def _matches(header: str, synonyms: Iterable[str]) -> bool:
    return header in synonyms or any(header.startswith(f"{item} ") for item in synonyms)


def _number(value: Any) -> float | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        # Accept common score notation but do not infer its denominator here.
        match = re.fullmatch(r"(-?\d+(?:\.\d+)?)\s*(?:/\s*\d+(?:\.\d+)?)?\s*%?", value)
        if not match:
            return None
        value = match.group(1)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _nonempty(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _confidence(score: int) -> str:
    return "High" if score >= 8 else "Medium" if score >= 4 else "Low"


def _is_assessment_component(header: str) -> bool:
    return bool(ASSESSMENT_COMPONENT_PATTERN.fullmatch(header))


def _is_aggregate_header(header: str) -> bool:
    return header == "total" or header.startswith(("total ", "grand total", "internal total", "aggregate", "overall marks"))


def _aggregate_max_marks(header: Any) -> float | None:
    """Read explicit limits from labels such as ``Total(60M)``."""
    text = _nonempty(header)
    if not _is_aggregate_header(normalize_header(text)):
        return None
    match = re.search(r"\(\s*(\d+(?:\.\d+)?)\s*(?:m|marks)?\s*\)", text, re.IGNORECASE)
    return float(match.group(1)) if match else None


@dataclass
class Detection:
    header_row: int
    columns: list[str]
    student_column: str | None = None
    identifier_column: str | None = None
    metadata_columns: dict[str, str] = field(default_factory=dict)
    subject_column: str | None = None
    marks_column: str | None = None
    max_marks_column: str | None = None
    subject_columns: list[str] = field(default_factory=list)
    assessment_component_columns: list[str] = field(default_factory=list)
    aggregate_column: str | None = None
    aggregate_max_marks: float | None = None
    assessment_structure: bool = False
    ignored_columns: list[str] = field(default_factory=list)
    format: str = "unknown"
    student_confidence: str = "Low"
    warnings: list[str] = field(default_factory=list)


@dataclass
class ParseResult:
    detection: Detection
    records: list[dict[str, Any]]
    invalid_rows: list[str]
    warnings: list[str]
    students: int
    subjects: int
    assumed_max_marks: bool


def detect_header_row(raw: pd.DataFrame, limit: int = 25) -> int | None:
    """Score initial rows, selecting the one most like an academic table header."""
    best_row, best_score = None, 0
    for index in range(min(limit, len(raw.index))):
        values = [normalize_header(value) for value in raw.iloc[index].tolist()]
        values = [value for value in values if value]
        if len(values) < 2:
            continue
        recognized = sum(_matches(value, group) for value in values for group in SYNONYMS.values())
        ignored = sum(value in IGNORED_HEADERS for value in values)
        # Header cells are mostly text, while data rows usually include numbers.
        numeric = sum(_number(value) is not None for value in values)
        score = recognized * 4 + ignored * 2 + min(len(values), 8) - numeric * 2
        if score > best_score:
            best_row, best_score = index, score
    return best_row if best_score >= 6 else None


def dataframe_from_raw(raw: pd.DataFrame, header_row: int) -> pd.DataFrame:
    headers = [_nonempty(value) or f"Unnamed: {index}" for index, value in enumerate(raw.iloc[header_row])]
    data = raw.iloc[header_row + 1 :].copy()
    data.columns = headers
    data = data.dropna(how="all")
    return data.reset_index(drop=True)


def detect_structure(data: pd.DataFrame, header_row: int = 0) -> Detection:
    columns = list(data.columns)
    normalized = {column: normalize_header(column) for column in columns}
    found: dict[str, str] = {}
    for semantic_field, synonyms in SYNONYMS.items():
        # A header such as "Subject A" is a legitimate wide-format subject,
        # not the long-format column named simply "Subject".
        matches = [
            column
            for column in columns
            if (normalized[column] in synonyms if semantic_field == "subject" else _matches(normalized[column], synonyms))
        ]
        if matches:
            found[semantic_field] = matches[0]

    detection = Detection(header_row=header_row, columns=columns)
    detection.student_column = found.get("student_name")
    detection.identifier_column = found.get("identifier")
    detection.subject_column = found.get("subject")
    detection.marks_column = found.get("marks")
    detection.max_marks_column = found.get("max_marks")
    for metadata_field in ("section", "branch", "year"):
        if metadata_field in found:
            detection.metadata_columns[metadata_field] = found[metadata_field]

    aggregate_columns = [column for column in columns if _is_aggregate_header(normalized[column])]
    component_groups: dict[str, list[str]] = {}
    for column in columns:
        component_match = ASSESSMENT_COMPONENT_PATTERN.fullmatch(normalized[column])
        if component_match:
            component_groups.setdefault(component_match.group(1).lower(), []).append(column)
    component_columns = max(component_groups.values(), key=len, default=[])
    # Multiple numbered components are never promoted to independent subjects.
    # An aggregate column makes this a complete one-subject assessment import.
    if len(component_columns) >= 2:
        detection.assessment_structure = True
        detection.assessment_component_columns = component_columns
        detection.aggregate_column = aggregate_columns[0] if aggregate_columns else None
        detection.aggregate_max_marks = _aggregate_max_marks(detection.aggregate_column) if detection.aggregate_column else None
        # "Total Marks" describes the aggregate score here, not a per-row max field.
        if detection.max_marks_column == detection.aggregate_column:
            detection.max_marks_column = None

    excluded = set(detection.metadata_columns.values()) | {
        value for value in (detection.student_column, detection.identifier_column, detection.subject_column, detection.marks_column, detection.max_marks_column) if value
    }
    for column in columns:
        header = normalized[column]
        if column in excluded or not header or header in IGNORED_HEADERS or column in component_columns or column in aggregate_columns:
            detection.ignored_columns.append(column)
            continue
        values = [_number(value) for value in data[column]]
        numeric_values = [value for value in values if value is not None]
        nonempty_count = sum(bool(_nonempty(value)) for value in data[column])
        numeric_ratio = len(numeric_values) / nonempty_count if nonempty_count else 0
        plausible = numeric_values and all(-1 <= value <= 1000 for value in numeric_values)
        if numeric_ratio >= 0.60 and plausible:
            detection.subject_columns.append(column)
        else:
            detection.ignored_columns.append(column)

    if detection.assessment_structure:
        detection.format = "assessment_components"
    elif detection.subject_column and detection.marks_column:
        detection.format = "long"
    elif detection.subject_columns:
        detection.format = "wide"
    if detection.student_column:
        detection.student_confidence = _confidence(8 if normalize_header(detection.student_column) in SYNONYMS["student_name"] else 4)
    if detection.identifier_column:
        detection.warnings.append(f"Identifier '{detection.identifier_column}' was detected but is not stored by the current database.")
    if not detection.max_marks_column and not detection.assessment_structure:
        detection.warnings.append("Maximum marks will default to 100 unless you change it during review.")
    if detection.assessment_structure:
        detection.warnings.append(
            "Multiple internal-assessment columns were detected as components of one subject. "
            "The aggregate marks column will be used for subject-level analytics."
        )
        if detection.aggregate_max_marks is not None:
            detection.warnings.append(
                f"Maximum marks: {detection.aggregate_max_marks:g} (detected from '{detection.aggregate_column}')."
            )
        else:
            detection.warnings.append(
                "No maximum marks value was found in the aggregate header. Set the editable default maximum marks before import."
            )
        if not detection.aggregate_column:
            detection.warnings.append("No aggregate marks column was detected. Select one manually or override this assessment detection.")
    return detection


def infer_title_metadata(raw: pd.DataFrame, header_row: int) -> dict[str, str]:
    """Conservatively use title lines such as 'Semester III' as a year value."""
    metadata: dict[str, str] = {}
    for row in raw.iloc[:header_row].itertuples(index=False):
        text = " ".join(_nonempty(item) for item in row if _nonempty(item))
        if not text:
            continue
        normalized = normalize_header(text)
        if "semester" in normalized or "academic year" in normalized:
            metadata["year"] = text
    return metadata


def parse_dataframe(raw: pd.DataFrame, *, header_row: int | None = None, mapping: dict[str, Any] | None = None, default_max_marks: float = 100.0) -> ParseResult:
    if raw.empty or raw.dropna(how="all").empty:
        detection = Detection(header_row=0, columns=[], warnings=["The spreadsheet is empty."])
        return ParseResult(detection, [], ["No table data was found."], detection.warnings, 0, 0, True)
    selected_header = detect_header_row(raw) if header_row is None else header_row
    if selected_header is None:
        detection = Detection(header_row=0, columns=[], warnings=["No recognizable header row was found."])
        return ParseResult(detection, [], ["Select a valid table header row."], detection.warnings, 0, 0, True)
    data = dataframe_from_raw(raw, selected_header)
    detection = detect_structure(data, selected_header)
    title_metadata = infer_title_metadata(raw, selected_header)
    mapping = mapping or {}
    for key in ("student_column", "identifier_column", "subject_column", "marks_column", "max_marks_column"):
        if key in mapping:
            setattr(detection, key, mapping[key] or None)
    for metadata_field in ("section", "branch", "year"):
        if metadata_field in mapping:
            value = mapping[metadata_field]
            if value in data.columns:
                detection.metadata_columns[metadata_field] = value
            elif value is None:
                detection.metadata_columns.pop(metadata_field, None)
    if "subject_columns" in mapping:
        detection.subject_columns = [column for column in mapping["subject_columns"] if column in data.columns]
    if mapping.get("disable_assessment_structure"):
        detection.assessment_structure = False
    if not detection.student_column or detection.student_column not in data.columns:
        return ParseResult(detection, [], ["No recognizable student column was found. Select one in the review controls."], detection.warnings, 0, 0, True)
    if not default_max_marks or default_max_marks <= 0:
        return ParseResult(detection, [], ["Default maximum marks must be greater than zero."], detection.warnings, 0, 0, True)

    records: list[dict[str, Any]] = []
    invalid: list[str] = []
    warnings = list(detection.warnings)
    assessment_subject_name = _nonempty(mapping.get("assessment_subject_name"))
    if detection.assessment_structure and not detection.aggregate_column:
        return ParseResult(
            detection,
            [],
            ["An aggregate marks column is required for an assessment-component marksheet before confirmation."],
            warnings,
            0,
            0,
            True,
        )
    if detection.assessment_structure and not assessment_subject_name:
        return ParseResult(
            detection,
            [],
            ["Subject name is required for an assessment-component marksheet before confirmation."],
            warnings,
            0,
            0,
            detection.aggregate_max_marks is None,
        )
    explicit_max = bool(detection.max_marks_column and detection.max_marks_column in data.columns)
    aggregate_max = detection.aggregate_max_marks if detection.assessment_structure else None
    if not explicit_max and aggregate_max is None:
        warnings.append(f"Maximum marks: {default_max_marks:g} (assumed; no maximum-mark column detected).")

    if detection.assessment_structure and detection.aggregate_column:
        work = [
            (row_index, row, assessment_subject_name, row[detection.aggregate_column])
            for row_index, row in data.iterrows()
        ]
    elif detection.subject_column and detection.marks_column:
        work = [(row_index, row, _nonempty(row[detection.subject_column]), row[detection.marks_column]) for row_index, row in data.iterrows()]
    elif detection.subject_columns:
        work = [(row_index, row, subject, row[subject]) for row_index, row in data.iterrows() for subject in detection.subject_columns]
    else:
        return ParseResult(detection, [], ["No numeric subject/marks columns were detected. Select subject columns in the review controls."], warnings, 0, 0, not explicit_max)

    seen: set[tuple[str, str]] = set()
    for row_index, row, subject, raw_mark in work:
        student = _nonempty(row[detection.student_column])
        mark = _number(raw_mark)
        if mark is None:  # A blank wide cell represents no submitted mark, not an import error.
            if _nonempty(raw_mark):
                invalid.append(f"Row {row_index + selected_header + 2}, {subject}: invalid marks value.")
            continue
        max_value = _number(row[detection.max_marks_column]) if explicit_max else aggregate_max or default_max_marks
        if not student:
            invalid.append(f"Row {row_index + selected_header + 2}, {subject}: student name is missing.")
            continue
        if max_value is None or max_value <= 0:
            invalid.append(f"Row {row_index + selected_header + 2}, {subject}: maximum marks must be greater than zero.")
            continue
        if mark < 0 or mark > max_value:
            invalid.append(f"Row {row_index + selected_header + 2}, {subject}: marks {mark:g} are outside 0–{max_value:g}.")
            continue
        key = (student.casefold(), subject.casefold())
        if key in seen:
            invalid.append(f"Row {row_index + selected_header + 2}, {subject}: duplicate student/subject record.")
            continue
        seen.add(key)
        record = {
            "student_name": student,
            "section": _nonempty(row[detection.metadata_columns["section"]]) if "section" in detection.metadata_columns else "",
            "branch": _nonempty(row[detection.metadata_columns["branch"]]) if "branch" in detection.metadata_columns else "",
            "year": _nonempty(row[detection.metadata_columns["year"]]) if "year" in detection.metadata_columns else title_metadata.get("year", ""),
            "subject": subject,
            "marks_obtained": mark,
            "max_marks": max_value,
        }
        if detection.identifier_column and detection.identifier_column in data.columns:
            record["identifier"] = _nonempty(row[detection.identifier_column])
        if detection.assessment_structure:
            record["assessment_components"] = {
                column: _nonempty(row[column]) for column in detection.assessment_component_columns
            }
        records.append(record)
    return ParseResult(detection, records, invalid, warnings, len({record["student_name"] for record in records}), len({record["subject"] for record in records}), not explicit_max and aggregate_max is None)


def load_file(uploaded_file: Any) -> dict[str, pd.DataFrame]:
    """Read CSV/XLSX without assuming a header or worksheet."""
    name = getattr(uploaded_file, "name", "").lower()
    content = uploaded_file.getvalue() if hasattr(uploaded_file, "getvalue") else uploaded_file.read()
    source = io.BytesIO(content)
    if name.endswith(".csv"):
        return {"CSV": pd.read_csv(source, header=None, dtype=object)}
    if name.endswith(".xlsx"):
        return pd.read_excel(source, sheet_name=None, header=None, dtype=object)
    raise ValueError("Only CSV and XLSX files are supported.")


def candidate_sheets(sheets: dict[str, pd.DataFrame]) -> list[str]:
    return [name for name, frame in sheets.items() if detect_header_row(frame) is not None]
