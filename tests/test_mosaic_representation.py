import copy

import pytest

from mosaic.evidence import SourceSpan
from mosaic.evolution import CurationPolicy
from mosaic.registry import Registry
from mosaic.representation import expand_plan, trusted_representations


SOURCE = "water (1 mL) was added and stirred for 60 s."


def admitted_registry():
    registry = Registry()
    proposal = {"domain": "chemistry.batch/2", "name": "DoseThenStir", "origins": ["a"],
                "contract": {"parameters": {"vessel": "identifier", "reagent": "literal_name",
                                            "amount": "quantity", "duration_s": "positive_time"},
                             "effects": ["material_added", "stirring_elapsed"], "guards": ["duration_s > 0"]},
                "expansion": ["Add", "Stir"],
                "parameter_mapping": {"0.vessel": "vessel", "0.reagent": "reagent", "0.amount": "amount",
                                      "1.vessel": "vessel", "1.duration_s": "duration_s"},
                "witnesses": [{"parameters": {"vessel": "reactor", "reagent": "water",
                                               "amount": {"value": 1, "unit": "mL"}, "duration_s": 60},
                               "steps": [{"op": "Add", "vessel": "reactor", "reagent": "water", "amount": {"value": 1, "unit": "mL"}},
                                         {"op": "Stir", "vessel": "reactor", "duration_s": 60}]}]}
    template = {key: proposal[key] for key in ("contract", "expansion", "parameter_mapping")}
    policy = CurationPolicy("chemistry.batch/2", {"DoseThenStir": template})
    return registry.evolve([{"action": "admit_macro", "proposal": proposal,
                             "evidence": [SourceSpan.locate("a", SOURCE, SOURCE).to_dict()]}],
                            expected_revision=registry.revision, sources={"a": SOURCE}, policy=policy)


def plan():
    return {"steps": [{"op": "DoseThenStir", "vessel": "reactor", "reagent": "water",
                       "amount": {"value": 1, "unit": "mL"}, "duration_s": 60,
                       "stage": "workup", "evidence": SOURCE}],
            "uncertainties": ["source does not state stirring speed"],
            "unmapped_actions": [], "extension_context": {"unknowns": ["pressure rating"]}}


def test_admitted_macro_mechanically_expands_and_revalidates_literal_evidence():
    registry, original = admitted_registry(), plan()
    before = copy.deepcopy(original)
    result = expand_plan(original, registry, source={"procedure": SOURCE})
    assert [step["op"] for step in result["steps"]] == ["Add", "Stir"]
    assert all(step["evidence"] == SOURCE and step["stage"] == "workup" for step in result["steps"])
    assert result["steps"][0]["amount"] == {"value": 1, "unit": "mL"}
    assert result["uncertainties"] == original["uncertainties"]
    assert result["extension_context"] == original["extension_context"] and original == before


@pytest.mark.parametrize("dimension,value", [("target_pH", 7), ("temp_C", 70), ("rpm", 500)])
def test_extra_physical_dimension_cannot_be_dropped_during_macro_expansion(dimension, value):
    original = plan()
    original["steps"][0][dimension] = value
    with pytest.raises(ValueError, match="unmapped dimensions"):
        expand_plan(original, admitted_registry())


def test_missing_or_invented_amount_blocks_macro_instead_of_synthesizing_one():
    original = plan()
    del original["steps"][0]["amount"]
    with pytest.raises(ValueError, match="source parameters"):
        expand_plan(original, admitted_registry())
    original = plan()
    original["steps"][0]["amount"]["value"] = 10
    with pytest.raises(ValueError, match="source evidence"):
        expand_plan(original, admitted_registry(), source={"procedure": SOURCE})


def test_candidate_or_uncertified_macro_never_expands():
    registry = admitted_registry()
    next(iter(registry.snapshot["representations"].values())).pop("certificate")
    with pytest.raises(ValueError, match="certificate"):
        expand_plan(plan(), registry)
    registry = admitted_registry()
    registry.snapshot["representation_candidates"] = list(registry.snapshot["representations"].values())
    registry.snapshot["representations"] = {}
    assert not trusted_representations(registry)["macros"]
    with pytest.raises(ValueError, match="no admitted representation"):
        expand_plan(plan(), registry)


def test_certificate_cannot_hide_modified_mapping_or_unsupported_expansion():
    registry = admitted_registry()
    next(iter(registry.snapshot["representations"].values()))["parameter_mapping"]["1.duration_s"] = "amount"
    with pytest.raises(ValueError, match="certificate"):
        trusted_representations(registry)


def test_alias_resolves_only_identical_contracts_and_keeps_source_context():
    registry = Registry()
    registry.snapshot["operations"]["Pause"] = copy.deepcopy(registry.snapshot["operations"]["Wait"])
    registry.snapshot["aliases"]["Pause"] = "Wait"
    original = {"steps": [{"op": "Pause", "duration_s": 60, "evidence": "wait for 60 s", "stage": "reaction"}],
                "uncertainties": ["vessel unknown"], "unmapped_actions": []}
    output = expand_plan(original, registry, source={"procedure": "wait for 60 s"})
    assert output["steps"][0] == {**original["steps"][0], "op": "Wait"}
    registry.snapshot["operations"]["Pause"]["risks"] = []
    with pytest.raises(ValueError, match="full contract"):
        trusted_representations(registry)


def test_alias_cycle_is_explicit_error():
    registry = Registry()
    registry.snapshot["operations"]["Pause"] = copy.deepcopy(registry.snapshot["operations"]["Wait"])
    registry.snapshot["aliases"] = {"Pause": "Wait", "Wait": "Pause"}
    with pytest.raises(ValueError, match="cycle"):
        trusted_representations(registry)
