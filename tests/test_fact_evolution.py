import copy

import pytest

from mosaic.fact_binding import bind_facts
from mosaic.fact_evolution import maintain_facts_library
from mosaic.fact_xdl import compile_facts
from mosaic.evaluation import check_conservation
from mosaic.facts import validate_facts
from mosaic.registry import Registry
from tests.facts_fixture import TEXT, graph


class Curator:
    def __init__(self, proposal):
        self.proposal = proposal
        self.calls = 0

    def model_call(self, role, system, payload):
        self.calls += 1
        assert role == "library_curator"
        observation = payload["unknown_mentions"][0]
        return {"data": {"proposals": [{"observation_id": observation["observation_id"], **copy.deepcopy(self.proposal)}]}}


def equipment_case():
    text = TEXT.replace("microreactor", "Schlenk tube")
    value = graph()
    value["entities"][1].update(name="Schlenk tube", expression="Schlenk tube")
    for evidence in value["evidence"]:
        evidence["quote"] = evidence["quote"].replace("microreactor", "Schlenk tube")
    return validate_facts(value, text), text


def equipment_proposal():
    return {"target_id": "equipment.schlenk_tube", "considered": ["equipment.flask"],
            "counterexample": "An unspecified flask does not establish an inert gas sidearm.", "defaults": {},
            "new_entry": {"name": "SchlenkTube", "category_id": "equipment.reaction_container", "legacy_kind": "schlenk_tube",
                          "capabilities": ["material_containment", "gas_handling"], "configuration_parameters": {}}}


def test_new_equipment_is_admitted_then_same_facts_rebound_without_extraction():
    facts, text = equipment_case()
    before = copy.deepcopy(facts)
    curator = Curator(equipment_proposal())
    registry, report = maintain_facts_library(Registry(), {"source": {"facts": facts}}, {"source": text}, curator)
    binding = bind_facts(facts, registry.snapshot)
    assert not binding["unresolved"] and curator.calls == 1
    assert binding["equipment"]["reactor"]["subtype_id"] == "equipment.schlenk_tube"
    output = compile_facts(facts, binding, text=text)
    assert 'type="schlenk_tube"' in output["xml"] and "equipment.schlenk_tube" not in output["xml"]
    assert check_conservation(facts, binding, output)["passed"]
    assert facts == before and report["facts_reextracted"] == 0
    # A second source reuses admission without another curator call.
    _, report = maintain_facts_library(registry, {"different_source": {"facts": facts}}, {"different_source": text}, curator)
    assert not report["actions"] and curator.calls == 1


@pytest.mark.parametrize("alter", [
    lambda p: p["new_entry"].update(params={"pressure_bar": 100}),
    lambda p: p["new_entry"].update(configuration_parameters={"capacity": {"type": "number", "default": 50}}),
    lambda p: p.update(considered=["equipment.unknown"]),
    lambda p: p.update(target_id="bad id"),
])
def test_equipment_proposals_are_transactional_and_bounded(alter):
    facts, text = equipment_case()
    proposal = equipment_proposal()
    alter(proposal)
    curator, original = Curator(proposal), Registry()
    evolved, report = maintain_facts_library(original, {"source": {"facts": facts}}, {"source": text}, curator)
    assert evolved.revision == original.revision and report["rejected"] and curator.calls == 2


def test_novel_operation_then_alias_reuse_needs_no_source_code_change():
    text, facts = TEXT.replace("stirred", "centrifuged"), graph()
    facts["events"][1].update(expression="centrifuge", action_surface="centrifuged")
    facts["evidence"][-1]["quote"] = facts["evidence"][-1]["quote"].replace("stirred", "centrifuged")
    facts = validate_facts(facts, text)
    proposal = {"target_id": "op.centrifuge", "considered": ["op.mix", "op.separate"], "defaults": {},
                "counterexample": "Mixing alone does not describe separation by centrifugal acceleration.",
                "new_entry": {"name": "Centrifuge", "kind": "action", "domain": "general", "description": "Centrifuge a sample under reported conditions.",
                    "parameters": {"duration": {"type": "quantity", "dimension": "time"}},
                    "preconditions": ["Sample location may remain unknown."], "effects": ["Exposes sample to centrifugal acceleration."],
                    "capabilities": ["centrifugation"]}}
    original = Registry()
    evolved, report = maintain_facts_library(original, {"source": {"facts": facts}}, {"source": text}, Curator(proposal))
    assert not report["rejected"]
    binding = bind_facts(facts, evolved.snapshot)
    assert binding["events"]["mix"]["operation_id"] == "op.centrifuge"
    output = compile_facts(facts, binding, text=text)
    assert "<Centrifuge " in output["xml"] and check_conservation(facts, binding, output)["passed"]
    baseline = validate_facts(graph(), TEXT)
    old_binding = bind_facts(baseline, evolved.snapshot)
    assert check_conservation(baseline, old_binding, compile_facts(baseline, old_binding, text=TEXT))["passed"]


def test_alias_to_wrong_or_colliding_concept_is_rejected():
    facts, text = equipment_case()
    proposal = equipment_proposal()
    proposal.update(target_id="equipment.microreactor", new_entry=None)
    # This semantic suggestion is NOT provably wrong by name alone: it remains
    # silver. A generic or conflicting existing alias, however, is rejected.
    facts["entities"][1]["expression"] = "vessel"
    curator = Curator(proposal)
    _, report = maintain_facts_library(Registry(), {"source": {"facts": facts}}, {"source": text}, curator)
    assert report["rejected"]
