"""Source-to-expression seam tests; no HTTP calls or platform execution."""
import copy
import json

import pytest

from mosaic.completion import complete
from protocol_risk.extract import build_ir
from protocol_risk.extensions import normalize_definition
from protocol_risk.missing import missing_parameter


TEXT = "water (1 mL) was added. The solid was washed with water (2 mL), then dried under vacuum."
ADD = {"op": "Add", "reagent": "water", "alias": "water", "amount": {"value": 1, "unit": "mL"},
       "evidence": "water (1 mL) was added."}
WASH_QUOTE = "The solid was washed with water (2 mL)"
DRY_QUOTE = "dried under vacuum."
WASH = {"name": "Wash", "domain": "chemistry", "description": "Wash retained material with a liquid.",
        "parameters": {"liquid": {"type": "string", "required": True},
                       "volume": {"type": "quantity", "required": True, "dimension": "volume", "unit": "mL"}},
        "effects": ["soluble_material_removed"], "hardware_roles": ["vessel"]}
DRY = {"name": "Dry", "domain": "chemistry", "description": "Dry retained material under stated conditions.",
       "parameters": {"method": {"type": "string", "required": True},
                      "duration": {"type": "quantity", "required": True, "dimension": "time", "unit": "s"}},
       "effects": ["residual_volatile_removed"], "hardware_roles": ["vessel"]}


def source(text=TEXT):
    return {"id": "completion_source", "procedure": text,
            "source": {"db": "TEXT", "url": "file:///example.txt"},
            "components": [{"name": "poisoned_ORD", "amount": 999}],
            "yield_percent": 99, "reaction_smiles": "POISON"}


def base():
    return build_ir(source(), {"steps": [copy.deepcopy(ADD)], "unmapped_actions": [
        {"evidence": WASH_QUOTE, "reason": "washing not yet mapped"},
        {"evidence": DRY_QUOTE, "reason": "drying not yet mapped"}]}, {})


def proposal():
    return {"steps": [copy.deepcopy(ADD),
        {"op": "Wash", "evidence": WASH_QUOTE, "stage": "workup", "parameters": {
            "liquid": {"value": "water", "evidence": "water"},
            "volume": {"value": 2, "unit": "mL", "evidence": "water (2 mL)"}}},
        {"op": "Dry", "evidence": DRY_QUOTE, "stage": "workup", "parameters": {
            "method": {"value": "vacuum", "evidence": "vacuum"},
            "duration": missing_parameter(DRY_QUOTE)}}],
        "definitions": {"Wash": copy.deepcopy(WASH), "Dry": copy.deepcopy(DRY)}, "uncertainties": []}


class Runner:
    def __init__(self, responses):
        self.responses, self.calls = responses, []

    def model_call(self, role, system, payload):
        self.calls.append((role, copy.deepcopy(payload)))
        return {"data": copy.deepcopy(self.responses[min(len(self.calls) - 1, len(self.responses) - 1)]),
                "model": "explicit-test-double"}


def test_supplemental_amounts_preserve_both_mass_and_molar_source_quantities():
    document = source(TEXT.replace("water (1 mL)", "water (18 mg, 1 mmol)", 1))
    original = copy.deepcopy(ADD)
    original.update(amount={"value": 18, "unit": "mg"}, evidence="water (18 mg, 1 mmol) was added.")
    protocol = build_ir(document, {"steps": [original], "unmapped_actions": [
        {"evidence": WASH_QUOTE}, {"evidence": DRY_QUOTE}]}, {})
    response = proposal()
    response["steps"][0] = {**original, "additional_amounts": [{"value": 1, "unit": "mmol"}]}
    result = complete(document, protocol, {}, Runner([response]))["protocol"]
    quantities = result["steps"][0]["source_quantities"]
    assert {(q["value"], q["unit"]) for q in quantities} == {(18, "mg"), (1, "mmol")}
    response["steps"][0]["additional_amounts"][0]["value"] = 99
    with pytest.raises(ValueError, match="Supplemental amount"):
        complete(document, protocol, {}, Runner([response]))


