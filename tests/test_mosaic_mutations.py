import copy

import pytest

from mosaic.mutations import assess_intervention, fault_instances, generate
from tests.chemistry_fixtures import reference
from protocol_risk.symbolic import evaluate


def test_two_same_class_amount_faults_are_not_one_semantic_intervention():
    parent = reference("A1", 0)
    parent["steps"].insert(1, {"id": "second_liquid", "op": "Add", "vessel": "reactor", "reagent": "r1", "amount": {"value": 1, "unit": "mL"}})
    child = copy.deepcopy(parent)
    child["steps"][0]["amount"]["value"] = 1000
    child["steps"][1]["amount"]["value"] = 1000
    assert evaluate(child).risks == ["A1"]
    with pytest.raises(ValueError, match="Multiple steps"):
        assess_intervention(parent, child)


def test_many_reports_from_one_missing_controller_are_one_fault_instance():
    parent = reference("A5", 0)
    child = copy.deepcopy(parent)
    del child["hardware"]["nodes"]["heater"]
    assert assess_intervention(parent, child)["count"] == 1
    assert len(fault_instances(child, evaluate(child).violations)) == 1


def test_equipment_rating_edit_cannot_masquerade_as_one_operational_fault():
    parent = reference("A1", 0)
    child = copy.deepcopy(parent)
    child["hardware"]["nodes"]["reactor"]["params"]["capacity_mL"] = 1
    with pytest.raises(ValueError, match="specifications"):
        assess_intervention(parent, child)


def test_distinct_capacity_and_configuration_mechanisms_survive_selection():
    parents = [reference("A1", i) for i in range(3)]
    output, report = generate(parents, [], per_risk=6)
    mechanisms = {s["mutation"]["mechanism_id"] for s in output}
    assert {"A1.single_add_overfill", "A1.active_fill_fraction", "A5.missing_controller",
            "A5.incompatible_bound_capability", "A5.unresolved_binding", "D4.nonpositive_quantity",
            "D4.incompatible_dimension"} <= mechanisms
    assert all(s["mutation"]["semantic_fault_count_verified"] for s in output)
    assert all(s["origin"] == "authored_control" for s in output)


def test_boiling_risk_has_temperature_and_closure_interventions():
    opened = reference("B1", 0)
    sealed = reference("B1", 1)
    sealed["context"]["pressure_control"] = "SEALED"
    sealed["steps"][-1]["temp_C"] = 110
    samples, _ = generate([opened, sealed], [], per_risk=10)
    mechanisms = {s["mutation"]["mechanism_id"] for s in samples if s["label"]["risk_l2"] == "B1"}
    assert mechanisms == {"B1.overheat_open_liquid", "B1.open_hot_closed_vessel"}


def test_negative_wrapper_carries_its_own_export_for_standalone_files():
    from protocol_risk.xdl import export_xdl
    parent = reference("A1", 0)
    parent["xdl"] = export_xdl(parent)
    samples, _ = generate([parent], [], per_risk=2)
    for sample in samples:
        assert sample["xdl"] == sample["protocol"]["xdl"] == export_xdl(sample["protocol"])


def test_bad_model_pointer_is_rejected_without_losing_following_valid_proposal():
    from mosaic.mutations import model_proposals
    parent = reference("A1", 0)
    class Runner:
        def model_call(self, role, system, payload):
            assert set(payload) == {"steps", "reagents", "hardware", "context"}
            return {"data": {"proposals": [None, {"patch": [None]},
                {"risk": "C2", "patch": [{"op": "replace", "path": "/steps/0/params/temp_C", "value": 100}]},
                {"risk": "A1", "patch": [{"op": "replace", "path": "/steps/0/amount/value", "value": 2000}]}]}}
    results = list(model_proposals(parent, Runner()))
    assert len(results) == 1 and results[0][0] == "A1"
    assert results[0][1]["steps"][0]["amount"]["value"] == 2000


def test_malformed_model_quantity_does_not_abort_programmatic_generation():
    parent = reference("A1", 0)
    class Runner:
        def model_call(self, role, system, payload):
            return {"data": {"proposals": [{"risk": "D4", "patch": [
                {"op": "replace", "path": "/steps/0/amount/value", "value": {"invalid": "object"}}]}]}}
    samples, report = generate([parent], [], runner=Runner(), llm_limit=1, per_risk=2)
    assert samples
    assert report["rejected"].get("Step intervention must change one supported operational field", 0) >= 1
    assert all(not isinstance(step.get("amount", {}).get("value"), dict)
               for sample in samples for step in sample["protocol"]["steps"])
