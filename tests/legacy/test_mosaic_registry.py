import copy

import pytest

from mosaic.evidence import SourceSpan
from mosaic.registry import Registry, minimum_cover


def test_unknown_capacity_cannot_cover_a_required_reactor():
    result = minimum_cover(["capacity", "temperature"], [
        {"device": "vial", "requirement": "capacity", "known": False, "evidence_ids": ["source"]},
        {"device": "heater", "requirement": "temperature", "known": True, "evidence_ids": ["datasheet"]}])
    assert result["status"] == "incomplete" and result["uncovered"] == ["capacity"]


def test_exact_cover_finds_one_device_instead_of_greedy_two():
    witnesses = [{"device": name, "requirement": r, "known": True, "evidence_ids": ["literal-source"]}
                 for name, requirements in {"a": ["r1"], "b": ["r2"], "c": ["r1", "r2"]}.items() for r in requirements]
    result = minimum_cover(["r1", "r2"], witnesses)
    assert result["devices"] == ["c"] and result["optimal"]


def test_automatic_evolution_keeps_unidentified_models_and_never_invents_review():
    text = "a 5 mL microreactor was used"
    citation = SourceSpan.locate("paper", text, text).to_dict()
    original = Registry()
    observation = {"identity": {"manufacturer": "WHEATON", "model": None}, "params": {"capacity_mL": 5}, "verified": False}
    change = {"action": "observe_device", "device": observation, "evidence": [citation]}
    evolved = original.evolve([change], expected_revision=original.revision, sources={"paper": text})
    assert not original.snapshot["observations"]
    assert evolved.compact_device_observations()["unidentified_observations"][0]["params"]["capacity_mL"] == 5
    observation["verified"] = True
    with pytest.raises(ValueError, match="human verification"):
        original.evolve([change], expected_revision=original.revision, sources={"paper": text})
