"""Canonical concepts evolve separately from expression mappings and execution."""
import copy

import pytest

from mosaic.canonical import finalize_negative, finalize_protocol
from mosaic.evidence import SourceSpan
from mosaic.registry import Registry
from protocol_risk.normalization import normalize_protocol, semantic_contract_hash


TEXT = "centrifuge the sample for 30 seconds"


def witness(word="centrifuge"):
    return {"id": "source", "steps": [{"id": "s1", "op": word,
            "parameters": {"duration_s": {"value": 30, "unit": "s", "evidence": TEXT}},
            "meta": {"evidence": TEXT}}]}


def change():
    return {"action": "admit_canonical_operation", "operation_id": "op.centrifuge",
            "counterexample": "Centrifugal separation is not stirring or gravity settling.",
            "considered_operations": ["op.mix", "op.separate"],
            "contract": {"name": "Centrifuge", "kind": "action", "domain": "general",
                         "parameters": {"duration_s": {"type": "quantity", "required": False}},
                         "preconditions": ["Sample and centrifuge configuration are explicit or unknown."],
                         "effects": ["Applies centrifugal force; separated fractions remain unspecified."],
                         "capabilities": ["centrifugation"]},
            "mapping": {"id": "alias.centrifuge", "expressions": ["centrifuge"],
                        "operation_id": "op.centrifuge", "parameter_map": {}},
            "witnesses": [witness()], "evidence": [SourceSpan.locate("s", TEXT, TEXT).to_dict()]}


def apply(registry, proposal):
    return registry.evolve([proposal], expected_revision=registry.revision, sources={"s": TEXT})


def test_new_semantics_are_admitted_as_a_declarative_concept_with_mapping():
    original = Registry()
    updated = apply(original, change())
    assert "op.centrifuge" not in original.snapshot["canonical_operations"]
    assert updated.snapshot["canonical_operations"]["op.centrifuge"]["execution_supported"] is False
    normalized = normalize_protocol(witness(), vocabulary={"operations": updated.snapshot["canonical_operations"],
                                                         "mappings": updated.snapshot["operation_mappings"]})
    assert normalized["steps"][0]["op"] == "Centrifuge"
    assert not normalized["normalization"]["unresolved"]


def test_adding_an_expression_never_creates_another_operation_contract():
    registry = apply(Registry(), change())
    before = semantic_contract_hash(registry.snapshot["canonical_operations"]["op.centrifuge"])
    proposal = {"action": "map_canonical_expression", "mapping": {
        "id": "alias.spin_sample", "expressions": ["spin sample"], "operation_id": "op.centrifuge"},
        "witnesses": [witness("spin sample")], "evidence": [SourceSpan.locate("s", TEXT, TEXT).to_dict()]}
    updated = apply(registry, proposal)
    assert len(updated.snapshot["canonical_operations"]) == len(registry.snapshot["canonical_operations"])
    assert semantic_contract_hash(updated.snapshot["canonical_operations"]["op.centrifuge"]) == before
    assert updated.snapshot["canonical_mapping_revision"] != registry.snapshot["canonical_mapping_revision"]


@pytest.mark.parametrize("field", ["counterexample", "considered_operations", "witnesses", "mapping"])
def test_incomplete_new_semantics_are_rejected_without_partial_registry_changes(field):
    registry = Registry()
    before = registry.revision
    proposal = change()
    proposal.pop(field)
    with pytest.raises(ValueError):
        apply(registry, proposal)
    assert registry.revision == before


def test_a_familiar_display_name_does_not_justify_a_new_concept():
    proposal = change()
    proposal["contract"]["name"] = "Mix"
    with pytest.raises(ValueError, match="existing canonical ID"):
        apply(Registry(), proposal)


def test_new_concepts_keep_pinned_mappings_when_children_are_finalized():
    registry = apply(Registry(), change())
    vocabulary = {"operations": registry.snapshot["canonical_operations"], "mappings": registry.snapshot["operation_mappings"]}
    parent = finalize_protocol(witness(), vocabulary=vocabulary)
    source_child = copy.deepcopy(witness())
    source_child["steps"][0]["parameters"]["duration_s"]["value"] = -10
    sample = finalize_negative({"protocol": source_child}, parent)
    assert sample["protocol"]["steps"][0]["op"] == "Centrifuge"
    assert sample["protocol"]["steps"][0]["parameters"]["duration_s"]["value"] == -10
