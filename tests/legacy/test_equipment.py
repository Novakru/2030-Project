import copy

import pytest

from mosaic.equipment import check_substitution, classify_equipment, equipment_groups
from mosaic.protocol.io import load_library


def cited_vial(**changes):
    # Test contract only, not a manufacturer specification.
    return {"id": "fixture_vial", "apparatus_kind": "vial", "params": {"capacity_mL": 10, "working_volume_mL": 8},
            "capacity_scope": "single_reaction_vessel", "capabilities": ["contain_material"],
            "wetted_materials": ["PTFE"], "ports": ["in", "out"],
            "source_url": "urn:test:explicit-device-contract", **changes}


def test_family_groups_keep_capacity_variants_and_original_facts():
    devices = [cited_vial(), cited_vial(id="larger_vial", params={"capacity_mL": 20})]
    original = copy.deepcopy(devices)
    groups = equipment_groups(devices)
    assert groups["families"]["vial"]["device_ids"] == ["fixture_vial", "larger_vial"]
    assert groups["catalog_profiles"][0]["params"]["capacity_mL"] == 10
    assert groups["catalog_profiles"][1]["params"]["capacity_mL"] == 20
    assert groups["substitution_groups"][0]["status"] == "candidates_only"
    assert devices == original


def test_microreactor_is_preserved_and_unknown_specific_kind_is_not_generic_flask():
    assert classify_equipment({"apparatus_kind": "micro-reactor", "category": "vessel"}) == "microreactor"
    assert classify_equipment({"apparatus_kind": "flow_reactor", "category": "vessel"}) is None
    assert classify_equipment({"category": "vessel"}) is None
    assert classify_equipment({"apparatus_kind": "custom_block", "category": "heater_stirrer"}) is None
    assert classify_equipment({"apparatus_kind": "microreactor", "family": "vial"}) is None


@pytest.mark.parametrize("labels", [
    {"apparatus_kind": "vial", "type": "microreactor"},
    {"apparatus_kind": "vial", "kind": "flask"},
    {"kind": "vial", "type": "unknown", "family": "vial"},
    {"type": "vial", "family": "microreactor"},
])
def test_conflicting_or_unresolved_source_type_labels_remain_unclassified(labels):
    device = {"id": "source_conflict", **labels}
    assert classify_equipment(device) is None
    report = equipment_groups([device])
    assert report["unclassified"] == [{"kind": "catalog_entry", "id": "source_conflict"}]
    assert not report["substitution_groups"]


def test_consistent_source_type_aliases_can_still_share_a_family():
    assert classify_equipment({"apparatus_kind": "micro-reactor", "kind": "microreactor", "type": "MICROREACTOR"}) == "microreactor"


def test_existing_catalog_models_and_templates_are_indexed_without_adding_models():
    devices = load_library("hardware.yaml")["devices"]
    groups = equipment_groups(devices)
    assert len(groups["catalog_profiles"]) == len(devices)
    assert not groups["unclassified"]
    assert "ika_rct_basic_25008259" in groups["families"]["hotplate_stirrer"]["device_ids"]
    assert "chemputer_reactor_template" in groups["families"]["batch_reactor"]["device_ids"]


def test_anonymous_observations_never_invent_identified_profiles():
    observations = [{"observation_id": "source_vial", "apparatus_kind": "vial", "params": {"capacity_mL": 5},
                     "identity": {"manufacturer": "stated vendor", "model": None}, "evidence": [{"quote": "5 mL vial"}]}]
    groups = equipment_groups([], observations)
    assert groups["anonymous_observations"][0]["params"]["capacity_mL"] == 5
    assert groups["identified_profiles"] == []
    assert groups["families"]["vial"]["observation_ids"] == ["source_vial"]


def test_identified_observation_profiles_keep_conflicting_scopes_separate():
    first = {"identity": {"manufacturer": "fixture", "model": "model"}, "apparatus_kind": "well_plate",
             "capacity_scope": "per_well", "params": {"capacity_mL": 1}, "evidence": [{"quote": "source"}]}
    second = {**first, "capacity_scope": "whole_plate"}
    groups = equipment_groups([], [first, first, second])
    assert len(groups["identified_profiles"]) == 2
    assert len(groups["identified_profiles"][0]["observation_ids"]) == 1
    third = {**first, "sterile": True}
    assert len(equipment_groups([], [first, third])["identified_profiles"]) == 2


def test_matching_family_alone_does_not_certify_substitution():
    result = check_substitution({"family": "vial"}, cited_vial())
    assert result["status"] == "unknown"
    assert result["unknowns"][0]["field"] == "functional_requirements"


