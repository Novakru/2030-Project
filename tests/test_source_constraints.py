import copy

import pytest
from lxml import etree

from protocol_risk.validation import prepare_protocol
from protocol_risk.yields import target_yield


def minimal_source_and_extraction(temperature=30):
    text = "Add 1 mL water. Heat at 20 C for 1 hour. Evaporate with maximum temperature of 30 C."
    component = {"id": "r1", "name": "water", "smiles": "O", "role": "SOLVENT", "amount": {"value": 1, "unit": "mL"}}
    raw = {"id": "test", "procedure": text, "components": [component], "raw": {}, "atmosphere": {},
           "temperature": {"value": 20}, "duration": {"value": 3600}, "source": {"url": "https://example.invalid/source"}}
    raw["raw"] = {"outcomes": [{"products": [{"is_desired_product": True, "measurements": [
        {"type": "YIELD", "percentage": {"value": 80}}]}]}]}
    raw["yield_percent"], raw["yield_evidence"] = target_yield(raw["raw"])
    protocol = {"id": "p", "source": {"db": "TEST"}, "reagents": [component], "context": {},
                "extraction": {"method": "llm_evidence_constrained", "unresolved": [], "unmapped_actions": []},
                "steps": [{"id": "s1", "op": "Add", "reagent": "r1", "vessel": "reactor", "amount": component["amount"],
                           "meta": {"evidence": "Add 1 mL water.", "stage": "reaction"}},
                          {"id": "s2", "op": "HeatChill", "vessel": "reactor", "temp_C": 20, "duration_s": 3600,
                           "meta": {"evidence": "Heat at 20 C for 1 hour.", "stage": "reaction"}},
                          {"id": "s3", "op": "Evaporate", "vessel": "reactor", "temp_C": temperature,
                           "meta": {"evidence": "Evaporate with maximum temperature of 30 C.", "stage": "workup"}}]}
    return raw, protocol


def test_upper_bound_does_not_become_invented_temperature_setpoint():
    raw, protocol = minimal_source_and_extraction()
    result = prepare_protocol(protocol, raw)
    assert result["steps"][-1]["meta"]["temp_upper_bound_C"] == 30
    assert "temp_C" not in result["steps"][-1]
    xml = etree.fromstring(result["xdl"].encode())
    assert xml.find("Procedure/Evaporate").get("temp") is None


def test_wrong_upper_bound_number_cannot_bypass_numeric_grounding():
    raw, protocol = minimal_source_and_extraction(temperature=99)
    with pytest.raises(ValueError, match="not_grounded"):
        prepare_protocol(protocol, raw)


def test_database_outcomes_remain_reference_metadata_without_becoming_process_facts():
    raw, protocol = minimal_source_and_extraction()
    protocol["yield_percent"] = 99
    result = prepare_protocol(protocol, raw)
    assert "yield_percent" not in result
    assert result["reference_metadata"]["yield_percent"] == 80
    assert result["reference_metadata"]["yield_evidence"] == raw["yield_evidence"]
    raw["yield_percent"] = None
    assert prepare_protocol(protocol, raw)["reference_metadata"]["yield_percent"] is None


def test_cited_equipment_setup_is_retained_without_adding_a_new_primitive():
    raw, protocol = minimal_source_and_extraction()
    setup = "A 5.0 mL wheaton microreactor was charged. "
    raw["procedure"] = setup + raw["procedure"]
    protocol["extraction"]["unmapped_actions"] = [{"evidence": setup.strip(), "reason": "Vessel identity not in Add quote"}]
    # Preserve the exact source prefix, including punctuation expected by the classifier.
    protocol["extraction"]["unmapped_actions"][0]["evidence"] = setup.strip().rstrip(".")
    result = prepare_protocol(protocol, raw)
    assert result["hardware"]["nodes"]["reactor"]["apparatus_kind"] == "microreactor"
    assert not result["extraction"]["unmapped_actions"]
    assert result["context"]["source_context_events"][0]["kind"] == "source_vessel_setup"
    protocol["extraction"]["unmapped_actions"].append({"evidence": "Wash with water", "reason": "Missing physical action"})
    with pytest.raises(ValueError, match="not mapped"):
        prepare_protocol(protocol, raw)
