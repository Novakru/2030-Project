"""Canonical representations preserve source information and intentional faults."""
import copy

import pytest

from mosaic.protocol.normalization import (
    analysis_protocol, is_normalized, normalize_protocol, semantic_contract_hash,
    validate_normalized,
)


def vocabulary():
    def operation(name, parameters, **extra):
        return {"name": name, "kind": "action", "domain": "general",
                "parameters": {key: {"type": "object" if key == "components" else "quantity" if key in {"amount", "duration_s", "rpm", "temperature", "temp_C"} else "string"}
                               for key in parameters},
                "preconditions": [], "effects": ["declared effect"], "capabilities": [], **extra}
    return {"operations": {
        "op.add": operation("Add", ["reagent", "amount", "method", "components"]),
        "op.mix": operation("Mix", ["method", "duration_s", "rpm"]),
        "op.heat": operation("Heat", ["temperature", "duration_s"]),
        "op.temperature": operation("SetTemperature", ["temp_C", "duration_s"]),
    }, "mappings": {"aliases": [
        {"id": "alias.add", "expressions": ["Add", "add", "charge", "加入"], "operation_id": "op.add"},
        {"id": "alias.stir", "expressions": ["Stir", "stir", "搅拌"], "operation_id": "op.mix",
         "defaults": {"method": "stir"}},
        {"id": "alias.shake", "expressions": ["shake"], "operation_id": "op.mix",
         "defaults": {"method": "shake"}, "context": {"object_role": "material_or_contents",
                                                          "ambiguous_without_context": True}},
        {"id": "alias.temperature", "expressions": ["HeatChill"], "operation_id": "op.temperature"},
    ], "migrations": {
        "ChargeMaterial": {"operation_id": "op.add", "classification": "parameter_variant",
                           "parameter_map": {"material": "reagent", "quantity": "amount"}},
        "HeatAndStir": {"operation_id": "op.heat", "classification": "composition",
                        "composition": {"steps": [
                            {"key": "heat", "operation_id": "op.heat",
                             "parameter_map": {"temperature": "temperature", "duration": "duration_s"}},
                            {"key": "mix", "operation_id": "op.mix", "defaults": {"method": "stir"},
                             "parameter_map": {"speed": "rpm", "duration": "duration_s"}}],
                            "relations": [{"from": "heat", "to": "mix", "relation": "same_interval"}]}}
    }, "contracts": {}}}


def protocol(*steps):
    return {"id": "example", "steps": list(steps), "operation_definitions": {},
            "crosscheck": {"tier": "silver", "conflicts": []}}


def parameter(value, evidence="literal source", unit=None):
    return {"value": value, "evidence": evidence, **({"unit": unit} if unit is not None else {})}


@pytest.mark.parametrize("expression", ["Add", "add", "charge", "加入"])
def test_declared_add_aliases_share_canonical_identity(expression):
    source = protocol({"id": "s1", "op": expression, "reagent": "r1", "vessel": "v1", "amount": {"value": 2, "unit": "mL"}})
    result = normalize_protocol(source, vocabulary=vocabulary())
    assert result["steps"][0]["operation_id"] == "op.add"
    assert result["steps"][0]["op"] == "Add"
    assert result["steps"][0]["normalization"]["source_operation"] == expression
    assert analysis_protocol(result) == source
    assert source["steps"][0]["op"] == expression


def test_mixing_method_distinguishes_contextual_aliases():
    stir = normalize_protocol(protocol({"id": "s1", "op": "Stir", "rpm": 350, "duration_s": 60}), vocabulary=vocabulary())
    ambiguous = normalize_protocol(protocol({"id": "s1", "op": "shake"}), vocabulary=vocabulary())
    shake = normalize_protocol({**protocol({"id": "s1", "op": "shake"}),
                                "context": {"object_role": "material_or_contents"}}, vocabulary=vocabulary())
    assert stir["steps"][0]["op"] == shake["steps"][0]["op"] == "Mix"
    assert stir["steps"][0]["parameters"]["method"]["value"] == "stir"
    assert shake["steps"][0]["parameters"]["method"]["value"] == "shake"
    assert ambiguous["steps"][0]["op"] == "Unresolved"


