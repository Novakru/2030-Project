"""Meaningful display checks: correct evidence location, parent values and no invented facts."""
from copy import deepcopy
import unittest

from audit.review_view import focus_indices, procedure, review_points, step_summary
from audit.tests.test_risk_reason import missing_heater


class ReviewViewTests(unittest.TestCase):
    def base(self):
        return {"id": "pos", "steps": [{"id": "s1", "op": "Add", "reagent": "r1",
                    "amount": {"value": 1, "unit": "mL"}}, {"id": "s2", "op": "Stir"}],
                "reagents": [{"id": "r1", "name": "water", "smiles": "O"}]}

    def test_capacity_edit_points_to_actual_charge_and_preserves_parent_value(self):
        parent = self.base()
        child = deepcopy(parent)
        child["steps"][0]["amount"]["value"] = 55
        record = {"id": "neg", "protocol": child, "label": {"risk_l2": "A1"},
                  "diff": [{"op": "replace", "path": "/steps/0/amount/value", "value": 55},
                           {"op": "remove", "path": "/quality/tier"},
                           {"op": "replace", "path": "/xdl", "value": "irrelevant metadata"}]}
        points = review_points(record, parent)
        self.assertEqual(len(points), 1)
        self.assertEqual(points[0]["changes"][0]["before"], "1 mL")
        self.assertEqual(points[0]["changes"][0]["after"], "55 mL")
        self.assertEqual(focus_indices(procedure(record), points[0]), [0])
        self.assertEqual(parent["steps"][0]["amount"]["value"], 1)

    def test_removed_step_uses_parent_id_and_does_not_misidentify_remaining_step(self):
        parent = self.base()
        child = deepcopy(parent)
        child["steps"].pop(0)
        record = {"id": "neg", "protocol": child, "diff": [{"op": "remove", "path": "/steps/0"}]}
        point = review_points(record, parent)[0]
        self.assertEqual(point["step_ids"], ["s1"])
        self.assertEqual(point["changes"][0]["after"], "已移除")
        self.assertEqual(point["removed_step"]["_id"], "s1")
        self.assertEqual(procedure(record)[0]["_id"], "s2")

    def test_native_contract_locates_consumer_instead_of_first_xdl_step(self):
        record = {"id": "neg_D2", "xdl": '<Synthesis><Procedure><Add reagent="x"/><Stir/><Evaporate vessel="v"/></Procedure></Synthesis>',
                  "label": {"risk_l2": "D2"}, "contract": {"consumer_xpath": "/Synthesis/Procedure/Evaporate",
                                                              "producer_xpath": "/Synthesis/Procedure/Transfer[1]"}}
        point = review_points(record)[0]
        steps = procedure(record)
        self.assertEqual(focus_indices(steps, point), [2])
        self.assertEqual(steps[2]["op"], "Evaporate")

    def test_quantity_unknown_is_prioritized_and_quotes_are_preserved(self):
        record = self.base()
        record["crosscheck"] = {"quantity_checks": [
            {"status": "matched", "step_id": "s1", "alias": "water", "measurements": [{"quote": "1 mL"}],
             "expected": {"value": 1, "unit": "mL"}},
            {"status": "unknown", "step_id": "s2", "alias": "catalyst", "expected": {"value": 0.2, "unit": "mmol"}}]}
        points = review_points(record)
        self.assertIn("catalyst", points[0]["title"])
        self.assertEqual(focus_indices(procedure(record), points[0]), [1])
        self.assertEqual(points[1]["changes"][0]["before"], "1 mL")

    def test_reagent_changes_follow_references_and_do_not_reuse_stale_source_alias(self):
        parent = self.base()
        parent["steps"][0]["meta"] = {"source_alias": "dry THF"}
        child = deepcopy(parent)
        child["reagents"][0]["name"] = "methanol"
        record = {"id": "neg_C1", "protocol": child,
                  "diff": [{"op": "replace", "path": "/reagents/0/name", "value": "methanol"}]}
        point = review_points(record, parent)[0]
        self.assertEqual(focus_indices(procedure(record), point), [0])
        self.assertIn("methanol", step_summary(procedure(record)[0], record)[1])
        self.assertNotIn("dry THF", step_summary(procedure(record)[0], record)[1])

    def test_missing_parent_is_explicit_not_guessed_from_patch(self):
        record = self.base()
        record["diff"] = [{"op": "replace", "path": "/steps/0/amount/value", "value": 50}]
        point = review_points(record)[0]
        self.assertEqual(point["changes"][0]["before"], "父记录未导入")
        self.assertEqual(point["changes"][0]["after"], "1 mL")

    def test_A5_prefers_explicit_heating_and_summarizes_the_deleted_device(self):
        row, parent = missing_heater()
        point = review_points(row, parent)[0]
        self.assertEqual(point["preferred_step_id"], "s009")
        self.assertEqual(focus_indices(procedure(row), point), [8, 6])
        self.assertIn("加热搅拌器", point["changes"][0]["before"])
        self.assertNotIn("{", point["changes"][0]["before"])
        self.assertEqual(point["changes"][0]["after"], "设备已删除")


if __name__ == "__main__":
    unittest.main()
