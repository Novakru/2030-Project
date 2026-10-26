"""Source-scale regressions; fixture records are not experimental observations."""
import copy

from protocol_risk.apparatus import source_apparatus
from protocol_risk.symbolic import _known, evaluate, hardware_evidence
from protocol_risk.xdl import bind_hardware


def subject(text="a 5.0 mL wheaton microreactor was charged with solvent (1.0 mL)"):
    return {"id": "fixture", "raw_sha256": "fixture-hash", "source": {"url": "https://example.test/procedure"},
            "steps": [{"id": "add", "op": "Add", "vessel": "reactor", "reagent": "solvent",
                       "amount": {"value": 1, "unit": "mL"}, "meta": {"stage": "reaction", "evidence": text}}],
            "reagents": [{"id": "solvent", "name": "water", "role": "SOLVENT"}]}


def test_microreactor_retains_source_capacity_without_model_or_pressure_guesses():
    p = bind_hardware(subject())
    vessel = p["hardware"]["nodes"]["reactor"]
    assert vessel["apparatus_kind"] == "microreactor"
    assert _known(vessel, "capacity_mL") == 5
    assert vessel["model"] is None and not vessel["verified"]
    assert _known(vessel, "pressure_max_bar") is None
    assert hardware_evidence(vessel) == "source_reported_provisional"
    assert "5.0 mL wheaton microreactor" in vessel["source_evidence"][0]["value"]
    # Do not silently upsize the apparatus to make an overloaded procedure pass.
    p["steps"][0]["amount"]["value"] = 6
    assert evaluate(p).risks == ["A1"]
    assert p["hardware"]["nodes"]["reactor"]["params"]["capacity_mL"] == 5


def test_source_capacity_cannot_be_edited_without_expiring_its_evidence():
    vessel, _ = source_apparatus(subject())
    vessel["params"]["capacity_mL"] = 50
    assert hardware_evidence(vessel) is None and _known(vessel, "capacity_mL") is None


def test_workup_flask_does_not_replace_the_reaction_microreactor():
    p = subject()
    p["steps"].append({"id": "workup", "op": "Evaporate", "vessel": "reactor",
                       "meta": {"stage": "workup", "evidence": "Transferred to a 100 mL round-bottom flask"}})
    assert source_apparatus(p)[0]["params"]["capacity_mL"] == 5


def test_structured_vial_volume_and_material_are_not_a_default_flask():
    p = subject("Solvent was added")
    p["context"] = {"source_setup": {"vessel": {"type": "VIAL", "material": {"type": "GLASS"},
                              "volume": {"units": "MILLILITER", "value": 8}}}}
    node = bind_hardware(p)["hardware"]["nodes"]["reactor"]
    assert node["apparatus_kind"] == "vial" and _known(node, "capacity_mL") == 8
    assert node["wetted_materials"] == ["glass_unspecified"]


def test_plate_single_well_is_not_multiplied_by_well_count():
    p = subject("Solvent was added")
    raw = {"raw_sha256": "fixture-hash", "source": p["source"], "setup": {"vessel": {"type": "WELL_PLATE",
        "details": "1536-well plate, 12.5 \u00b5L-wells", "volume": {"units": "MICROLITER", "value": 12.5}}}}
    node, issues = source_apparatus(p, raw)
    assert issues == [] and _known(node, "capacity_mL") == .0125
    assert node["capacity_scope"] == "per_well"
    raw["setup"]["vessel"]["details"] = "96-well block, 8 x 30 mm glass vial inserts"
    node, _ = source_apparatus(p, raw)
    assert _known(node, "capacity_mL") is None
    assert node["params"]["reported_volume_mL"] == .0125


def test_conflicting_source_sizes_are_retained_and_abstain():
    p = subject()
    raw = {"raw_sha256": "fixture-hash", "source": p["source"], "setup": {"vessel": {
        "type": "MICROREACTOR", "volume": {"units": "MILLILITER", "value": 50}}}}
    node, issues = source_apparatus(p, raw)
    assert issues[0]["reason"] == "source_apparatus_conflict"
    assert _known(node, "capacity_mL") is None
    assert issues[0]["text"]["params"]["capacity_mL"] == 5


def test_unknown_apparatus_remains_unknown_and_controller_is_only_proposed():
    p = bind_hardware(subject("Solvent was added"))
    assert _known(p["hardware"]["nodes"]["reactor"], "capacity_mL") is None
    assert p["hardware"]["nodes"]["heater"]["binding_basis"] == "proposed_analysis_configuration"


def test_reported_heating_block_is_not_replaced_by_an_ika_model():
    p = subject()
    p["steps"].append({"id": "heat", "op": "HeatChill", "temp_C": 80, "vessel": "reactor",
                       "meta": {"stage": "reaction", "evidence": "placed in a pre-heated aluminum block at 80 C"}})
    heater = bind_hardware(p)["hardware"]["nodes"]["heater"]
    assert heater["apparatus_kind"] == "heating_block" and heater["model"] is None
    assert _known(heater, "T_max_C") is None


def test_reviewed_override_remains_authoritative_and_source_is_retained():
    p = subject()
    original = copy.deepcopy(p)
    bind_hardware(p, configuration={"nodes": {"reactor": "pyrex_rb_4320a_50"}, "edges": [], "bindings": {}})
    assert p["hardware"]["nodes"]["reactor"]["params"]["capacity_mL"] == 50
    assert p["hardware"]["source_apparatus"]["params"]["capacity_mL"] == 5
    assert p["steps"] == original["steps"]
