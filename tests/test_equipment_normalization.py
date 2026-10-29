"""Public-interface checks for canonical names and unmodified physical faults."""
import copy

import pytest

from mosaic.protocol.apparatus import source_fact_hash
from mosaic.protocol.equipment_normalization import (
    analysis_equipment, analysis_node, conditional_substitutes, normalize_equipment,
)
from mosaic.protocol.io import load_library


def hardware(node):
    return {"nodes": {"reactor": node}, "bindings": {"reactor": "reactor"}, "edges": []}


def source_microreactor(**changes):
    node = {"id": "source_micro", "category": "vessel", "apparatus_kind": "microreactor",
            "params": {"capacity_mL": 5}, "capacity_scope": "single_reaction_vessel",
            "wetted_materials": None, "ports": [], "model": None,
            "source_parameters": ["capacity_mL"], "verified": False,
            "verification": {"status": "source_reported", "human_verified": False},
            "source_evidence": [{"source_url": "urn:test:source", "raw_sha256": "a" * 64,
                                 "locator": "/procedure", "value": "5 mL microreactor"}]}
    node.update(changes)
    node["source_fact_sha256"] = source_fact_hash(node)
    return node


@pytest.mark.parametrize("alias", ["round-bottom flask", "round-bottomed flask", "RBF", "ＲＢＦ", "圆底烧瓶"])
def test_round_bottom_aliases_have_one_identity_with_original_spelling_separate(alias):
    node = normalize_equipment(hardware({"category": "vessel", "apparatus_kind": alias}))["nodes"]["reactor"]
    assert node["category_id"] == "equipment.reaction_container"
    assert node["subtype_id"] == "equipment.round_bottom_flask"
    assert node["apparatus_kind"] == "RoundBottomFlask"
    assert node["normalization"]["original_names"]["apparatus_kind"] == alias


@pytest.mark.parametrize("alias", ["microreactor", "micro-reactor", "微反应器", "微型反应器"])
def test_microreactor_aliases_preserve_subtype_and_never_infer_flow(alias):
    node = source_microreactor(apparatus_kind=alias)
    normalized = normalize_equipment(hardware(node))["nodes"]["reactor"]
    assert normalized["subtype_id"] == "equipment.microreactor"
    assert normalized["apparatus_kind"] == "Microreactor"
    assert normalized["params"] == {"capacity_mL": 5}
    assert not {"flow_mode", "flow_rate", "operating_mode", "capabilities"} & normalized.keys()
    assert analysis_node(normalized) == node


def test_mixing_subtypes_do_not_collapse_methods_or_invent_speed_ranges():
    magnetic = normalize_equipment(hardware({"kind": "磁力搅拌器", "params": {"rpm_max": None}}))["nodes"]["reactor"]
    vortex = normalize_equipment(hardware({"kind": "vortex mixer"}))["nodes"]["reactor"]
    assert magnetic["category_id"] == vortex["category_id"] == "equipment.mixing"
    assert magnetic["subtype_id"] != vortex["subtype_id"]
    assert magnetic["params"]["rpm_max"] is None
    assert "capabilities" not in magnetic


@pytest.mark.parametrize("node,reason", [
    ({"category": "vessel", "apparatus_kind": "mircoreactor"}, "unknown_subtype"),
    ({"category": "vessel", "apparatus_kind": "magnetic stirrer"}, "category_subtype_conflict"),
    ({"apparatus_kind": "vial", "type": "microreactor"}, "conflicting_subtypes"),
    ({"apparatus_kind": "column"}, "unknown_subtype"),
    ({"category": "vessel"}, "subtype_not_reported"),
])
def test_unknown_or_conflicting_context_does_not_force_a_match(node, reason):
    result = normalize_equipment(hardware(node))["nodes"]["reactor"]
    assert result["normalization"]["status"] == "unresolved"
    assert result["subtype_id"] is None
    assert any(value.startswith(reason) for value in result["normalization"]["reasons"])
    assert analysis_node(result) == node


def test_explicit_context_disambiguates_column():
    result = normalize_equipment(hardware({"category": "column", "apparatus_kind": "column"}))["nodes"]["reactor"]
    assert result["subtype_id"] == "equipment.chromatography_column"
    assert result["normalization"]["status"] == "resolved"


def test_unresolved_source_template_does_not_gain_a_specific_source_vessel_type():
    source = {"id": "chemputer_reactor_template", "category": "vessel",
              "binding_basis": "unresolved_source_apparatus", "params": {"capacity_mL": None}}
    result = normalize_equipment(hardware(source))["nodes"]["reactor"]
    assert result["subtype_id"] is None
    assert result["configuration"]["profile_id"] == "chemputer_reactor_template"
    assert analysis_node(result) == source


def test_known_profile_selects_subtype_without_copying_catalog_ratings():
    source = {"id": "ika_rct_basic_25008259", "category": "heater_stirrer", "params": {"rpm_max": None}}
    result = normalize_equipment(hardware(source))["nodes"]["reactor"]
    assert result["subtype_id"] == "equipment.hotplate_stirrer"
    assert result["params"] == {"rpm_max": None}
    assert result["configuration"] == {"profile_id": "ika_rct_basic_25008259"}
    assert analysis_node(result) == source


