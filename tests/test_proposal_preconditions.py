"""Exercise source-operator paths with explicit simulated fixtures, never real labels."""
import copy

import pytest

from tests.chemistry_fixtures import reference
from protocol_risk.mutation_rules import make_negative, proposals
from protocol_risk.symbolic import evaluate
from protocol_risk.xdl import export_xdl


@pytest.mark.parametrize("risk", ["A1", "A2", "A3", "A4", "B2", "B3", "B5", "D2"])
def test_each_conditional_operator_can_make_one_and_only_one_target_fault(risk):
    parent = reference("A1" if risk == "A4" else risk, 0)
    if risk == "A4":
        parent["hardware"]["nodes"]["reactor"]["wetted_materials"] = ["borosilicate_glass"]
    if risk == "D2":
        parent["constraints"]["required_steps"][0]["source_url"] = "https://example.test/fixture-required-step"
    original = copy.deepcopy(parent)
    accepted = [make_negative(parent, child, proposed, evidence, origin="authored_control")
                for proposed, child, evidence in proposals(parent, {}) if proposed == risk]
    assert any(n is not None and evaluate(n["protocol"]).risks == [risk] for n in accepted)
    assert parent == original and evaluate(parent).risks == []


def test_no_verified_equipment_means_no_hardware_limit_mutations():
    parent = reference("A1", 0)
    for node in parent["hardware"]["nodes"].values():
        node["verified"] = False
    assert not {"A1", "A2", "A3", "A4"}.intersection(risk for risk, _, _ in proposals(parent, {}))


def test_temperature_operator_can_inject_a_device_request_without_inventing_sample_mapping():
    parent = reference("A2", 0)
    parent["hardware"]["nodes"]["heater"]["sample_temperature_validated"] = False
    candidates = [child for risk, child, _ in proposals(parent, {}) if risk == "A2"]
    assert candidates and all(c["steps"][-1]["temp_C"] == parent["steps"][-1]["temp_C"] for c in candidates)
    assert all("controller_setpoint_C" in c["steps"][-1] for c in candidates)
    parent["steps"][-1]["controller_setpoint_C"] = 25
    candidates = [child for risk, child, _ in proposals(parent, {}) if risk == "A2"]
    assert candidates and all(c["steps"][-1]["temp_C"] == parent["steps"][-1]["temp_C"] for c in candidates)
    assert "Analysis controller setpoint" in export_xdl(candidates[0])


def test_sourced_equipment_can_support_provisional_examples_without_human_claims():
    parent = reference("A1", 0)
    node = parent["hardware"]["nodes"]["reactor"]
    node.update(verified=False, verification={"status": "source_reviewed", "human_verified": False},
                source_url="https://example.test/fixture-datasheet")
    candidates = [(child, evidence) for risk, child, evidence in proposals(parent, {}) if risk == "A1"]
    sample = make_negative(parent, candidates[0][0], "A1", candidates[0][1], origin="authored_control")
    assert sample and "source_reviewed_provisional" in sample["audit"]["hardware_evidence_levels"]
    assert sample["benchmark_eligible"] is False


@pytest.mark.parametrize("risk", ["B2", "B3", "B5", "D2"])
def test_risk_specific_missing_evidence_is_not_filled_in(risk):
    parent = reference(risk, 0)
    if risk == "B2":
        parent["context"]["pure_solvent"] = False
    elif risk == "B3":
        parent["context"]["vapor_exposed"] = False
    elif risk == "B5":
        parent["reagents"][1]["mass_fraction"] = 0.1
    assert risk not in {name for name, _, _ in proposals(parent, {})}


@pytest.mark.parametrize("limit", ["ambient", True, float("inf"), float("nan")])
def test_non_numeric_or_nonfinite_verified_limits_abstain(limit):
    parent = reference("A3", 0)
    parent["hardware"]["nodes"]["heater"]["params"]["rpm_max"] = limit
    assert "A3" not in {risk for risk, _, _ in proposals(parent, {})}
    assert any(u["rule"] == "A3" for u in evaluate(parent).unknowns)
