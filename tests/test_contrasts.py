import copy

from protocol_risk.contrasts import pair_groups
from protocol_risk.yields import target_yield


def record(name, yield_percent, catalyst="[Pd]", amount=1, solvent="CO", temperature=60):
    raw = {"reaction_id": name, "inputs": {
        "substrate": {"components": [{"reaction_role": "REACTANT", "identifiers": [{"type": "SMILES", "value": "CCBr"}], "amount": {"moles": {"units": "MILLIMOLE", "value": 1}}}]},
        "catalyst": {"components": [{"reaction_role": "CATALYST", "identifiers": [{"type": "SMILES", "value": catalyst}], "amount": {"moles": {"units": "MILLIMOLE", "value": amount}}}]},
        "solvent": {"components": [{"reaction_role": "SOLVENT", "identifiers": [{"type": "SMILES", "value": solvent}], "amount": {"volume": {"units": "MILLILITER", "value": 2}}}]}},
        "conditions": {"temperature": {"setpoint": {"units": "CELSIUS", "value": temperature}}},
        "outcomes": [{"reaction_time": {"units": "HOUR", "value": 1}, "products": [{"is_desired_product": True, "identifiers": [{"type": "SMILES", "value": "CCO"}], "measurements": [{"type": "YIELD", "percentage": {"value": yield_percent}}]}]}]}
    value, evidence = target_yield(raw)
    return {"id": name, "raw": raw, "yield_percent": value, "yield_evidence": evidence,
            "raw_sha256": "test_" + name, "source": {"dataset_id": "same_study"}}


def test_catalyst_contrast_requires_all_other_recorded_conditions_equal():
    good, bad = record("good", 80), record("bad", 2, catalyst="[Ni]")
    before = copy.deepcopy([good, bad])
    contrasts = list(pair_groups([good, bad]))
    assert [c["risk_hypothesis"] for c in contrasts] == ["C3"]
    assert contrasts[0]["benchmark_eligible"] is False
    assert [good, bad] == before
    bad["raw"]["conditions"]["temperature"]["setpoint"]["value"] = 100
    assert list(pair_groups([good, bad])) == []


def test_successful_replicate_of_failure_setting_disqualifies_it():
    rows = [record("good", 80), record("bad", 2, catalyst="[Ni]"), record("conflict", 70, catalyst="[Ni]")]
    assert list(pair_groups(rows)) == []


def test_intermediate_replicate_is_not_hidden_by_threshold_filtering():
    rows = [record("good", 80), record("bad", 2, catalyst="[Ni]"), record("middle", 20, catalyst="[Ni]")]
    assert list(pair_groups(rows)) == []


def test_quantity_change_is_c4_and_not_identity_change():
    pairs = list(pair_groups([record("good", 80), record("bad", 2, amount=0.1)]))
    assert [c["risk_hypothesis"] for c in pairs] == ["C4"]


def test_solvent_change_is_c1_when_recorded_amounts_are_equal():
    pairs = list(pair_groups([record("good", 80), record("bad", 2, solvent="CCO")]))
    assert [c["risk_hypothesis"] for c in pairs] == ["C1"]


def test_different_study_or_assay_is_not_a_matched_contrast():
    good, bad = record("good", 80), record("bad", 2, catalyst="[Ni]")
    bad["source"]["dataset_id"] = "other_study"
    assert list(pair_groups([good, bad])) == []
    bad["source"]["dataset_id"] = "same_study"
    bad["raw"]["outcomes"][0]["analyses"] = {"new_assay": {"type": "NMR"}}
    assert list(pair_groups([good, bad])) == []


def test_temperature_and_time_contrasts_have_their_own_factor():
    good, bad = record("good", 80), record("bad", 2, temperature=20)
    assert [c["risk_hypothesis"] for c in pair_groups([good, bad])] == ["C2"]
    bad = record("bad", 2)
    bad["raw"]["outcomes"][0]["reaction_time"]["value"] = 0.1
    assert [c["risk_hypothesis"] for c in pair_groups([good, bad])] == ["C6"]


def test_missing_chemical_identity_cannot_prove_equal_other_conditions():
    good, bad = record("good", 80), record("bad", 2, catalyst="[Ni]")
    for row in (good, bad):
        row["raw"]["inputs"]["substrate"]["components"][0]["identifiers"] = []
    assert list(pair_groups([good, bad])) == []


def test_different_publications_in_one_dataset_cannot_form_a_contrast():
    good, bad = record("good", 80), record("bad", 2, catalyst="[Ni]")
    good["raw"]["provenance"] = {"doi": "10.example/study_a"}
    bad["raw"]["provenance"] = {"doi": "10.example/study_b"}
    assert list(pair_groups([good, bad])) == []
