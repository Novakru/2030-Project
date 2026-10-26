import copy

import pytest
from lxml import etree

from protocol_risk.pipeline import _prepare
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
    result = _prepare(protocol, raw)
    assert result["steps"][-1]["meta"]["temp_upper_bound_C"] == 30
    assert "temp_C" not in result["steps"][-1]
    xml = etree.fromstring(result["xdl"].encode())
    assert xml.find("Procedure/Evaporate").get("temp") is None


def test_wrong_upper_bound_number_cannot_bypass_numeric_grounding():
    raw, protocol = minimal_source_and_extraction(temperature=99)
    with pytest.raises(ValueError, match="not_grounded"):
        _prepare(protocol, raw)


def test_cached_extraction_cannot_preserve_an_outdated_success_label():
    raw, protocol = minimal_source_and_extraction()
    protocol["yield_percent"] = 99
    result = _prepare(protocol, raw)
    assert result["yield_percent"] == 80
    assert result["yield_evidence"] == raw["yield_evidence"]
    raw["yield_percent"] = None
    with pytest.raises(ValueError, match="unambiguous target yield"):
        _prepare(protocol, raw)
