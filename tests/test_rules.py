"""Independent boundaries, applicability checks, and all single-fault operators."""
import copy

import jsonpatch
import pytest
from hypothesis import given, strategies as st

from protocol_risk.controls import generate_controls, mutate, reference
from protocol_risk.io import load_library
from protocol_risk.perturb import SOFT
from protocol_risk.symbolic import evaluate

RISKS = list(load_library("risks.yaml")["risks"])


@pytest.mark.parametrize("risk", RISKS)
@pytest.mark.parametrize("variant", range(3))
def test_three_positive_and_three_mutated_examples_per_rule(risk, variant):
    parent = reference(risk, variant)
    original = copy.deepcopy(parent)
    assert evaluate(parent).risks == []
    child = mutate(parent, risk, variant)
    assert parent == original
    assert evaluate(child).risks == ([] if risk in SOFT else [risk])


def test_every_patch_replays_exactly_and_probabilities_are_not_fabricated():
    parents, negatives = generate_controls(12)
    mapping = {p["id"]: p for p in parents}
    assert len(negatives) == 240
    for sample in negatives:
        reconstructed = jsonpatch.apply_patch(copy.deepcopy(mapping[sample["parent_id"]]), sample["diff"])
        assert reconstructed == sample["protocol"]
        assert sample["mutation"]["semantic_fault_count"] == 1
        if sample["label"]["label_type"] == "soft":
            assert sample["label"]["feasible"] is None
            assert sample["label"]["p_infeasible"] is None


@given(st.floats(min_value=50, max_value=1500, allow_nan=False, allow_infinity=False))
def test_stirring_rate_within_inclusive_limits_is_valid(rpm):
    protocol = reference("A3", 0)
    protocol["steps"][-1]["rpm"] = rpm
    assert "A3" not in evaluate(protocol).risks


@pytest.mark.parametrize("rpm", [-1, 49, 1501, 2000])
def test_stirring_rate_outside_limits_is_invalid(rpm):
    protocol = reference("A3", 0)
    protocol["steps"][-1]["rpm"] = rpm
    assert evaluate(protocol).risks == ["A3"]


def test_unverified_hardware_does_not_give_hard_temperature_labels():
    protocol = mutate(reference("A2", 0), "A2", 0)
    protocol["hardware"]["nodes"]["heater"]["verified"] = False
    result = evaluate(protocol)
    assert "A2" not in result.risks
    assert any(x["rule"] == "A2" for x in result.unknowns)


def test_hotplate_surface_limit_is_not_a_liquid_temperature_limit():
    protocol = mutate(reference("A2", 0), "A2", 0)
    protocol["hardware"]["nodes"]["heater"]["sample_temperature_validated"] = False
    assert "A2" not in evaluate(protocol).risks


def test_freezing_check_abstains_for_solutions_and_mixtures():
    protocol = mutate(reference("B2", 0), "B2", 0)
    protocol["context"]["pure_solvent"] = False
    assert "B2" not in evaluate(protocol).risks
    protocol["context"]["pure_solvent"] = True
    protocol["reagents"].append({"id": "ethanol", "name": "ethanol", "smiles": "CCO", "role": "SOLVENT"})
    protocol["steps"].insert(1, {"id": "e", "op": "Add", "vessel": "reactor", "reagent": "ethanol", "amount": {"value": 2, "unit": "mL"}})
    assert "B2" not in evaluate(protocol).risks


def test_flashpoint_alone_is_not_an_ignition_event():
    protocol = reference("B3", 0)
    assert evaluate(protocol).risks == []
    protocol["context"]["ignition_source"] = True
    assert evaluate(protocol).risks == ["B3"]
    protocol["context"]["vapor_exposed"] = False
    assert evaluate(protocol).risks == []


def test_dilute_acid_is_outside_concentrated_acid_order_rule():
    protocol = mutate(reference("B5", 0), "B5", 0)
    protocol["reagents"][1]["mass_fraction"] = 0.1
    assert "B5" not in evaluate(protocol).risks


def test_good_references_do_not_trigger_missing_hardware_or_units():
    for risk in ("A5", "D3", "D4"):
        assert evaluate(reference(risk, 0)).risks == []


def test_receiving_vessel_capacity_is_checked_after_transfer():
    protocol = reference("D1", 0)
    protocol["hardware"]["nodes"]["product"]["params"]["capacity_mL"] = 2
    assert evaluate(protocol).risks == ["A1"]


def test_unit_error_does_not_also_trigger_capacity_error():
    assert evaluate(mutate(reference("D4", 0), "D4", 0)).risks == ["D4"]
