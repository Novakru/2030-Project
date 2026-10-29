"""Representation admission, source fidelity and lossless extended XDL."""
import copy
import json

import pytest
from lxml import etree

from mosaic.protocol.extensions import (
    MISSING_MARKERS, PROFILE, definition_semantic_hash,
    normalize_definition,
    validate_extension_step,
)
from mosaic.protocol.xdl import canonical_hash, export_xdl, validate_xdl


SOURCE = "Wash the organic phase with 2000 uL water. Stir overnight."


def definition():
    return {
        "description": "Wash a retained phase with the explicitly named wash liquid.",
        "parameters": {
            "solvent": {"type": "string", "required": True},
            "amount": {"type": "quantity", "required": True, "unit": "mL", "dimension": "volume"},
        },
        "effects": ["phase_washed"], "hardware_roles": ["phase_contact"],
    }


def step():
    return {"id": "s001", "op": "Wash", "vessel": "reactor", "parameters": {
        "solvent": {"value": "water", "evidence": SOURCE.split(". ")[0] + "."},
        "amount": {"value": 2.0, "unit": "mL", "evidence": "2000 uL water"}},
        "meta": {"evidence": SOURCE.split(". ")[0] + ".", "stage": "workup"}}


def protocol():
    return {
        "xdl_profile": PROFILE, "source_text": SOURCE,
        "operation_definitions": {"Wash": normalize_definition("Wash", definition())},
        "steps": [step(), {"id": "s002", "op": "Stir", "vessel": "reactor",
            "meta": {"evidence": "Stir overnight.", "stage": "reaction"},
            "missing_parameters": {"duration_s": {"status": "qualitative", "marker": "__QUALITATIVE__",
                "evidence": "Stir overnight.", "raw": "overnight"}}}],
        "hardware": {"nodes": {"reactor": {"category": "vessel", "verified": False,
            "params": {}, "source_evidence": []}}, "edges": []},
        "reagents": [{"id": "r001", "name": "water", "smiles": None}],
        "context": {},
    }


def test_automatic_contract_admission_is_separate_from_execution():
    result = normalize_definition("Wash", definition())
    assert result["representation_status"] == "admitted"
    assert result["execution_supported"] is False
    assert result["domain"] == "chemistry"
    assert result["semantic_sha256"] == definition_semantic_hash("Wash", result)
    validate_extension_step(step(), result, SOURCE)


def test_semantic_contract_hash_ignores_evidence_but_retains_meaning():
    original = normalize_definition("Wash", definition())
    observed = copy.deepcopy(original)
    observed.update(evidence=[{"quote": "a new occurrence"}], origins=["record2"], status="reviewed")
    assert normalize_definition("Wash", observed)["semantic_sha256"] == original["semantic_sha256"]
    changed = definition()
    changed["effects"] = ["product_phase_removed"]
    assert definition_semantic_hash("Wash", changed) != original["semantic_sha256"]
    changed = definition()
    changed["description"] = "Dry a phase, rather than washing it."
    assert definition_semantic_hash("Wash", changed) != original["semantic_sha256"]


@pytest.mark.parametrize("change", [
    {"execution_supported": True}, {"code": "import os"}, {"name": "Other"},
    {"semantic_sha256": "fake"}, {"effects": "phase_washed"}, {"domain": ""},
    {"parameters": {"amount": {"type": "object", "required": True}}},
    {"parameters": {"amount": {"type": "number"}}},
    {"parameters": {"amount": {"type": "string", "required": True, "unit": "mL"}}},
])
def test_invalid_contracts_cannot_be_admitted(change):
    proposed = definition()
    proposed.update(change)
    with pytest.raises(ValueError):
        normalize_definition("Wash", proposed)


def test_core_meanings_cannot_be_overridden_but_analysis_only_sonication_can_be_extended():
    with pytest.raises(ValueError, match="overwrite"):
        normalize_definition("Add", definition())
    assert normalize_definition("Sonicate", definition())["name"] == "Sonicate"


@pytest.mark.parametrize("item", [
    {"value": True, "unit": "mL", "evidence": "2000 uL water"},
    {"value": float("nan"), "unit": "mL", "evidence": "2000 uL water"},
    {"value": {"value": 2}, "unit": "mL", "evidence": "2000 uL water"},
    {"value": 2, "unit": "mg", "evidence": "2000 uL water"},
    {"value": 2000, "unit": "mL", "evidence": "2000 uL water"},
    {"value": 2, "unit": "mL", "evidence": "invented water addition"},
])
def test_wrong_quantities_types_units_and_quotes_are_rejected(item):
    candidate = step()
    candidate["parameters"]["amount"] = item
    with pytest.raises(ValueError):
        validate_extension_step(candidate, definition(), SOURCE)


