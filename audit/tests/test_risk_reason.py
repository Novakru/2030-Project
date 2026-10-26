from copy import deepcopy
import unittest

from audit.risk_reason import explain_risk


def record(code, rule_id, values):
    return {"label": {"risk_l2": code, "label_type": "hard", "judge": "symbolic",
                      "evidence": [{"rule_id": rule_id, "risk": code, "values": values}]}}


def missing_heater():
    row = record("A5", "A5.required_controller_missing", {"controller": "heater", "step_id": "s007"})
    row["label"]["evidence"].append({"risk": "A5", "rule_id": "A5.required_controller_missing",
                                      "values": {"controller": "heater", "step_id": "s009"}})
    row["protocol"] = {"hardware": {"nodes": {}, "bindings": {"heater": "heater"}},
        "steps": [{"id": f"s00{i}", "op": "Add"} for i in range(1, 7)] + [
            {"id": "s007", "op": "Stir", "duration_s": 120}, {"id": "s008", "op": "Add"},
            {"id": "s009", "op": "HeatChill", "temp_C": 80, "duration_s": 43200, "stir": True}]}
    row["diff"] = [{"op": "remove", "path": "/hardware/nodes/heater"}]
    parent = deepcopy(row["protocol"])
    parent["hardware"]["nodes"]["heater"] = {"category": "heater_stirrer", "id": "ika_rct_basic_25008259"}
    return row, parent


class RiskReasonTests(unittest.TestCase):
    def test_capacity_uses_frozen_evidence_and_leaves_record_unchanged(self):
        row = record("A1", "A1.capacity", {"volume_mL": 55, "capacity_mL": 50})
        original = deepcopy(row)
        result = explain_risk(row)
        self.assertIn("55 mL", result["summary"])
        self.assertIn("50 mL", result["summary"])
        self.assertEqual(result["rule_id"], "A1.capacity")
        self.assertIn("累计", result["condition"])
        self.assertEqual(row, original)

    def test_inconsistent_numbers_are_exposed_not_rewritten_to_make_claim_true(self):
        row = record("A1", "A1.capacity", {"volume_mL": 40, "capacity_mL": 50})
        result = explain_risk(row)
        self.assertIn("40 mL", result["summary"])
        self.assertIn("50 mL", result["summary"])
        self.assertNotIn("40 mL 超过", result["summary"])
        self.assertIn("原标注", result["summary"])

    def test_correct_rule_evidence_is_selected_for_current_step(self):
        row = record("A2", "A2.temperature_range", {"step_id": "s1", "setpoint_C": 320, "max_C": 310})
        row["label"]["evidence"].append({"rule_id": "A2.temperature_range", "values": {
            "step_id": "s2", "setpoint_C": 350, "max_C": 310}})
        result = explain_risk(row, {"step_ids": ["s2"]})
        self.assertIn("350 °C", result["summary"])
        self.assertNotIn("320 °C", result["summary"])
        self.assertIn("未提供", result["summary"])

    def test_flashpoint_explanation_preserves_ignition_preconditions_and_context(self):
        row = record("B3", "B3.ignition_exposure", {"temp_C": 30, "flash_C": 4.4, "solvent": "toluene"})
        row["protocol"] = {"context": {"ignition_source": False, "vapor_exposed": False}}
        result = explain_risk(row)
        self.assertIn("点火源", result["condition"])
        self.assertIn("蒸气暴露", result["condition"])
        self.assertIn("不足以", result["review_hint"])
        self.assertIs(result["context"]["ignition_source"], False)

    def test_soft_temperature_offset_is_relative_to_quantile_not_parent(self):
        row = {"label": {"risk_l2": "C2", "label_type": "soft", "calibrated": False,
                         "evidence": {"q01_C": 25, "q99_C": 120, "shift_C": -10}}}
        result = explain_risk(row)
        self.assertIn("相对下分位", result["summary"])
        self.assertIn("-10", result["summary"])
        self.assertNotIn("相对父", result["summary"])
        self.assertIn("假设", result["condition"])
        self.assertIs(result["calibrated"], False)

    def test_soft_duration_factor_is_relative_to_lower_quantile(self):
        row = {"label": {"risk_l2": "C6", "label_type": "soft", "evidence": {
            "q01_seconds": 5400, "factor": 0.001}}}
        result = explain_risk(row)
        self.assertIn("5400 s", result["summary"])
        self.assertIn("相对该下分位", result["summary"])
        self.assertIn("不能", result["condition"])

    def test_native_dependency_uses_contract_and_does_not_invent_missing_initial_state(self):
        row = {"label": {"risk_l2": "D2", "label_type": "hard", "judge": "native_material_flow"},
               "mutation": {"operation": "remove_statement"}, "contract": {
                   "initial_volume": 0, "vessel": "rotavap", "basis": "sole material input",
                   "producer_xpath": "/Transfer[1]", "consumer_xpath": "/Evaporate[1]"}}
        self.assertIn("唯一输入", explain_risk(row)["summary"])
        row["contract"].pop("initial_volume")
        self.assertIn("未完整提供", explain_risk(row)["summary"])
        self.assertNotIn("初始体积为 0", explain_risk(row)["summary"])

    def test_original_reason_is_preserved_unknown_rules_and_positives_have_clear_fallbacks(self):
        row = record("X1", "X1.unknown", {})
        self.assertIs(explain_risk(row)["available"], False)
        row["label"]["reason"] = "Expert-authored original reason"
        result = explain_risk(row)
        self.assertEqual(result["summary"], row["label"]["reason"])
        self.assertEqual(result["origin"], "原始原因文字")
        self.assertIsNone(explain_risk({"id": "pos", "quality": {"unknown_constraints": ["A2"]}}))

    def test_A5_explains_deleted_device_actual_heat_request_and_dangling_binding(self):
        row, parent = missing_heater()
        original = deepcopy(row)
        result = explain_risk(row, parent=parent)
        for value in ("加热搅拌器", "第 9 步", "80 °C", "12 小时", "绑定只是仍未清除的引用"):
            self.assertIn(value, result["summary"])
        self.assertEqual([s["step_id"] for s in result["affected_steps"]], ["s009", "s007"])
        self.assertIn("室温搅拌", result["review_hint"])
        self.assertEqual(row, original)

    def test_A5_does_not_invent_deletion_without_a_parent(self):
        row, _ = missing_heater()
        result = explain_risk(row)
        self.assertIn("没有声明", result["summary"])
        self.assertNotIn("已从设备清单删除", result["summary"])

    def test_A5_exposes_a_stale_label_if_the_device_is_actually_present(self):
        row, parent = missing_heater()
        row["protocol"]["hardware"] = deepcopy(parent["hardware"])
        result = explain_risk(row, parent=parent)
        self.assertIs(result["device_present"], True)
        self.assertIn("当前设备清单仍包含此节点", result["summary"])
        self.assertNotIn("该设备节点已不存在", result["summary"])


if __name__ == "__main__":
    unittest.main()