def test_conflicting_contextual_mappings_are_not_arbitrarily_selected():
    catalog = vocabulary()
    catalog["mappings"]["aliases"].extend([
        {"id": "a", "expressions": ["agitate"], "operation_id": "op.mix", "defaults": {"method": "stir"}},
        {"id": "b", "expressions": ["agitate"], "operation_id": "op.mix", "defaults": {"method": "shake"}}])
    result = normalize_protocol(protocol({"id": "s1", "op": "agitate"}), vocabulary=catalog)
    assert result["steps"][0]["normalization"]["status"] == "unresolved"


def test_exact_contract_wins_and_unknown_contract_requires_new_proposal():
    catalog = vocabulary()
    catalog["mappings"]["migrations"]["ChargeMaterial"]["requires_exact_contract"] = True
    catalog["mappings"]["contracts"]["known"] = {"legacy_name": "ChargeMaterial", "operation_id": "op.mix"}
    source = protocol({"id": "s1", "op": "ChargeMaterial", "parameters": {"material": parameter("r1")}})
    source["operation_definitions"] = {"ChargeMaterial": {"semantic_sha256": "known"}}
    assert normalize_protocol(source, vocabulary=catalog)["steps"][0]["operation_id"] == "op.mix"
    source["operation_definitions"]["ChargeMaterial"]["semantic_sha256"] = "unknown"
    assert normalize_protocol(source, vocabulary=catalog)["steps"][0]["operation_id"] == "op.unresolved"


def test_parameter_renaming_preserves_all_independent_source_facts():
    source = protocol({"id": "s1", "op": "ChargeMaterial", "parameters": {
        "material": parameter("r1"), "quantity": parameter(2, unit="mL"),
        "independent_moles": parameter(4, unit="mmol")}})
    normalized = normalize_protocol(source, vocabulary=vocabulary())
    step = normalized["steps"][0]
    assert step["parameters"]["reagent"] == source["steps"][0]["parameters"]["material"]
    assert step["reported_parameters"]["independent_moles"]["value"] == 4
    assert analysis_protocol(normalized) == source
    assert set(normalized["operation_definitions"]) == {"Add"}
    assert normalized["normalization"]["source_operation_definitions"] == {}


def test_dotted_parameters_have_reversible_current_value_bindings():
    catalog = vocabulary()
    catalog["mappings"]["migrations"]["ChargeMaterial"]["parameter_map"]["mass"] = "components.solute.mass"
    source = protocol({"id": "s1", "op": "ChargeMaterial", "parameters": {"mass": parameter(10, unit="mg")}})
    normalized = normalize_protocol(source, vocabulary=catalog)
    normalized["steps"][0]["parameters"]["components"]["solute"]["mass"]["value"] = -9
    lowered = analysis_protocol(normalized)
    assert lowered["steps"][0]["parameters"] == {"mass": parameter(-9, unit="mg")}


def test_normalization_does_not_repair_negative_quantities_or_bad_references():
    source = protocol({"id": "s1", "op": "Add", "reagent": "missing_reagent", "vessel": "deleted_vessel",
                       "amount": {"value": -8, "unit": "seconds"}})
    normalized = normalize_protocol(source, vocabulary=vocabulary())
    normalized["steps"][0]["amount"]["value"] = -11
    normalized["steps"][0]["reagent"] = "another_missing_reagent"
    lower = analysis_protocol(normalized)
    assert lower["steps"][0]["amount"] == {"value": -11, "unit": "seconds"}
    assert lower["steps"][0]["reagent"] == "another_missing_reagent"
    assert lower["steps"][0]["vessel"] == "deleted_vessel"
    assert lower["crosscheck"] == source["crosscheck"]


def test_source_unknowns_are_preserved_without_default_overwrite():
    gap = {"status": "qualitative", "marker": "__QUALITATIVE__", "raw": "overnight", "evidence": "overnight"}
    source = protocol({"id": "s1", "op": "Stir", "missing_parameters": {"duration_s": gap},
                       "parameters": {"method": gap}})
    normalized = normalize_protocol(source, vocabulary=vocabulary())
    assert normalized["steps"][0]["parameters"]["method"] == gap
    assert normalized["steps"][0]["missing_parameters"]["duration_s"] == gap
    assert analysis_protocol(normalized) == source