def test_explicit_supported_demands_can_be_conditionally_compatible():
    result = check_substitution({"family": "vial", "capabilities": ["contain_material"], "working_volume_mL": 5,
        "capacity_scope": "single_reaction_vessel", "wetted_materials": ["PTFE"], "ports": ["in"]}, cited_vial())
    assert result["status"] == "compatible"
    assert not result["unknowns"] and not result["incompatibilities"]


def test_same_family_can_be_too_small_and_does_not_borrow_larger_rating():
    requirement = {"family": "vial", "capacity_mL": 15, "capacity_scope": "single_reaction_vessel"}
    assert check_substitution(requirement, cited_vial())["status"] == "incompatible"
    assert check_substitution(requirement, cited_vial(params={"capacity_mL": None}))["status"] == "unknown"


def test_working_capacity_is_not_inferred_from_nominal_capacity():
    result = check_substitution({"working_volume_mL": 5, "capacity_scope": "single_reaction_vessel"},
                                cited_vial(params={"capacity_mL": 10}))
    assert result["status"] == "unknown"


def test_whole_plate_volume_neither_passes_nor_rejects_a_per_well_demand():
    candidate = cited_vial(apparatus_kind="well_plate", capacity_scope="whole_plate", params={"capacity_mL": 0.1})
    result = check_substitution({"family": "well_plate", "capacity_mL": 1, "capacity_scope": "per_well"}, candidate)
    assert result["status"] == "unknown" and not result["incompatibilities"]


def test_hotplate_setpoint_limits_do_not_establish_sample_temperature_range():
    candidate = {"category": "heater_stirrer", "params": {"T_min_C": 50, "T_max_C": 500},
                 "parameter_scope": "heating_plate_setpoint", "source_url": "urn:test:hotplate"}
    result = check_substitution({"temperature_C": 30, "temperature_scope": "sample"}, candidate)
    assert result["status"] == "unknown" and not result["incompatibilities"]
    assert check_substitution({"temperature_C": 30, "temperature_scope": "plate_setpoint"}, candidate)["status"] == "incompatible"
    assert check_substitution({"temperature_C": 100, "temperature_scope": "plate_setpoint"}, candidate)["status"] == "compatible"


@pytest.mark.parametrize("scope", ["unknown", "unresolved", "reported_vessel_volume_scope_unresolved", "N/A", "not reported"])
@pytest.mark.parametrize("field,scope_field,params", [
    ("capacity_mL", "capacity_scope", {"capacity_mL": 10}),
    ("temperature_C", "temperature_scope", {"T_min_C": 0, "T_max_C": 100}),
    ("pressure_bar", "pressure_scope", {"pressure_min_bar": 0, "pressure_max_bar": 100}),
    ("flow_mL_min", "flow_scope", {"flow_min_mL_min": 0, "flow_max_mL_min": 100}),
    ("rpm", "mixing_mode", {"rpm_min": 0, "rpm_max": 100}),
])
def test_identical_uncertainty_labels_do_not_establish_applicable_numeric_scope(scope, field, scope_field, params):
    requirement = {field: 5, scope_field: scope}
    candidate = {"params": params, scope_field: scope, "source_url": "urn:test:explicit-contract"}
    result = check_substitution(requirement, candidate)
    assert result["status"] == "unknown"
    assert any(item["field"] == scope_field for item in result["unknowns"])


def test_missing_bound_and_uncited_numeric_claims_are_unknown():
    candidate = {"params": {"rpm_max": 1500}, "mixing_mode": "magnetic", "source_url": "urn:test:stirrer"}
    assert check_substitution({"rpm": 300, "mixing_mode": "magnetic"}, candidate)["status"] == "unknown"
    assert check_substitution({"rpm": 1600, "mixing_mode": "magnetic"}, candidate)["status"] == "incompatible"
    assert check_substitution({"rpm": 300}, {"params": {"rpm_min": 0, "rpm_max": 1500}})["status"] == "unknown"
    candidate["params"]["rpm_min"] = 1600
    assert check_substitution({"rpm": 300}, candidate)["status"] == "unknown"


@pytest.mark.parametrize("reference", [{}, None, "not a reference", {"quote": "a number"},
    {"source_url": "unknown"}, {"source_url": "https://"},
    {"source_id": "source", "source_sha256": "bad", "start": 0, "end": 1, "quote": "x"},
    {"source_id": "source", "source_sha256": "a" * 64, "start": True, "end": 1, "quote": "x"}])
def test_empty_or_malformed_references_cannot_authorize_numeric_ranges(reference):
    candidate = {"params": {"rpm_min": 0, "rpm_max": 1000}, "mixing_mode": "magnetic", "evidence": [reference]}
    result = check_substitution({"rpm": 300, "mixing_mode": "magnetic"}, candidate)
    assert result["status"] == "unknown"
    assert all(not item["evidence"] for item in result["checks"])


