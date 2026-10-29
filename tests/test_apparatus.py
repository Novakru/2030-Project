"""Source-scale regressions; fixture records are not experimental observations."""
import copy

from mosaic.protocol.apparatus import source_apparatus
from mosaic.protocol.xdl import bind_hardware


def subject(text="a 5.0 mL wheaton microreactor was charged with solvent (1.0 mL)"):
    return {"id": "fixture", "raw_sha256": "fixture-hash", "source": {"url": "https://example.test/procedure"},
            "steps": [{"id": "add", "op": "Add", "vessel": "reactor", "reagent": "solvent",
                       "amount": {"value": 1, "unit": "mL"}, "meta": {"stage": "reaction", "evidence": text}}],
            "reagents": [{"id": "solvent", "name": "water", "role": "SOLVENT"}]}


def test_workup_flask_does_not_replace_the_reaction_microreactor():
    p = subject()
    p["steps"].append({"id": "workup", "op": "Evaporate", "vessel": "reactor",
                       "meta": {"stage": "workup", "evidence": "Transferred to a 100 mL round-bottom flask"}})
    assert source_apparatus(p)[0]["params"]["capacity_mL"] == 5


def test_reviewed_override_remains_authoritative_and_source_is_retained():
    p = subject()
    original = copy.deepcopy(p)
    bind_hardware(p, configuration={"nodes": {"reactor": "pyrex_rb_4320a_50"}, "edges": [], "bindings": {}})
    assert p["hardware"]["nodes"]["reactor"]["params"]["capacity_mL"] == 50
    assert p["hardware"]["source_apparatus"]["params"]["capacity_mL"] == 5
    assert p["steps"] == original["steps"]
