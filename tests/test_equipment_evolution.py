"""Exercise admission, current-batch rebinding and independent substitution checks."""
import copy

import pytest

from mosaic.canonical import finalize_protocol, registry_vocabulary
from mosaic.evidence import SourceSpan
from mosaic.protocol.equipment_normalization import normalize_equipment, analysis_equipment, conditional_substitutes
from mosaic.registry import Registry
from tests.test_mosaic_evolution import observed, evolve


TEXT = "Use a Schlenk flask, also described here as a Schlenk tube."


def proposal():
    aliases = ["Schlenk flask", "Schlenk tube"]
    return {"action": "equipment_subtype", "origins": ["source"], "reason": "Gas-handling glassware is more specific than an unspecified flask.",
            "subtype_id": "equipment.schlenk_vessel",
            "equipment": {"name": "SchlenkVessel", "category_id": "equipment.reaction_container",
                          "legacy_kind": "schlenk_vessel", "capabilities": ["material_containment", "gas_handling"]},
            "aliases": aliases, "considered_subtypes": ["equipment.flask"],
            "counterexample": "An unspecified flask does not describe the gas-handling construction.",
            "witnesses": [{"node": {"category": "vessel", "apparatus_kind": a, "params": {}}} for a in aliases]}


def admit(value=None):
    obs = observed(TEXT, "source", kind="device", device={"kind": "Schlenk flask"})
    return evolve([obs], [value or proposal()])


def test_equipment_admission_rebinds_prior_unknown_without_changing_facts():
    raw = {"nodes": {"reactor": {"category": "vessel", "apparatus_kind": "Schlenk flask", "params": {"capacity_mL": 25}}}}
    old = normalize_equipment(raw)
    assert old["nodes"]["reactor"]["subtype_id"] is None
    registry, report = admit()
    vocab = registry_vocabulary(registry)
    rebound = normalize_equipment(old, catalog=vocab["equipment"], mappings=vocab["equipment_mappings"])
    assert rebound["nodes"]["reactor"]["subtype_id"] == "equipment.schlenk_vessel"
    assert analysis_equipment(rebound, catalog=vocab["equipment"]) == raw
    assert normalize_equipment(rebound, catalog=vocab["equipment"], mappings=vocab["equipment_mappings"]) == rebound
    assert report["retryable_source_ids"] == ["source"]
    record = finalize_protocol({"steps": [{"id": "s1", "op": "Wait", "duration_s": 1}], "reagents": [], "hardware": rebound}, vocabulary=vocab)
    # Referenced/source equipment is emitted; semantic IDs and contracts are external.
    record["hardware"]["nodes"]["reactor"]["binding_basis"] = "source_reported"
    record = finalize_protocol(record, vocabulary=vocab)
    assert 'type="schlenk_vessel"' in record["xdl"]
    assert "equipment.schlenk_vessel" not in record["xdl"]


@pytest.mark.parametrize("alter", [
    lambda p: p["equipment"].update(params={"pressure_max_bar": 100}),
    lambda p: p["equipment"].update(configuration_parameters={"capacity": {"type": "number", "default": 50}}),
    lambda p: p.update(aliases=["vessel"]),
    lambda p: p.update(aliases=["invented apparatus"]),
    lambda p: p.update(witnesses=[]),
    lambda p: p["witnesses"][0]["node"].update(params={"capacity_mL": 50}),
    lambda p: p.update(considered_subtypes=["equipment.does_not_exist"]),
])
def test_invalid_equipment_proposals_do_not_partially_modify_registry(alter):
    p = proposal()
    alter(p)
    registry, report = admit(p)
    assert report["rejected"]
    assert "equipment.schlenk_vessel" not in registry.snapshot["equipment_catalog"]["subtypes"]


def test_new_alias_does_not_version_or_duplicate_equipment_contract():
    registry, _ = admit()
    before = copy.deepcopy(registry.snapshot["equipment_catalog"])
    obs = observed("Use Schlenk glassware.", "alias", kind="device", device={"kind": "Schlenk glassware"})
    p = {"action": "equipment_alias", "origins": ["alias"], "reason": "Same gas-handling vessel concept.",
         "subtype_id": "equipment.schlenk_vessel", "aliases": ["Schlenk glassware"],
         "witnesses": [{"node": {"category": "vessel", "apparatus_kind": "Schlenk glassware", "params": {}}}]}
    registry, report = evolve([obs], [p], registry=registry)
    assert not report["rejected"] and registry.snapshot["equipment_catalog"] == before
    assert "Schlenk glassware" in registry.snapshot["equipment_mappings"]["aliases"]["equipment.schlenk_vessel"]


def test_conditional_rule_is_admitted_but_missing_physical_facts_stay_unknown():
    registry = Registry()
    text = "Compare a vial and a round-bottom flask."
    change = {"action": "admit_equipment_substitution", "rule": {
        "id": "equipment.pilot_container_rule", "relation": "conditional",
        "subtypes": ["equipment.vial", "equipment.round_bottom_flask"],
        "required_demands": ["capacity_scope", "wetted_materials"], "any_demands": ["capacity_mL"]},
        "evidence": [SourceSpan.locate("rule", text, text).to_dict()],
        "witnesses": [{"candidate_id": "pyrex_rb_4320a_50", "expected": "unknown", "requirement": {
            "subtype_id": "equipment.vial", "capacity_mL": 1, "capacity_scope": "single_reaction_vessel",
            "wetted_materials": ["borosilicate_glass"]}}]}
    evolved = registry.evolve([change], expected_revision=registry.revision, sources={"rule": text})
    profile = next(p for p in evolved.snapshot["devices"] if p["id"] == "pyrex_rb_4320a_50")
    result = conditional_substitutes(change["witnesses"][0]["requirement"], [profile],
        catalog=evolved.snapshot["equipment_catalog"], mappings=evolved.snapshot["equipment_mappings"])[0]
    assert result["status"] == "unknown" and result["rule_id"] == change["rule"]["id"]
    assert evolved.snapshot["equipment_mappings"]["substitution_rules"][0]["admission_scope"] == "candidate_selection_only"
    change["rule"]["id"] = "equipment.unsafe_microreactor_rule"
    change["rule"]["subtypes"][0] = "equipment.microreactor"
    with pytest.raises(ValueError, match="geometry"):
        registry.evolve([change], expected_revision=registry.revision, sources={"rule": text})
