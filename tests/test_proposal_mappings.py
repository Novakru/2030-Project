"""Registered expressions work in the real extraction seam, before legacy grammar."""
import copy

import pytest

from mosaic.protocol.normalization import normalize_protocol
from mosaic.chemistry import ChemistryDomain
from mosaic.completion import complete
from mosaic.proposal_mappings import resolve_proposal


class Runner:
    def __init__(self, proposal):
        self.proposal, self.calls = proposal, 0

    def model_call(self, role, system, payload):
        self.calls += 1
        return {"data": copy.deepcopy(self.proposal), "model": "explicit-test-double"}


@pytest.mark.parametrize("expression,quote", [("加入", "Water (1 mL) was added."), ("charge", "Water (1 mL) was charged.")])
def test_registered_add_words_do_not_require_model_repair_or_a_new_definition(expression, quote):
    proposal = {"steps": [{"op": expression, "reagent": "Water", "alias": "Water", "evidence": quote,
                           "amount": {"value": 1, "unit": "mL"}}]}
    runner = Runner(proposal)
    result = complete({"id": "source", "procedure": quote}, None, {}, runner)["protocol"]
    canonical = normalize_protocol(result)
    assert runner.calls == 1
    assert canonical["steps"][0]["op"] == "Add"
    assert canonical["steps"][0]["meta"]["source_expression"]["expression"] == expression
    assert proposal["steps"][0]["op"] == expression


@pytest.mark.parametrize("expression,method,quote", [
    ("shake", "shake", "The mixture was shaken for 30 seconds."),
    ("vortex", "vortex", "The mixture was vortexed for 30 seconds.")])
def test_contextual_mixing_words_preserve_method_in_production_completion(expression, method, quote):
    proposal = {"steps": [{"op": expression, "object_role": "material_or_contents", "evidence": quote,
                           "parameters": {"duration_s": {"value": 30, "unit": "s", "evidence": "30 seconds"}}}]}
    runner = Runner(proposal)
    result = complete({"id": "source", "procedure": quote}, None, {}, runner)["protocol"]
    canonical = normalize_protocol(result)
    assert runner.calls == 1
    assert canonical["steps"][0]["op"] == "Mix"
    assert canonical["steps"][0]["parameters"]["method"]["value"] == method


def test_known_composition_is_not_treated_as_an_ordinary_heat_alias():
    quote = "The mixture was heated at 70 C and stirred for 30 seconds."
    runner = Runner({"steps": [{"op": "加热并搅拌", "evidence": quote, "temp_C": 70, "duration_s": 30}]})
    result = complete({"id": "source", "procedure": quote}, None, {}, runner)["protocol"]
    canonical = normalize_protocol(result)
    assert [step["op"] for step in canonical["steps"]] == ["Heat", "Mix"]
    assert canonical["temporal_relations"][0]["relation"] == "same_interval"


def test_source_units_are_converted_before_independent_core_grounding():
    quote = "The mixture was stirred for 2 min."
    runner = Runner({"steps": [{"op": "搅拌", "evidence": quote, "parameters": {
        "duration_s": {"value": 2, "unit": "min", "evidence": "2 min"}}}]})
    result = complete({"id": "source", "procedure": quote}, None, {}, runner)["protocol"]
    assert result["steps"][0]["duration_s"] == 120


def test_unknown_or_ambiguous_surface_forms_stay_unresolved_without_shape_repair():
    source = {"steps": [{"op": "shake", "parameters": {"duration_s": -5}}]}
    result, traces = resolve_proposal(source, {})
    assert result == source and traces == {}


def test_alias_adapter_cannot_hide_a_reported_quantity_behind_a_missing_marker():
    quote = "The mixture was shaken for 30 seconds."
    proposal = {"steps": [{"op": "shake", "object_role": "material_or_contents", "evidence": quote,
        "parameters": {"duration_s": {"status": "not_reported", "marker": "__NOT_REPORTED__", "raw": None, "evidence": quote}}}]}
    with pytest.raises(ValueError, match="(?:reported|explicit|quantity)"):
        complete({"id": "source", "procedure": quote}, None, {}, Runner(proposal))


def test_initial_extractor_uses_the_same_deterministic_core_alias_adapter():
    quote = "Water (1 mL) was added."
    class Client:
        calls = 0
        def complete(self, system, prompt, cache=True):
            self.calls += 1
            return {"data": {"steps": [{"op": "加入", "evidence": quote, "reagent": "Water", "alias": "Water",
                                        "amount": {"value": 1, "unit": "mL"}}]}, "model": "test-double"}
    class ExtractRunner:
        def extraction_client(self):
            return client
    client = Client()
    result = ChemistryDomain().extract({"id": "source", "procedure": quote}, ExtractRunner(), critique=False, mapping=False)
    assert client.calls == 1
    assert result["protocol"]["steps"][0]["meta"]["source_expression"]["expression"] == "加入"


def test_canonical_action_needs_no_redundant_definition_or_curator_roundtrip():
    quote = "Dissolve the solid in water (2 mL)."
    proposal = {"steps": [{"op": "Dissolve", "evidence": quote, "parameters": {
        "solvent": {"value": "water", "evidence": "water"},
        "volume": {"value": 2, "unit": "mL", "evidence": "water (2 mL)"}}}]}
    result = complete({"id": "source", "procedure": quote}, None, {}, Runner(proposal))["protocol"]
    canonical = normalize_protocol(result)
    assert canonical["steps"][0]["op"] == "Dissolve"
    assert not canonical["normalization"]["unresolved"]


def test_explicit_unknown_contract_cannot_be_ignored_by_canonical_name_adapter():
    proposal = {"steps": [{"op": "Dissolve", "evidence": "Dissolve the solid."}],
                "definitions": {"Dissolve": {"description": "A distinct proposed meaning."}}}
    resolved, traces = resolve_proposal(proposal, {})
    assert resolved == proposal and traces == {}


def test_core_typed_containers_and_reported_qualifiers_preserve_values():
    proposal = {"steps": [{"op": "Stir", "evidence": "Stir at room temperature for 2 min.", "parameters": {
        "duration_s": {"value": 120, "unit": "s"}, "temperature_condition": "room temperature"}}]}
    resolved, traces = resolve_proposal(proposal, {})
    assert resolved["steps"][0]["op"] == "MappedMix"
    assert resolved["steps"][0]["parameters"]["temperature_condition"]["value"] == "room temperature"
    assert resolved["steps"][0]["parameters"]["duration_s"]["value"] == 120
    assert traces[0]["expression"] == "Stir"


def test_known_gas_formula_is_a_spelling_mapping_and_conflicting_containers_fail():
    resolved, _ = resolve_proposal({"steps": [{"op": "Atmosphere", "evidence": "under N2", "parameters": {
        "gas": "N2", "mode": "environment"}}]}, {})
    assert resolved["steps"][0]["gas"] == "nitrogen"
    with pytest.raises(ValueError, match="Conflicting"):
        resolve_proposal({"steps": [{"op": "Stir", "duration_s": 10, "parameters": {"duration_s": 20}}]}, {})
