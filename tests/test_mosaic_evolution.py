"""Admission tests use explicit contracts, not assertions about model accuracy."""
import copy
from types import SimpleNamespace

import pytest

from mosaic.evidence import SourceSpan
from mosaic.evolution import CurationPolicy, maintain_library
from mosaic.registry import Registry


class Curator:
    def __init__(self, proposals=(), error=None):
        self.proposals, self.error, self.calls = list(proposals), error, []

    def model_call(self, role, system, payload):
        self.calls.append((role, system, payload))
        if self.error:
            raise self.error
        return {"data": {"proposals": copy.deepcopy(self.proposals)}, "model": "test-curator"}


def observed(text, identifier, *, kind="operation", **fields):
    return {"kind": kind, "observation_id": identifier,
            "evidence": [SourceSpan.locate(identifier, text, text).to_dict()], **fields}


def evolve(observations, proposals=(), *, registry=None, domain=None, runner=None):
    sources = {o["evidence"][0]["source_id"]: o["evidence"][0]["quote"] for o in observations}
    return maintain_library(registry or Registry(), observations, sources=sources,
                            runner=runner or Curator(proposals),
                            domain=domain or SimpleNamespace(name="chemistry.batch/2"))


def test_semantic_candidate_merges_source_phrases_without_executable_claim():
    observations = [observed("centrifuged at 1000 g", "a", source_action="centrifuged"),
                    observed("spun down for ten minutes", "b", source_action="spun down")]
    proposal = {"action": "cluster_operation", "origins": ["a", "b"], "name": "Centrifuge",
                "reason": "Neither settling nor filtering represents centrifugal separation.",
                "contract": {"effect": "centrifugal_phase_separation", "parameters": ["rcf_g", "duration_s"]}}
    original = Registry()
    result, report = evolve(observations, [proposal], registry=original)
    candidate = result.snapshot["operation_candidates"][0]
    assert candidate["name"] == "Centrifuge" and candidate["origins"] == ["a", "b"]
    assert len(candidate["evidence"]) == 2
    assert candidate["status"] == "candidate_not_executable"
    assert "Centrifuge" not in result.snapshot["operations"]
    assert not original.snapshot["operation_candidates"]
    assert report["retryable_source_ids"] == []


def test_new_evidence_aggregates_into_existing_semantic_candidate_idempotently():
    first = observed("centrifuged at 1000 g", "a", source_action="centrifuged")
    second = observed("centrifuged for five minutes", "b", source_action="centrifuged")
    proposal = {"action": "cluster_operation", "origins": ["a"], "name": "Centrifuge",
                "reason": "New separation effect", "contract": {"effect": "separation"}}
    registry, _ = evolve([first], [proposal])
    proposal.update(origins=["b"], name="centrifuge")
    registry, _ = evolve([second], [proposal], registry=registry)
    again, _ = evolve([second], [proposal], registry=registry)
    assert len(registry.snapshot["operation_candidates"]) == 1
    assert set(registry.snapshot["operation_candidates"][0]["origins"]) == {"a", "b"}
    assert again.revision == registry.revision


def test_curator_cannot_invent_observation_ids_or_factual_fields():
    observation = observed("a microreactor was used", "a", kind="device", device={"kind": "microreactor"})
    proposals = [{"action": "cluster_operation", "origins": ["forged"], "name": "Open", "reason": "none"},
                 {"action": "cluster_device", "origins": ["a"], "family": "microreactor",
                  "reason": "same kind", "params": {"pressure_max_bar": 100}}]
    registry, report = evolve([observation], proposals)
    assert len(report["rejected"]) == 2
    assert "pressure_max_bar" not in str(registry.snapshot["observations"])


def test_invalid_evidence_is_not_sent_to_curator():
    observation = observed("Heat to 50 C", "a", op="HeatChill")
    observation["evidence"][0]["quote"] = "Heat to 500 C"
    runner = Curator()
    _, report = maintain_library(Registry(), [observation], sources={"a": "Heat to 50 C"},
                                runner=runner, domain=SimpleNamespace(name="chemistry.batch/2"))
    assert not runner.calls and len(report["rejected"]) == 1


def test_budget_failure_preserves_all_observations_and_marks_pending():
    observation = observed("annealed under argon", "a", source_action="anneal")
    registry, report = evolve([observation], runner=Curator(error=ValueError("budget exhausted")))
    assert registry.snapshot["operation_observations"][0]["observation_id"] == "a"
    assert report["curator"]["status"] == "unavailable"
    assert report["pending_observation_ids"] == ["a"]