def test_extension_can_refine_a_misclassified_core_action_without_losing_source_facts():
    text = "The mixture was heated by microwave at 80 C for 30 minutes."
    document = source(text)
    protocol = build_ir(document, {"steps": [{"op": "Irradiate", "duration_s": 1800, "evidence": text}],
                                  "unmapped_actions": [{"evidence": text}]}, {})
    definition = {"description": "Heat material using microwave energy", "parameters": {
        "temperature": {"type": "quantity", "unit": "C", "required": True},
        "time": {"type": "quantity", "unit": "min", "required": True}}, "effects": ["heated"]}
    response = {"steps": [{"op": "MicrowaveHeat", "evidence": text, "parameters": {
        "temperature": {"value": 80, "unit": "C", "evidence": "80 C"},
        "time": {"value": 30, "unit": "min", "evidence": "30 minutes"}}}],
        "definitions": {"MicrowaveHeat": definition}}
    result = complete(document, protocol, {}, Runner([response]))["protocol"]
    assert result["steps"][0]["op"] == "MicrowaveHeat"
    assert result["steps"][0]["meta"]["refined_core_proposal"] == "Irradiate"
    response["steps"][0]["parameters"].pop("time")
    definition["parameters"]["time"]["required"] = False
    with pytest.raises(ValueError, match="existing grounded core step"):
        complete(document, protocol, {}, Runner([response]))


def test_standard_missing_parameter_does_not_call_agent_or_invent_value():
    document = source("Add water.")
    protocol = build_ir(document, {"steps": [{"op": "Add", "reagent": "water", "evidence": "Add water."}]}, {})
    runner = Runner([])
    original = copy.deepcopy(protocol)
    result = complete(document, protocol, {}, runner)
    assert not runner.calls and result["notes"]["attempts"] == 0
    assert result["protocol"]["steps"][0]["missing_parameters"]["amount"]["marker"] == "__NOT_REPORTED__"
    assert "amount" not in result["protocol"]["steps"][0]
    assert result["protocol"]["xdl_profile"] == "mosaic-xdl/1"
    assert protocol == original


def test_wash_dry_are_new_declarative_atoms_with_missing_duration():
    protocol, document, runner = base(), source(), Runner([proposal()])
    original = copy.deepcopy(protocol)
    result = complete(document, protocol, {}, runner)
    converted = result["protocol"]
    assert [step["op"] for step in converted["steps"]] == ["Add", "Wash", "Dry"]
    assert converted["steps"][0]["amount"] == {"value": 1, "unit": "mL"}
    assert converted["steps"][1]["parameters"]["volume"]["value"] == 2
    assert converted["steps"][2]["parameters"]["duration"]["marker"] == "__NOT_REPORTED__"
    assert set(converted["operation_definitions"]) == {"Wash", "Dry"}
    assert all(not definition["execution_supported"] for definition in converted["operation_definitions"].values())
    assert converted["extraction"]["unmapped_actions"] == []
    assert protocol == original and len(runner.calls) == 1
    assert runner.calls[0][0] == "operation_expander"


def test_every_agent_input_is_text_derived_and_invariant_to_ord_poisoning():
    document = source()
    runner = Runner([proposal()])
    complete(document, base(), {}, runner)
    serialized = json.dumps(runner.calls)
    assert "poisoned_ORD" not in serialized and "POISON" not in serialized
    assert "yield_percent" not in serialized and "components" not in serialized
    assert runner.calls[0][1]["source"] == {"id": document["id"], "procedure": TEXT}


def test_all_extension_source_works_without_any_strict_ir():
    text = "The solid was washed with water (2 mL)."
    response = {"steps": [{**proposal()["steps"][1], "evidence": text}], "definitions": {"Wash": WASH}}
    result = complete(source(text), None, {}, Runner([response]))["protocol"]
    assert [step["op"] for step in result["steps"]] == ["Wash"]
    assert result["reagents"] == [] and result["source_text"] == text


