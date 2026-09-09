import io
import unittest

import pandas as pd

from marksheet_parser import candidate_sheets, load_file, normalize_header, parse_dataframe


class MarksheetParserTests(unittest.TestCase):
    def parse(self, rows):
        return parse_dataframe(pd.DataFrame(rows))

    def test_existing_canonical_long_format(self):
        result = self.parse([["student_name", "section", "branch", "year", "subject", "marks_obtained", "max_marks"], ["Rahul", "A", "CSE", "3", "DBMS", 85, 100]])
        self.assertEqual(result.records[0]["student_name"], "Rahul")
        self.assertEqual(result.records[0]["subject"], "DBMS")

    def test_wide_arbitrary_subjects_and_alternative_names(self):
        result = self.parse([["Candidate Name", "Registration Number", "DBMS", "OS", "Computer Networks", "Total", "Percentage"], ["Rahul", "R1", 82, 76, 88, 246, 82]])
        self.assertEqual({r["subject"] for r in result.records}, {"DBMS", "OS", "Computer Networks"})
        self.assertEqual(result.records[0]["identifier"], "R1")

    def test_title_rows_and_later_header(self):
        result = self.parse([["ABC University"], ["B.Tech Examination"], ["Semester III"], ["Roll Number", "Student Name", "AI", "ML"], [101, "Anu", 91, 84]])
        self.assertEqual(result.detection.header_row, 3)
        self.assertEqual(result.records[0]["year"], "Semester III")

    def test_different_order_and_ignored_derived_columns(self):
        result = self.parse([["Physics", "Student Name", "Roll No", "Chemistry", "Maths", "Grade"], [72, "Rahul", 101, 91, 85, "A"]])
        self.assertEqual(result.subjects, 3)
        self.assertNotIn("Grade", result.detection.subject_columns)

    def test_invalid_marks_and_missing_student_are_reported(self):
        result = self.parse([["Name", "DBMS"], ["Rahul", 110], [None, 60]])
        self.assertFalse(result.records)
        self.assertEqual(len(result.invalid_rows), 2)

    def test_empty_sheet(self):
        result = parse_dataframe(pd.DataFrame())
        self.assertFalse(result.records)
        self.assertTrue(result.invalid_rows)

    def test_explicit_max_marks(self):
        result = self.parse([["Name", "Subject", "Marks", "Max Marks"], ["Rahul", "DBMS", 45, 50]])
        self.assertEqual(result.records[0]["max_marks"], 50)
        self.assertFalse(result.assumed_max_marks)

    def test_maximum_marks_fallback(self):
        result = self.parse([["Name", "MATH"], ["Rahul", 85]])
        self.assertTrue(result.assumed_max_marks)
        self.assertEqual(result.records[0]["max_marks"], 100)

    def test_candidate_sheets(self):
        sheets = {"Cover": pd.DataFrame([["University"]]), "Marks": pd.DataFrame([["Name", "AI"], ["R", 80]])}
        self.assertEqual(candidate_sheets(sheets), ["Marks"])

    def test_header_normalization(self):
        self.assertEqual(normalize_header(" Student_Name-2025! "), "student name 2025")

    def test_global_metadata_is_preserved(self):
        result = self.parse([["Academic Year 2025-26"], ["Name", "AI"], ["Ravi", 80]])
        self.assertEqual(result.records[0]["year"], "Academic Year 2025-26")

    def test_invalid_explicit_maximum_marks(self):
        result = self.parse([["Name", "Subject", "Marks", "Max Marks"], ["Ravi", "AI", 50, 0]])
        self.assertFalse(result.records)
        self.assertIn("maximum marks", result.invalid_rows[0])

    def test_blank_wide_marks_are_skipped(self):
        result = self.parse([["Name", "AI", "ML"], ["Ravi", 80, None]])
        self.assertEqual(len(result.records), 1)

    def test_user_mapping_can_select_low_confidence_student_column(self):
        raw = pd.DataFrame([["Roll No", "Candidate Full", "Cloud Computing"], [101, "Ravi", 85]])
        result = parse_dataframe(raw, mapping={"student_column": "Candidate Full", "subject_columns": ["Cloud Computing"]})
        self.assertEqual(result.records[0]["student_name"], "Ravi")

    def test_xlsx_loader_returns_all_sheets(self):
        stream = io.BytesIO()
        with pd.ExcelWriter(stream, engine="openpyxl") as writer:
            pd.DataFrame([["University"]]).to_excel(writer, sheet_name="Cover", header=False, index=False)
            pd.DataFrame([["Name", "AI"], ["Ravi", 80]]).to_excel(writer, sheet_name="Marks", header=False, index=False)

        class Upload:
            name = "marks.xlsx"

            def getvalue(self):
                return stream.getvalue()

        sheets = load_file(Upload())
        self.assertEqual(set(sheets), {"Cover", "Marks"})
        self.assertEqual(candidate_sheets(sheets), ["Marks"])

    def test_ncp_components_use_total_as_one_subject_mark(self):
        result = self.parse(
            [
                ["S No", "Enroll no", "Name", "NCP-I", "NCP-II", "NCP-III", "NCP-IV", "Total(60M)", "Signature"],
                [1, "E1", "Sriram Bhavya Sri", 10, 11, 12.5, 10, 43.5, ""],
                [2, "E2", "Vadla Megavardhan Chary", 8, 7, 6, 9, 30, ""],
            ],
        )
        required = parse_dataframe(
            pd.DataFrame(
                [
                    ["S No", "Enroll no", "Name", "NCP-I", "NCP-II", "NCP-III", "NCP-IV", "Total(60M)"],
                    [1, "E1", "Sriram Bhavya Sri", 10, 11, 12.5, 10, 43.5],
                ]
            )
        )
        self.assertTrue(result.detection.assessment_structure)
        self.assertEqual(result.detection.aggregate_column, "Total(60M)")
        self.assertFalse(required.records)
        self.assertIn("Subject name is required", required.invalid_rows[0])
        mapped = parse_dataframe(
            pd.DataFrame(
                [
                    ["S No", "Enroll no", "Name", "NCP-I", "NCP-II", "NCP-III", "NCP-IV", "Total(60M)"],
                    [1, "E1", "Sriram Bhavya Sri", 10, 11, 12.5, 10, 43.5],
                ]
            ),
            mapping={"assessment_subject_name": "Network Communication Protocols"},
        )
        self.assertEqual(len(mapped.records), 1)
        self.assertEqual(mapped.records[0]["subject"], "Network Communication Protocols")
        self.assertEqual(mapped.records[0]["marks_obtained"], 43.5)
        self.assertEqual(mapped.records[0]["max_marks"], 60)
        self.assertEqual(set(mapped.records[0]["assessment_components"]), {"NCP-I", "NCP-II", "NCP-III", "NCP-IV"})

    def test_internal_components_with_total_marks_use_editable_default_maximum(self):
        result = parse_dataframe(
            pd.DataFrame([["Name", "Internal 1", "Internal 2", "Internal 3", "Total Marks"], ["Ravi", 8, 9, 10, 27]]),
            mapping={"assessment_subject_name": "DBMS"},
            default_max_marks=30,
        )
        self.assertTrue(result.detection.assessment_structure)
        self.assertEqual(result.records[0]["max_marks"], 30)
        self.assertTrue(result.assumed_max_marks)

    def test_ia_components_with_aggregate_are_one_subject(self):
        result = parse_dataframe(
            pd.DataFrame([["Name", "IA-1", "IA-2", "IA-3", "Aggregate"], ["Ravi", 15, 14, 16, 45]]),
            mapping={"assessment_subject_name": "Artificial Intelligence"},
            default_max_marks=50,
        )
        self.assertEqual([record["subject"] for record in result.records], ["Artificial Intelligence"])
        self.assertEqual(result.records[0]["marks_obtained"], 45)

    def test_regular_wide_subject_columns_are_not_components(self):
        result = self.parse([["Name", "Subject A", "Subject B", "Subject C"], ["Ravi", 70, 80, 90]])
        self.assertFalse(result.detection.assessment_structure)
        self.assertEqual({record["subject"] for record in result.records}, {"Subject A", "Subject B", "Subject C"})

    def test_components_without_aggregate_are_blocked(self):
        result = parse_dataframe(
            pd.DataFrame([["Name", "CAT-1", "CAT-2", "CAT-3"], ["Ravi", 10, 12, 13]]),
            mapping={"assessment_subject_name": "DBMS"},
        )
        self.assertFalse(result.records)
        self.assertIn("aggregate marks column", result.invalid_rows[0])


if __name__ == "__main__":
    unittest.main()