def test_explicitly_disabled_curator_keeps_evidence_without_fabricating_a_failure():
    observation = observed("annealed under argon", "a", source_action="anneal")
    registry, report = maintain_library(Registry(), [observation], sources={"a": "annealed under argon"},
                                        runner=None, domain=SimpleNamespace(name="materials.solids/1"))
    assert report["curator"]["status"] == "disabled" and not report["rejected"]
    assert report["pending_observation_ids"] == ["a"]
    assert len(registry.snapshot["operation_observations"]) == 1


def test_identical_repeated_observation_is_deduplicated_without_a_false_error():
    observation = observed("add water", "a", op="Add")
    registry, report = evolve([observation, copy.deepcopy(observation)])
    assert not report["rejected"] and len(registry.snapshot["operation_observations"]) == 1


def test_bounded_stratification_does_not_hide_new_operation_after_many_adds():
    observations = [observed("add water " + str(index), "add_" + str(index), op="Add") for index in range(200)]
    observations.append(observed("centrifuged", "novel", source_action="centrifuged"))
    runner = Curator()
    registry, report = evolve(observations, runner=runner)
    assert len(runner.calls) == 4
    selected = [o for _, _, payload in runner.calls for o in payload["observations"]]
    assert any(o["observation_id"] == "novel" for o in selected)
    assert len(registry.snapshot["operation_observations"]) == 201
    assert len(report["pending_observation_ids"]) == 41


def test_identical_contract_alias_is_admitted_but_semantic_loss_is_rejected():
    registry = Registry()
    registry.snapshot["operations"]["Pause"] = copy.deepcopy(registry.snapshot["operations"]["Wait"])
    observation = observed("pause for one minute", "a", op="Wait")
    proposals = [{"action": "alias", "from": "Pause", "to": "Wait", "origins": ["a"],
                  "reason": "Full contracts including state effects and risks are identical."},
                 {"action": "alias", "from": "Filter", "to": "Separate", "origins": ["a"],
                  "reason": "Both separate material."}]
    result, report = evolve([observation], proposals, registry=registry)
    assert result.snapshot["aliases"] == {"Pause": "Wait"}
    assert report["retryable_source_ids"] == ["a"]
    assert len(report["rejected"]) == 1


def macro_proposal():
    return {"action": "macro", "name": "TimedPause", "origins": ["a"], "reason": "Explicit timed pause.",
            "contract": {"parameters": {"duration_s": "positive_time"},
                         "effects": ["elapsed_time"], "guards": ["duration_s > 0"]},
            "expansion": ["Wait"], "parameter_mapping": {"0.duration_s": "duration_s"},
            "witnesses": [{"parameters": {"duration_s": 60}, "steps": [{"op": "Wait", "duration_s": 60}]}]}


def test_macro_stays_candidate_until_domain_has_implemented_contract():
    result, report = evolve([observed("wait for one minute", "a", op="Wait")], [macro_proposal()])
    assert not result.snapshot["representations"]
    assert result.snapshot["representation_candidates"][0]["status"] == "candidate_not_executable"
    assert "No implemented" in report["actions"][-1]["admission_blocker"]


def test_macro_admission_checks_implemented_contract_and_actual_roundtrip():
    proposal = macro_proposal()
    template = {key: copy.deepcopy(proposal[key]) for key in ("contract", "expansion", "parameter_mapping")}
    policy = CurationPolicy("chemistry.batch/2", {"TimedPause": template},
                            canonical_contracts=Registry().snapshot["operations"])
    domain = SimpleNamespace(name=policy.domain, curation_policy=policy)
    observation = observed("wait for one minute", "a", op="Wait")
    result, report = evolve([observation], [proposal], domain=domain)
    admitted = next(iter(result.snapshot["representations"].values()))
    assert admitted["certificate"]["lossless"]
    assert report["retryable_source_ids"] == ["a"]
    proposal["witnesses"][0]["steps"][0]["duration_s"] = 10
    result, report = evolve([observation], [proposal], domain=domain)
    assert not result.snapshot["representations"]
    assert "roundtrip" in report["actions"][-1]["admission_blocker"]


def test_macro_parameter_or_effect_loss_cannot_be_laundered_by_a_model_claim():
    proposal = macro_proposal()
    template = {key: copy.deepcopy(proposal[key]) for key in ("contract", "expansion", "parameter_mapping")}
    domain = SimpleNamespace(name="chemistry.batch/2", curation_policy=CurationPolicy(
        "chemistry.batch/2", {"TimedPause": template}, canonical_contracts=Registry().snapshot["operations"]))
    proposal["contract"]["effects"] = []
    result, report = evolve([observed("wait one minute", "a", op="Wait")], [proposal], domain=domain)
    assert not result.snapshot["representations"]
    assert "implemented domain contract" in report["actions"][-1]["admission_blocker"]


