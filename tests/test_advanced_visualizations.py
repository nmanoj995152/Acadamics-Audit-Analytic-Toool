import unittest

import pandas as pd

from advanced_visualizations import (
    clean_analytics_data,
    create_performance_distribution,
    create_performance_heatmap,
    create_student_profile,
    create_subject_boxplot,
    create_subject_risk_matrix,
)


class AdvancedVisualizationTests(unittest.TestCase):
    def setUp(self):
        self.data = clean_analytics_data(pd.DataFrame([
            {"student_name": "A", "subject": "Math", "marks_obtained": 40, "max_marks": 100},
            {"student_name": "A", "subject": "Science", "marks_obtained": 80, "max_marks": 100},
            {"student_name": "B", "subject": "Math", "marks_obtained": 60, "max_marks": 100},
            {"student_name": "B", "subject": "Science", "marks_obtained": 90, "max_marks": 100},
        ]))

    def test_factories_return_figures_for_sufficient_data(self):
        for factory in (create_performance_distribution, create_subject_boxplot, create_performance_heatmap, create_subject_risk_matrix):
            self.assertIsNotNone(factory(self.data))
        self.assertIsNotNone(create_student_profile(self.data, "A"))

    def test_cleaner_removes_invalid_denominators(self):
        cleaned = clean_analytics_data(pd.DataFrame([
            {"student_name": "A", "subject": "Math", "marks_obtained": 2, "max_marks": 0},
        ]))
        self.assertTrue(cleaned.empty)

    def test_sparse_data_returns_safe_empty_states(self):
        one = self.data.iloc[[0]]
        self.assertIsNotNone(create_performance_distribution(one))
        self.assertIsNone(create_subject_boxplot(one))
        self.assertIsNone(create_performance_heatmap(one))
        self.assertIsNone(create_subject_risk_matrix(one))


if __name__ == "__main__":
    unittest.main()
