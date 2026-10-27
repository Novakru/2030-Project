import unittest

from audit.review_view import review_points, step_summary, text


class ExtendedReviewTests(unittest.TestCase):
    def test_missing_parameter_is_visible_and_locates_its_step(self):
        marker = {"status": "not_reported", "marker": "__NOT_REPORTED__", "evidence": "stirred", "raw": None}
        record = {"steps": [{"id": "stir", "op": "Stir", "missing_parameters": {"duration_s": marker}}]}
        summary = step_summary(record["steps"][0], record)[1]
        self.assertIn("原文未报告", summary)
        self.assertIn("__NOT_REPORTED__", summary)
        point = next(p for p in review_points(record) if p["key"].startswith("parameter:"))
        self.assertEqual(point["step_ids"], ["stir"])
        self.assertIn("原文", point["note"])

    def test_extension_definition_and_values_are_reviewable_without_a_standard_executor(self):
        record = {"operation_definitions": {"Wash": {"description": "Wash an isolated solid"}},
                  "steps": [{"id": "wash", "op": "Wash", "parameters": {
                      "liquid": {"value": "water", "evidence": "washed with water"}}}]}
        title, summary = step_summary(record["steps"][0], record)
        self.assertIn("扩展", title)
        self.assertIn("water", summary)
        point = next(p for p in review_points(record) if p["key"].startswith("extension:"))
        self.assertEqual(point["step_ids"], ["wash"])
        self.assertIn("Wash an isolated solid", point["note"])
        self.assertNotIn("evidence", text(record["steps"][0]["parameters"]["liquid"]))
