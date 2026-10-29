"""Public XML, semantic identity and fault replay through canonical vocabulary."""
import copy

import jsonpatch
import pytest

from mosaic.canonical import finalize_protocol
from mosaic.mutations import assess_intervention
from protocol_risk.canonical_xdl import read_canonical_xdl
from protocol_risk.io import load_library
from protocol_risk.mutation_rules import make_negative
from protocol_risk.normalization import analysis_protocol, normalize_protocol, semantic_contract_hash
from protocol_risk.symbolic import evaluate
from protocol_risk.xdl import canonical_hash, export_xdl, validate_xdl


def example():
    return {"id": "pos_example", "source": {"db": "TEXT"}, "reagents": [{"id": "r1", "name": "water"}],
            "steps": [{"id": "s1", "op": "Add", "reagent": "r1", "vessel": "v1",
                       "amount": {"value": 1, "unit": "mL"}, "meta": {"evidence": "add 1 mL water"}}],
            "hardware": {"nodes": {"v1": {"category": "vessel", "apparatus_kind": "microreactor",
                                           "verified": True, "params": {"capacity_mL": 2}}}, "edges": [], "bindings": {}},
            "quality": {"tier": "silver"}, "context": {}, "xdl_profile": "mosaic-xdl/1"}


def test_actual_catalog_covers_every_exact_legacy_contract():
    operations = load_library("atomic_operations.yaml")["operations"]
    mappings = load_library("operation_mappings.yaml")
    assert len(mappings["migrations"]) == 204
    assert len(mappings["contracts"]) == 547
    assert {entry["classification"] for entry in mappings["contracts"].values()} == {
        "synonym", "parameter_variant", "composition", "observation", "independent"}
    for contract in mappings["contracts"].values():
        assert contract["operation_id"] in operations
        for member in contract.get("composition", {}).get("steps", []):
            assert member["operation_id"] in operations


def test_canonical_xml_preserves_evidence_equipment_and_mappings_after_json_roundtrip():
    parent = finalize_protocol(example())
    import json
    serialized = json.loads(json.dumps(parent, sort_keys=True))
    assert export_xdl(serialized) == parent["xdl"]
    decoded = read_canonical_xdl(parent["xdl"])
    for key in ("steps", "hardware", "normalization", "operation_definitions"):
        assert decoded[key] == parent[key]
    assert validate_xdl(parent["xdl"])
    assert parent["hardware"]["nodes"]["v1"]["subtype_id"] == "equipment.microreactor"


@pytest.mark.parametrize("word", ["Add", "add", "charge", "加入", "投料"])
def test_aliases_produce_same_semantic_identity(word):
    source = example()
    source["steps"][0]["op"] = word
    assert canonical_hash(finalize_protocol(source)) == canonical_hash(finalize_protocol(example()))


def test_display_rename_and_new_alias_do_not_version_contract():
    original = finalize_protocol(example())
    renamed = copy.deepcopy(original)
    contract = renamed["operation_definitions"].pop("Add")
    before = semantic_contract_hash(contract)
    contract["name"] = "IntroduceMaterial"
    contract["aliases"] = ["an extra expression"]
    renamed["operation_definitions"]["IntroduceMaterial"] = contract
    renamed["steps"][0]["op"] = "IntroduceMaterial"
    assert semantic_contract_hash(contract) == before
    assert canonical_hash(renamed) == canonical_hash(original)
    assert validate_xdl(export_xdl(renamed))


def test_intentional_negative_keeps_error_and_replays_against_canonical_parent():
    parent = finalize_protocol(example())
    child = copy.deepcopy(parent)
    child["steps"][0]["amount"]["value"] = 3
    sample = make_negative(parent, child, "A1", {"precondition": "known capacity"})
    assert sample is not None
    assert sample["protocol"]["steps"][0]["amount"]["value"] == 3
    assert evaluate(sample["protocol"]).risks == ["A1"]
    assert assess_intervention(parent, sample["protocol"])["field"] == "/amount/value"
    assert jsonpatch.apply_patch(parent, sample["diff"]) == sample["protocol"]
    assert validate_xdl(sample["xdl"])


def test_unknown_contract_reusing_known_name_is_not_silently_merged():
    source = example()
    source["steps"][0]["op"] = "ChargeMaterial"
    source["operation_definitions"] = {"ChargeMaterial": {"semantic_sha256": "not-reviewed"}}
    normalized = normalize_protocol(source)
    assert normalized["steps"][0]["op"] == "Unresolved"
    assert normalized["normalization"]["unresolved"]
    with pytest.raises(ValueError, match="library evolution"):
        finalize_protocol(source)


def test_changed_mixing_method_does_not_reuse_stirring_equipment_checks():
    source = example()
    source["steps"] = [{"id": "mix", "op": "Stir", "vessel": "v1", "duration_s": 30}]
    normalized = normalize_protocol(source)
    normalized["steps"][0]["parameters"]["method"]["value"] = "vortex"
    assert analysis_protocol(normalized)["steps"][0]["op"] == "Mix"
    assert any(item["rule"] == "operation_effects" for item in evaluate(normalized).unknowns)


def test_quantity_units_normalize_and_inverse_reads_current_value():
    source = example()
    source["steps"] = [{"id": "mix", "op": "Mix", "parameters": {
        "duration_s": {"value": 2, "unit": "min", "evidence": "mix for 2 min"}}}]
    normalized = normalize_protocol(source)
    assert normalized["steps"][0]["parameters"]["duration_s"]["value"] == 120
    assert normalized["steps"][0]["parameters"]["duration_s"]["unit"] == "s"
    assert analysis_protocol(normalized) == source
    normalized["steps"][0]["parameters"]["duration_s"]["value"] = -180
    assert analysis_protocol(normalized)["steps"][0]["parameters"]["duration_s"]["value"] == -3


def test_canonical_xml_rejects_dtd_and_contract_tampering():
    parent = finalize_protocol(example())
    with pytest.raises(ValueError):
        validate_xdl('<!DOCTYPE Synthesis [<!ENTITY x "unsafe">]>' + parent["xdl"])
    with pytest.raises(ValueError, match="modified canonical contract"):
        validate_xdl(parent["xdl"].replace('semantic_sha256="', 'semantic_sha256="bad', 1))


def test_qualitative_conditions_and_temporal_relations_remain_semantically_distinct():
    source = example()
    source["steps"] = [{"id": "s1", "op": "HeatChill", "temp_C": 70, "stir": True,
                        "missing_parameters": {"duration_s": {"status": "qualitative", "marker": "__QUALITATIVE__",
                                                             "raw": "overnight", "evidence": "overnight"}}}]
    original = finalize_protocol(source)
    changed = copy.deepcopy(original)
    changed["steps"][0]["missing_parameters"]["duration_s"]["raw"] = "several days"
    assert canonical_hash(changed) != canonical_hash(original)
    changed = copy.deepcopy(original)
    changed["temporal_relations"][0]["relation"] = "before"
    assert canonical_hash(changed) != canonical_hash(original)