def test_literal_string_value_and_required_parameters_are_checked():
    candidate = step()
    candidate["parameters"]["solvent"]["value"] = "toluene"
    with pytest.raises(ValueError, match="literally"):
        validate_extension_step(candidate, definition(), SOURCE)
    del candidate["parameters"]["solvent"]
    with pytest.raises(ValueError, match="Required"):
        validate_extension_step(candidate, definition(), SOURCE)


def test_parameter_evidence_cannot_borrow_another_steps_quantity():
    candidate = step()
    candidate["parameters"]["amount"] = {"value": 3, "unit": "mL", "evidence": "3 mL water"}
    with pytest.raises(ValueError, match="contained"):
        validate_extension_step(candidate, definition(), SOURCE + " Later add 3 mL water.")


@pytest.mark.parametrize("status,raw", [("not_reported", None), ("qualitative", "a little"), ("ambiguous", "some")])
def test_explicit_missing_markers_preserve_source_wording(status, raw):
    text = "Wash with " + (raw + " " if raw else "") + "water."
    candidate = step()
    candidate["meta"]["evidence"] = text
    candidate["parameters"]["solvent"]["evidence"] = text
    candidate["parameters"]["amount"] = {"status": status, "marker": MISSING_MARKERS[status], "evidence": text, "raw": raw}
    validate_extension_step(candidate, definition(), text)
    assert "value" not in candidate["parameters"]["amount"]


def test_missing_marker_cannot_hide_an_explicit_amount():
    candidate = step()
    candidate["parameters"]["amount"] = {"status": "not_reported", "marker": "__NOT_REPORTED__",
        "evidence": candidate["meta"]["evidence"], "raw": None}
    with pytest.raises(ValueError, match="source-reported"):
        validate_extension_step(candidate, definition(), SOURCE)


@pytest.mark.parametrize("marker", [
    {"status": "not_reported", "marker": "__QUALITATIVE__", "evidence": "water"},
    {"status": "qualitative", "marker": "__QUALITATIVE__", "evidence": "water", "raw": None},
    {"status": "ambiguous", "marker": "__AMBIGUOUS__", "evidence": "water", "raw": "unquoted"},
    {"status": "not_reported", "marker": "__NOT_REPORTED__", "evidence": "water", "value": 2},
])
def test_malformed_markers_are_rejected(marker):
    candidate = step()
    candidate["parameters"]["amount"] = marker
    with pytest.raises(ValueError):
        validate_extension_step(candidate, definition(), SOURCE)


def test_bool_requires_an_explicit_boolean_instead_of_inventing_a_condition():
    contract = {"description": "Record the explicit experimental toggle.", "effects": ["toggle_recorded"],
        "parameters": {"enabled": {"type": "boolean", "required": True}}}
    candidate = {"op": "Toggle", "evidence": "enabled true", "parameters": {
        "enabled": {"value": True, "evidence": "enabled true"}}}
    validate_extension_step(candidate, contract, "enabled true")
    candidate["evidence"] = "under vacuum"
    candidate["parameters"]["enabled"]["evidence"] = "under vacuum"
    with pytest.raises(ValueError, match="Boolean"):
        validate_extension_step(candidate, contract, "under vacuum")


def test_extended_canonical_hash_ignores_evidence_and_retains_unknowns_and_contracts():
    original = protocol()
    same = copy.deepcopy(original)
    same["steps"][0]["parameters"]["amount"]["evidence"] = "another source occurrence"
    same["steps"][1]["missing_parameters"]["duration_s"]["evidence"] = "another overnight quote"
    same["operation_definitions"]["Wash"]["origins"] = ["another-record"]
    assert canonical_hash(same) == canonical_hash(original)
    same["operation_definitions"]["Wash"]["description"] += " With a different semantic contract."
    assert canonical_hash(same) != canonical_hash(original)
    same = copy.deepcopy(original)
    same["steps"][1]["missing_parameters"]["duration_s"].update(status="not_reported", marker="__NOT_REPORTED__", raw=None)
    assert canonical_hash(same) != canonical_hash(original)