def test_existing_contract_is_reused_from_hash_keyed_registry_without_new_definition():
    wash, dry = normalize_definition("Wash", WASH), normalize_definition("Dry", DRY)
    registry = {"extension_operations": {wash["semantic_sha256"]: wash, dry["semantic_sha256"]: dry}}
    response = proposal()
    response["definitions"] = {}
    runner = Runner([response])
    result = complete(source(), base(), registry, runner)
    assert set(result["protocol"]["operation_definitions"]) == {"Wash", "Dry"}
    assert len(runner.calls[0][1]["extension_definitions"]) == 2


def test_new_contract_version_does_not_modify_registry_or_union_parameter_sets():
    older = normalize_definition("Wash", {**WASH, "description": "Wash material with a liquid.",
                                         "parameters": {"liquid": {"type": "string", "required": True}}})
    registry = {"extension_operations": {older["semantic_sha256"]: older}}
    before = copy.deepcopy(registry)
    result = complete(source(), base(), registry, Runner([proposal()]))["protocol"]
    assert result["operation_definitions"]["Wash"]["semantic_sha256"] != older["semantic_sha256"]
    assert registry == before


def test_known_core_metadata_and_reagent_identifiers_survive_inserted_extensions():
    protocol = base()
    protocol["reagents"][0]["id"] = "stable_water"
    protocol["steps"][0]["reagent"] = "stable_water"
    protocol["steps"][0]["meta"]["review_trace"] = "prior_source_check"
    result = complete(source(), protocol, {}, Runner([proposal()]))["protocol"]
    assert result["steps"][0]["reagent"] == "stable_water"
    assert result["steps"][0]["meta"]["review_trace"] == "prior_source_check"


@pytest.mark.parametrize("mutation", ["invented_quantity", "missing_quantity", "invented_string", "borrow_other_step",
                                      "change_core", "drop_core", "drop_dry", "reorder", "generic", "core_shadow"])
def test_repair_preserves_facts_and_actions_before_accepting(mutation):
    invalid, valid = proposal(), proposal()
    if mutation == "invented_quantity":
        invalid["steps"][1]["parameters"]["volume"]["value"] = 999
    elif mutation == "missing_quantity":
        invalid["steps"][1]["parameters"]["volume"] = missing_parameter(WASH_QUOTE)
    elif mutation == "invented_string":
        invalid["steps"][1]["parameters"]["liquid"]["value"] = "ethanol"
    elif mutation == "borrow_other_step":
        invalid["steps"][1]["parameters"]["volume"] = {"value": 1, "unit": "mL", "evidence": ADD["evidence"]}
    elif mutation == "change_core":
        invalid["steps"][0]["amount"]["value"] = 2
    elif mutation == "drop_core":
        invalid["steps"].pop(0)
    elif mutation == "drop_dry":
        invalid["steps"].pop()
    elif mutation == "reorder":
        invalid["steps"] = list(reversed(invalid["steps"]))
    elif mutation == "generic":
        invalid["definitions"]["RawInstruction"] = {**invalid["definitions"].pop("Wash"), "name": "RawInstruction"}
        invalid["steps"][1]["op"] = "RawInstruction"
    elif mutation == "core_shadow":
        invalid["definitions"]["Add"] = {**WASH, "name": "Add"}
    runner = Runner([invalid, valid])
    result = complete(source(), base(), {}, runner)
    assert result["notes"]["attempts"] == 2
    assert runner.calls[1][1]["repair"]["previous_proposal"] == invalid
    assert runner.calls[1][1]["repair"]["validation_errors"]


def test_invalid_completion_fails_after_two_bounded_repairs():
    response = proposal()
    response["steps"][1]["parameters"]["volume"]["value"] = 999
    runner = Runner([response])
    with pytest.raises(ValueError, match="Operation completion failed"):
        complete(source(), base(), {}, runner)
    assert len(runner.calls) == 3