def test_parameter_collision_retains_both_values_and_marks_conflict():
    catalog = vocabulary()
    catalog["mappings"]["migrations"]["ChargeMaterial"]["parameter_map"]["quantity2"] = "amount"
    source = protocol({"id": "s1", "op": "ChargeMaterial", "parameters": {
        "quantity": parameter(2, unit="mL"), "quantity2": parameter(8, unit="mL")}})
    normalized = normalize_protocol(source, vocabulary=catalog)
    assert normalized["steps"][0]["normalization"]["status"] == "unresolved"
    assert normalized["steps"][0]["reported_parameters"]["quantity2"]["value"] == 8
    assert analysis_protocol(normalized) == source


def test_composition_retains_concurrency_and_projects_current_member_values():
    source = protocol({"id": "s1", "op": "HeatAndStir", "vessel": "v1", "parameters": {
        "temperature": parameter(80, unit="C"), "speed": parameter(500, unit="rpm"),
        "duration": parameter(90, unit="s"), "additional_fact": parameter("literal")}},
        {"id": "s2", "op": "Add", "requires": ["s1"], "reagent": "r2"})
    normalized = normalize_protocol(source, vocabulary=vocabulary())
    assert [step["op"] for step in normalized["steps"]] == ["Heat", "Mix", "Add"]
    assert normalized["temporal_relations"][0]["relation"] == "same_interval"
    assert normalized["steps"][2]["requires"] == ["s1"]
    assert analysis_protocol(normalized) == source
    normalized["steps"][1]["parameters"]["rpm"]["value"] = 900
    assert analysis_protocol(normalized)["steps"][0]["parameters"]["speed"]["value"] == 900


def test_legacy_combined_temperature_step_is_not_a_plain_alias():
    source = protocol({"id": "s1", "op": "HeatChill", "temp_C": 70, "stir": True, "rpm": 400})
    result = normalize_protocol(source, vocabulary=vocabulary())
    assert [step["op"] for step in result["steps"]] == ["SetTemperature", "Mix"]
    assert result["temporal_relations"][0]["relation"] == "same_interval"
    assert analysis_protocol(result) == source


def test_contract_hash_ignores_display_and_mappings_but_tracks_semantics():
    contract = {"id": "op.mix", **vocabulary()["operations"]["op.mix"]}
    relabeled = copy.deepcopy(contract)
    relabeled.update(name="Agitate", description="Different prose", aliases=["new alias"], mapping_revision="new")
    relabeled["parameters"]["method"]["description"] = "New display text"
    assert semantic_contract_hash(contract) == semantic_contract_hash(relabeled)
    relabeled["effects"].append("new state effect")
    assert semantic_contract_hash(contract) != semantic_contract_hash(relabeled)


def test_idempotence_and_corrupt_contract_rejection():
    source = protocol({"id": "s1", "op": "Stir", "duration_s": 20})
    normalized = normalize_protocol(source, vocabulary=vocabulary())
    assert is_normalized(normalized)
    assert normalize_protocol(normalized, vocabulary=vocabulary()) == normalized
    assert validate_normalized(normalized) == []
    normalized["operation_definitions"]["Mix"]["effects"].append("unhashed mutation")
    with pytest.raises(ValueError, match="semantic hash"):
        validate_normalized(normalized)


def test_quantitative_conversion_is_reversed_from_current_value():
    catalog = vocabulary()
    catalog["mappings"]["migrations"]["ChargeMaterial"]["parameter_map"]["quantity"] = {
        "target": "amount", "scale": 0.001, "unit": "mL"}
    source = protocol({"id": "s1", "op": "ChargeMaterial", "parameters": {"quantity": parameter(2000, unit="uL")}})
    normalized = normalize_protocol(source, vocabulary=catalog)
    assert normalized["steps"][0]["parameters"]["amount"]["value"] == 2
    normalized["steps"][0]["parameters"]["amount"]["value"] = -3
    assert analysis_protocol(normalized)["steps"][0]["parameters"]["quantity"] == parameter(-3000, unit="uL")


def test_projection_does_not_change_integer_types_for_identity_mappings():
    source = protocol({"id": "s1", "op": "ChargeMaterial", "parameters": {"quantity": parameter(2, unit="mL")}})
    lower = analysis_protocol(normalize_protocol(source, vocabulary=vocabulary()))
    assert type(lower["steps"][0]["parameters"]["quantity"]["value"]) is int