def test_roundtrip_alone_cannot_approve_a_guard_violating_witness():
    proposal = macro_proposal()
    template = {key: copy.deepcopy(proposal[key]) for key in ("contract", "expansion", "parameter_mapping")}
    domain = SimpleNamespace(name="chemistry.batch/2", curation_policy=CurationPolicy(
        "chemistry.batch/2", {"TimedPause": template}, canonical_contracts=Registry().snapshot["operations"]))
    proposal["witnesses"][0] = {"parameters": {"duration_s": -60}, "steps": [{"op": "Wait", "duration_s": -60}]}
    result, report = evolve([observed("wait one minute", "a", op="Wait")], [proposal], domain=domain)
    assert not result.snapshot["representations"]
    assert "guard" in report["actions"][-1]["admission_blocker"]


def test_known_device_family_aggregates_observations_without_extra_core_profiles():
    observations = [observed("a 5 mL microreactor", "a", kind="device", device={"kind": "microreactor", "params": {"capacity_mL": 5}}),
                    observed("a glass microreactor", "b", kind="device", device={"kind": "microreactor"})]
    proposal = {"action": "cluster_device", "origins": ["a", "b"], "family": "microreactor",
                "reason": "Both are source-reported microreactors; flow mode and identity remain unknown."}
    original = Registry()
    result, report = evolve(observations, [proposal], registry=original)
    assert len(result.snapshot["devices"]) == len(original.snapshot["devices"])
    assert result.snapshot["families"]["microreactor"]["origins"] == ["a", "b"]
    assert len(result.compact_device_observations()["unidentified_observations"]) == 2
    assert report["actions"][-1]["status"] == "classification_only"


def test_curator_cannot_reclassify_generic_microreactor_as_known_flow_equipment():
    observation = observed("a microreactor", "a", kind="device", device={"kind": "microreactor"})
    proposal = {"action": "cluster_device", "origins": ["a"], "family": "pump", "reason": "It could be flow."}
    result, report = evolve([observation], [proposal])
    assert "contradicts" in report["rejected"][0]["reason"]
    assert not result.snapshot["families"]["pump"].get("origins")


def test_curator_uses_real_runner_budget_and_replays_without_external_calls(tmp_path):
    from mosaic.agents import AgentRunner
    from mosaic.store import RunStore

    calls = []
    proposal = {"action": "cluster_operation", "origins": ["a"], "name": "Centrifuge",
                "reason": "Centrifugal separation lacks an implemented representation.", "contract": {"effect": "separation"}}

    class Client:
        def complete(self, system, prompt, cache=True):
            calls.append(prompt)
            return {"data": {"proposals": [proposal]}, "model": "fixture-curator", "cache_key": "test"}

    store = RunStore(tmp_path, {"test": "library-curator-replay"})
    runner = AgentRunner(store, models={"library_curator": "fixture-curator"}, max_calls=1, client_factory=lambda model: Client())
    observation = observed("centrifuged", "a", source_action="centrifuged")
    result, report = evolve([observation], runner=runner)
    assert len(calls) == 1 and runner.calls == 1
    assert report["curator"]["model"] == "fixture-curator"

    def forbidden_client(model):
        raise AssertionError("Offline curation must not contact a model")

    offline = AgentRunner(store, models={"library_curator": "fixture-curator"}, max_calls=0,
                          offline=True, client_factory=forbidden_client)
    replay, report = evolve([observation], runner=offline)
    assert replay.revision == result.revision and offline.replayed["library_curator"] == 1
    assert store.verify()


@pytest.mark.parametrize("domain_name,action,contract", [
    ("biology.assay/1", "Centrifuge", {"effect": "centrifugal_separation", "parameters": ["rcf_g", "duration_s"]}),
    ("materials.solids/1", "Anneal", {"effect": "solid_heat_treatment", "parameters": ["ramp", "atmosphere", "substrate"]}),
])
def test_domain_policy_seam_preserves_other_domain_semantics_as_unexecuted_candidates(domain_name, action, contract):
    observation = observed(action.lower() + " specimen", "a", source_action=action)
    proposal = {"action": "cluster_operation", "name": action, "origins": ["a"],
                "reason": "Existing chemistry primitives omit domain-specific dimensions.", "contract": contract}
    result, _ = evolve([observation], [proposal], domain=SimpleNamespace(name=domain_name))
    candidate = result.snapshot["operation_candidates"][0]
    assert candidate["domain"] == domain_name and candidate["contract"] == contract
    assert candidate["status"] == "candidate_not_executable" and action not in result.snapshot["operations"]