def test_broad_wash_quote_cannot_cover_an_unrepresented_add():
    text = "water (1 mL) was added and the solid was washed with water (2 mL)."
    response = {"steps": [{**proposal()["steps"][1], "evidence": text}], "definitions": {"Wash": WASH}}
    with pytest.raises(ValueError, match="unrepresented"):
        complete(source(text), None, {}, Runner([response]))


def test_same_atom_supports_other_values_without_new_operation_name():
    text = "The solid was washed with ethanol (3 mL)."
    response = {"steps": [{"op": "Wash", "evidence": text, "parameters": {
        "liquid": {"value": "ethanol", "evidence": "ethanol"},
        "volume": {"value": 3, "unit": "mL", "evidence": "ethanol (3 mL)"}}}], "definitions": {"Wash": WASH}}
    converted = complete(source(text), None, {}, Runner([response]))["protocol"]
    assert list(converted["operation_definitions"]) == ["Wash"]
    assert converted["operation_definitions"]["Wash"]["semantic_sha256"] == normalize_definition("Wash", WASH)["semantic_sha256"]


def test_quench_is_not_restricted_to_a_fixed_extension_operation_list():
    text = "The mixture was quenched with water."
    definition = {"name": "Quench", "description": "Quench a reactive mixture with a stated reagent.",
                  "parameters": {"reagent": {"type": "string", "required": True},
                                 "volume": {"type": "quantity", "required": True, "dimension": "volume", "unit": "mL"}},
                  "effects": ["reactive_material_terminated"]}
    response = {"steps": [{"op": "Quench", "evidence": text, "parameters": {
        "reagent": {"value": "water", "evidence": "water"}, "volume": missing_parameter(text)}}],
        "definitions": {"Quench": definition}}
    result = complete(source(text), None, {}, Runner([response]))["protocol"]
    assert result["steps"][0]["op"] == "Quench"
    assert result["steps"][0]["parameters"]["volume"]["marker"] == "__NOT_REPORTED__"


def test_analytical_observation_does_not_require_an_operation_expander_call():
    document = source("Add water. TLC analysis showed completion.")
    protocol = build_ir(document, {"steps": [{"op": "Add", "reagent": "water", "evidence": "Add water."}],
        "unmapped_actions": [{"evidence": "TLC analysis showed completion.", "reason": "analysis"}]}, {})
    runner = Runner([])
    result = complete(document, protocol, {}, runner)
    assert result["notes"]["agent_called"] is False and not runner.calls
    assert not result["protocol"]["extraction"]["unmapped_actions"]
    assert result["protocol"]["extraction"]["source_observations"][0]["evidence"] == "TLC analysis showed completion."


def test_abandoned_reaction_note_is_preserved_as_observation_instead_of_missing_action():
    document = source("Add water. Reaction abandoned.")
    protocol = build_ir(document, {"steps": [{"op": "Add", "reagent": "water", "evidence": "Add water."}],
        "unmapped_actions": [{"evidence": "Reaction abandoned.", "reason": "reported result"}]}, {})
    result = complete(document, protocol, {}, Runner([]))["protocol"]
    assert result["extraction"]["source_observations"][0]["evidence"] == "Reaction abandoned."
    assert not result["extraction"]["unmapped_actions"]


def test_inert_enclosure_operation_preserves_canonical_gas_via_literal_formula():
    text = "under N2 atmosphere"
    document = source(text)
    protocol = build_ir(document, {"steps": [{"op": "Atmosphere", "gas": "nitrogen", "mode": "environment", "evidence": text}],
                                  "unmapped_actions": [{"evidence": text}]}, {})
    definition = {"description": "Handle materials in an explicitly reported inert enclosure",
        "parameters": {"gas": {"type": "string", "required": True}}, "effects": ["atmosphere_established"]}
    response = {"steps": [{"op": "HandleInert", "parameters": {"gas": {"value": "N2", "evidence": text}}, "evidence": text}],
                "definitions": {"HandleInert": definition}}
    result = complete(document, protocol, {}, Runner([response]))["protocol"]
    assert result["steps"][0]["parameters"]["gas"]["value"] == "N2"