def test_valid_reference_shapes_remain_usable_without_pretending_to_verify_ratings():
    text = "Test contract: magnetic stirring range 0 to 1000 rpm."
    references = [SourceSpan.locate("test_contract", text, text).to_dict(),
                  {"raw_sha256": "a" * 64, "locator": "/device/rpm"},
                  {"source_url": "https://example.test/manual"}]
    for reference in references:
        candidate = {"params": {"rpm_min": 0, "rpm_max": 1000}, "mixing_mode": "magnetic", "evidence": [reference]}
        assert check_substitution({"rpm": 300, "mixing_mode": "magnetic"}, candidate)["status"] == "compatible"


def test_flow_and_pressure_numeric_limits_require_matching_operating_scopes():
    candidate = {"params": {"flow_min_mL_min": 0.1, "flow_max_mL_min": 2,
                             "pressure_min_bar": 0, "pressure_max_bar": 3},
                 "flow_scope": "per_channel", "pressure_scope": "absolute", "source_url": "urn:test:pump"}
    result = check_substitution({"flow_mL_min": 1, "flow_scope": "per_channel",
                                 "pressure_bar": 2, "pressure_scope": "absolute"}, candidate)
    assert result["status"] == "compatible"
    assert check_substitution({"flow_mL_min": 3, "flow_scope": "whole_device"}, candidate)["status"] == "unknown"
    assert check_substitution({"pressure_bar": 10, "pressure_scope": "gauge"}, candidate)["status"] == "unknown"
    assert check_substitution({"pressure_bar": 10, "pressure_scope": "absolute"}, candidate)["status"] == "incompatible"


def test_family_search_capabilities_do_not_become_instance_ratings():
    candidate = {"category": "heater_stirrer", "source_url": "urn:test:unrated-class"}
    assert check_substitution({"family": "hotplate_stirrer", "capabilities": ["heat"]}, candidate)["status"] == "unknown"


def test_material_ports_geometry_and_sterility_check_actual_requested_values():
    candidate = cited_vial(wetted_materials=["PTFE", "glass"], geometry={"joint": "24/40"}, sterile=False)
    result = check_substitution({"wetted_materials": ["PTFE"], "ports": ["vacuum"],
                                 "geometry": {"joint": "14/20"}, "sterile": True}, candidate)
    assert result["status"] == "incompatible" and len(result["incompatibilities"]) == 4


@pytest.mark.parametrize("geometry", [
    {"diameter_mm": {"value": None, "unit": "mm"}}, {"diameter_mm": "unknown"},
    {"height_mm": True}, {"height_mm": {"value": 5, "unit": "unknown"}},
    {"height_mm": {"value": 5, "unit": "kg"}}, {"dimensions_mm": [5, None]},
    {"height_mm": {"value": 5}}, {},
])
def test_recursively_unknown_or_untyped_geometry_never_passes_even_when_equal(geometry):
    candidate = cited_vial(geometry=copy.deepcopy(geometry))
    result = check_substitution({"capabilities": ["contain_material"], "geometry": geometry}, candidate)
    assert result["status"] == "unknown"


def test_boolean_and_numeric_geometry_cannot_match_through_python_coercion():
    assert check_substitution({"geometry": {"height_mm": True}}, cited_vial(geometry={"height_mm": 1}))["status"] == "unknown"


def test_fully_specified_geometry_identifiers_and_dimensions_remain_usable():
    geometry = {"joint": "24/40", "well_count": 96, "height_mm": {"value": 5, "unit": "mm"}}
    assert check_substitution({"geometry": geometry}, cited_vial(geometry=copy.deepcopy(geometry)))["status"] == "compatible"


def test_unsupported_constraint_and_missing_topology_never_silently_pass():
    result = check_substitution({"capabilities": ["contain_material"], "connections": [["in", "out"]]}, cited_vial())
    assert result["status"] == "unknown"
    assert result["unknowns"][0]["field"] == "connections"


def test_scope_only_constraint_is_not_silently_ignored():
    result = check_substitution({"capabilities": ["contain_material"], "temperature_scope": "sample"}, cited_vial())
    assert result["status"] == "unknown"


@pytest.mark.parametrize("requirement", [{"capabilities": "contain_material"}, {"sterile": "false"},
                                          {"geometry": "round"}, {"ports": []}])
def test_malformed_constraints_are_explicit_errors(requirement):
    with pytest.raises(ValueError):
        check_substitution(requirement, cited_vial())


@pytest.mark.parametrize("field,value", [("capacity_mL", 0), ("working_volume_mL", -1), ("rpm", float("nan"))])
def test_invalid_demands_are_explicit_errors(field, value):
    with pytest.raises(ValueError):
        check_substitution({field: value}, cited_vial())
