"""Dataset regressions: distinguish source fragments, instantiations and observed facts."""
import copy

import pytest

from protocol_risk.controls import reference
from protocol_risk.io import load_library
from protocol_risk.sop import candidates, recipe_evidence, records, source_text
from protocol_risk.symbolic import concentrated_sulfuric, evaluate
from protocol_risk.xdl import canonical_hash, export_xdl, validate_xdl


def test_remaining_categories_have_distinct_variants_with_honest_parent_diversity():
    parents, negatives = records()
    assert len(parents) == 17 and len(negatives) == 34
    for risk, count, parent_count in (("B2", 12, 1), ("B3", 12, 6), ("B5", 10, 10)):
        group = [r for r in negatives if r["label"]["risk_l2"] == risk]
        assert len(group) == count and len({r["parent_id"] for r in group}) == parent_count
        assert len({canonical_hash(r["protocol"]) for r in group}) == count
        assert all(not r["benchmark_eligible"] for r in group)
    assert all(p["construction"]["observed_experiment"] is False for p in parents if p["origin"] == "instantiated_sop")
    assert all(validate_xdl(r["xdl"]) for r in parents + negatives)


def test_b2_uses_preloaded_pure_dmso_and_only_one_temperature_mutation():
    parent, _, child = next(item for item in candidates() if item[1] == "B2")
    assert parent["initial_contents"]["reactor"][0]["amount"] is None
    assert all(s["op"] != "Add" for s in parent["steps"])
    expected = copy.deepcopy(parent)
    expected["steps"][0]["temp_C"] = child["steps"][0]["temp_C"]
    assert expected == child and evaluate(child).risks == ["B2"]
    assert "30 C is a constructed" in " ".join(parent["construction"]["assumptions"])
    mixed = copy.deepcopy(child)
    mixed["context"]["pure_solvent"] = False
    assert "B2" not in evaluate(mixed).risks
    assert "Analysis initial contents" in export_xdl(child)


def test_b3_does_not_equate_above_flashpoint_with_actual_ignition():
    for parent, risk, child in candidates():
        if risk != "B3":
            continue
        assert evaluate(parent).risks == [] and evaluate(child).risks == ["B3"]
        child["context"]["vapor_exposed"] = False
        assert "B3" not in evaluate(child).risks


def test_acid_fragments_preserve_known_qualifiers_and_unresolved_endpoints():
    for parent, risk, child in candidates():
        if risk != "B5":
            continue
        assert evaluate(parent).risks == [] and evaluate(child).risks == ["B5"]
        acid = parent["reagents"][1]
        assert acid.get("mass_fraction") in (None, 0.96)
        assert parent["unresolved_instructions"] and len(parent["steps"]) == 2
        assert "Unresolved source instruction" in export_xdl(parent)
        assert parent["steps"] == child["steps"][::-1]


def test_unlocated_recipe_values_are_rejected():
    recipe = copy.deepcopy(load_library("sop_recipes.yaml")["acid_dilutions"][0])
    source, text = source_text(recipe["source"])
    recipe["acid_mL"] = 123.456
    with pytest.raises(ValueError, match="volumes not located"):
        recipe_evidence(recipe, source, text)


def test_explicit_dilute_fraction_overrides_a_qualitative_concentrated_annotation():
    reagent = {"chemical": "sulfuric_acid_concentrated", "mass_fraction": 0.1,
               "concentration_evidence": {"qualifier": "concentrated", "source_url": "https://example.test", "source_sha256": "fixture"}}
    assert not concentrated_sulfuric(reagent)
    del reagent["mass_fraction"]
    assert concentrated_sulfuric(reagent)
    reagent["concentration_evidence"].pop("source_sha256")
    assert not concentrated_sulfuric(reagent)


def test_initial_contents_are_counted_and_require_declared_references():
    parent = reference("B2", 0)
    parent["hardware"]["nodes"]["reactor"]["params"]["capacity_mL"] = 20
    parent["initial_contents"] = {"reactor": [{"reagent": "r1", "amount": {"value": 10, "unit": "mL"}}]}
    assert evaluate(parent).risks == ["A1"]  # 10 mL preloaded + 11 mL addition.
    changed = copy.deepcopy(parent)
    changed["initial_contents"]["reactor"][0]["reagent"] = "undeclared"
    assert "D3" in evaluate(changed).risks
    assert canonical_hash(changed) != canonical_hash(parent)