def test_model_and_manufacturer_are_configuration_not_new_equipment_concepts():
    source = {"apparatus_kind": "magnetic stirrer", "model": "vendor model 123", "manufacturer": "vendor"}
    result = normalize_equipment(hardware(source))["nodes"]["reactor"]
    assert result["configuration"] == {"model": "vendor model 123", "manufacturer": "vendor"}
    assert "model" not in result and "manufacturer" not in result
    assert result["subtype_id"] == "equipment.magnetic_stirrer"
    assert analysis_node(result) == source


def test_analysis_preserves_model_configuration_edits_and_deletions():
    source = {"apparatus_kind": "magnetic stirrer", "model": "old model", "manufacturer": "vendor"}
    normalized = normalize_equipment(hardware(source))["nodes"]["reactor"]
    normalized["configuration"]["model"] = "new model"
    del normalized["configuration"]["manufacturer"]
    result = analysis_node(normalized)
    assert result["model"] == "new model"
    assert "manufacturer" not in result


def test_normalization_is_idempotent_pure_and_exactly_reversible_for_legacy_hardware():
    original = hardware(source_microreactor())
    original["bindings"]["heater"] = "missing_heater"
    original["edges"] = [["pump", "missing_node"]]
    frozen = copy.deepcopy(original)
    normalized = normalize_equipment(original)
    assert original == frozen
    assert normalize_equipment(normalized) == normalized
    assert analysis_equipment(normalized) == original
    assert normalized["bindings"] == original["bindings"]
    assert normalized["edges"] == original["edges"]


def test_analysis_never_restores_edited_numbers_or_removed_nodes_and_bindings():
    normalized = normalize_equipment(hardware(source_microreactor()))
    normalized["nodes"]["reactor"]["params"]["capacity_mL"] = 1
    projected = analysis_equipment(normalized)
    assert projected["nodes"]["reactor"]["params"]["capacity_mL"] == 1
    assert source_fact_hash(projected["nodes"]["reactor"]) != projected["nodes"]["reactor"]["source_fact_sha256"]
    del normalized["nodes"]["reactor"]
    normalized["bindings"] = {"reactor": "wrong_reference"}
    assert analysis_equipment(normalized)["nodes"] == {}
    assert analysis_equipment(normalized)["bindings"] == {"reactor": "wrong_reference"}


@pytest.mark.parametrize("field,value", [("category", "MixingEquipment"), ("category_id", "equipment.mixing"),
                                        ("subtype_id", "equipment.vial"), ("apparatus_kind", "Vial")])
def test_canonical_identity_edits_expire_old_source_evidence(field, value):
    node = normalize_equipment(hardware(source_microreactor()))["nodes"]["reactor"]
    node[field] = value
    assert "source_fact_sha256" not in analysis_node(node)


def candidate(kind="round_bottom_flask", **changes):
    return {"id": "fixture", "apparatus_kind": kind, "category": "vessel",
            "params": {"capacity_mL": 20}, "capacity_scope": "single_reaction_vessel",
            "wetted_materials": ["PTFE"], "ports": ["in", "out"],
            "source_url": "urn:test:explicit-rating", **changes}


def demands(subtype="equipment.round_bottom_flask"):
    return {"subtype_id": subtype, "capacity_mL": 10, "capacity_scope": "single_reaction_vessel",
            "wetted_materials": ["PTFE"], "ports": ["in"]}


def test_alias_identity_alone_does_not_establish_a_substitute():
    result = conditional_substitutes({"subtype_id": "equipment.round_bottom_flask"}, [candidate("RBF")])[0]
    assert result["status"] == "unknown"
    assert result["rule_id"] == "equipment.same_subtype"
    assert result["unknowns"][0]["field"] == "functional_requirements"


def test_substitution_uses_explicit_constraints_and_does_not_merge_catalog_entries():
    original = [candidate("RBF"), candidate("圆底烧瓶", id="small", params={"capacity_mL": 5})]
    snapshot = copy.deepcopy(original)
    result = conditional_substitutes(demands(), original)
    assert [row["status"] for row in result] == ["compatible", "incompatible"]
    assert original == snapshot


def test_shared_category_never_makes_flask_and_microreactor_interchangeable():
    result = conditional_substitutes(demands(), [candidate("microreactor")])[0]
    assert result["status"] == "unknown"
    assert result["rule_id"] is None
    assert any(row["field"] == "substitution_rule" for row in result["unknowns"])


def test_canonical_identity_edits_cannot_reuse_previous_substitution_evidence():
    normalized = normalize_equipment(hardware(candidate()))["nodes"]["reactor"]
    normalized["category"] = "MixingEquipment"
    result = conditional_substitutes(demands(), [normalized])[0]
    assert result["status"] == "unknown"
    assert any(row["field"] == "canonical_identity" for row in result["unknowns"])


def test_conditional_batch_container_relation_requires_scope_material_and_volume():
    result = conditional_substitutes(demands(), [candidate("vial")])[0]
    assert result["status"] == "compatible"
    assert result["rule_id"] == "equipment.batch_container_alternative"
    incomplete = conditional_substitutes({"subtype_id": "equipment.round_bottom_flask", "ports": ["in"]}, [candidate("vial")])[0]
    assert incomplete["status"] == "unknown"


def test_existing_legacy_profiles_normalize_without_fabricating_ratings():
    devices = load_library("hardware.yaml")["devices"]
    original = {"nodes": {node["id"]: node for node in devices}}
    normalized = normalize_equipment(original)
    assert all(node["normalization"]["status"] == "resolved" for node in normalized["nodes"].values())
    assert analysis_equipment(normalized) == original
    for key, node in normalized["nodes"].items():
        assert node["params"] == original["nodes"][key]["params"]
