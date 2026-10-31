"""Conditional replacement remains separate from alias admission."""
import pytest
from mosaic.registry import Registry
from mosaic.evidence import SourceSpan
from mosaic.protocol.equipment_normalization import conditional_substitutes


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
