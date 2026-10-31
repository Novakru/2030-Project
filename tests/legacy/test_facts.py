import copy

import pytest

from mosaic.facts import validate_facts
from mosaic.units import equivalent
from mosaic.fact_binding import bind_facts
from mosaic.fact_xdl import compile_facts
from mosaic.evaluation import check_conservation, score_reference
from mosaic.registry import Registry
from tests.legacy.facts_fixture import TEXT, graph


def compiled():
    facts = validate_facts(graph(), TEXT)
    binding = bind_facts(facts, Registry().snapshot)
    return facts, binding, compile_facts(facts, binding, text=TEXT)


def test_one_typed_quantity_preserves_independent_doses_and_hardware_scope():
    facts, binding, output = compiled()
    assert check_conservation(facts, binding, output)["passed"]
    assert 'mass="24.2 mg"' in output["xml"] and 'amount="0.2 mmol"' in output["xml"]
    assert 'type="microreactor"' in output["xml"]
    assert "__QUALITATIVE__" in output["xml"] and "25" not in output["xml"]
    assert "nominal_volume" not in output["xml"]
    assert output["hardware_config"]["reactor"]["properties"]


@pytest.mark.parametrize("mutation", ["dose", "reagent", "subtype", "scope", "time", "event", "hardware_config"])
def test_independent_checker_detects_real_output_losses(mutation):
    facts, binding, output = compiled()
    if mutation == "dose":
        output["xml"] = output["xml"].replace('amount="0.2 mmol"', '')
    elif mutation == "reagent":
        output["xml"] = output["xml"].replace('reagent="Benzamide"', 'reagent="missing"')
    elif mutation == "subtype":
        output["xml"] = output["xml"].replace('type="microreactor"', 'type="reactor"')
    elif mutation == "scope":
        output["xml"] = output["xml"].replace('mass_scope="added_portion"', 'mass_scope="nominal_capacity"')
    elif mutation == "time":
        output["xml"] = output["xml"].replace('time="2 min"', 'time="2 h"')
    elif mutation == "event":
        output["event_locations"]["mix"] = [0]
    else:
        output["hardware_config"].clear()
    assert not check_conservation(facts, binding, output)["passed"]


@pytest.mark.parametrize("mutation", ["step", "temperature", "gear", "rating", "reagent"])
def test_checker_also_detects_unsupported_compiler_additions(mutation):
    facts, binding, output = compiled()
    if mutation == "step":
        output["xml"] = output["xml"].replace("</Procedure>", '<Wait time="5 h"/></Procedure>')
    elif mutation == "temperature":
        output["extensions"]["steps"]["Add"]["properties"].append("temp")
        output["xml"] = output["xml"].replace('<Add ', '<Add temp="25 °C" ')
    elif mutation == "gear":
        output["xml"] = output["xml"].replace("</Hardware>", '<Component id="invented" type="reactor"/></Hardware>')
    elif mutation == "reagent":
        output["xml"] = output["xml"].replace("</Reagents>", '<Reagent name="invented reagent"/></Reagents>')
    else:
        output["hardware_config"]["reactor"]["properties"]["pressure_rating"] = {"value": 100}
    assert not check_conservation(facts, binding, output)["passed"]


def test_nested_amount_bug_is_rejected_at_first_contract():
    bad = graph()
    bad["facts"][0]["value"]["value"] = {"value": "24.2", "unit": "mg"}
    with pytest.raises(ValueError):
        validate_facts(bad, TEXT)


def test_quantity_evidence_cannot_keep_number_but_invent_a_different_unit():
    bad = graph()
    bad["facts"][0]["value"]["unit"] = "kg"
    with pytest.raises(ValueError, match="unit absent"):
        validate_facts(bad, TEXT)


def test_empty_graph_is_not_a_successful_protocol():
    bad = graph()
    bad["events"] = []
    with pytest.raises(ValueError):
        validate_facts(bad, TEXT)


def test_real_saved_model_receipt_exercises_two_independent_doses_offline():
    from pathlib import Path
    import json
    receipt = json.loads((Path(__file__).parent / "fixtures/legacy_typed_add.json").read_text(encoding="utf-8"))
    step = receipt["step"]
    # Reuse literal values from an actual old response, not a fresh inference.
    text = step["evidence"] + " was added to a vial."
    value = graph()
    value["entities"][0].update(name=step["parameters"]["reagent"], expression=step["parameters"]["reagent"])
    value["entities"][1].update(name="vial", expression="vial")
    value["events"] = value["events"][:1]
    value["events"][0]["evidence_ids"] = ["c1"]
    value["facts"] = value["facts"][:2]
    quantities = [step["parameters"]["amount"], step["parameters"]["additional_amounts"][0]]
    for fact, amount in zip(value["facts"], quantities):
        fact["value"].update(value=str(amount["value"]), unit=amount["unit"])
    value["evidence"] = [{"evidence_id": "c1", "quote": text}, {"evidence_id": "c2", "quote": "vial"}]
    value["relations"] = []
    checked = validate_facts(value, text)
    binding = bind_facts(checked, Registry().snapshot)
    output = compile_facts(checked, binding, text=text)
    assert 'mass="46.9 mg"' in output["xml"] and 'amount="71 µmol"' in output["xml"]
    assert check_conservation(checked, binding, output)["passed"]


def test_ambiguous_repeated_quotes_require_occurrence_and_exact_offsets():
    bad = graph()
    bad["evidence"].append({"evidence_id": "repeated", "quote": "mixture"})
    with pytest.raises(ValueError, match="repeated"):
        validate_facts(bad, TEXT + " mixture")
    bad["evidence"][-1]["occurrence"] = 1
    checked = validate_facts(bad, TEXT + " mixture")
    assert checked["evidence"][-1]["start"] == len(TEXT) + 1


def test_incompatible_units_and_dangling_references_and_cycles_fail():
    for mutate in (lambda g: g["facts"][0]["value"].update(unit="mL"),
                   lambda g: g["events"][0].update(vessel_id="invented"),
                   lambda g: g["relations"].append({"relation_id": "r2", "subject_id": "mix", "relation": "precedes", "object_id": "add", "evidence_ids": ["c3"]})):
        bad = graph()
        mutate(bad)
        with pytest.raises(ValueError):
            validate_facts(bad, TEXT)


def test_units_allow_equivalence_but_never_mass_moles_or_force_mass():
    def q(kind, val, unit):
        return {"value_type": "quantity", "quantity_kind": kind, "value": val, "unit": unit, "status": "reported"}
    assert equivalent(q("mass", "1", "g"), q("mass", "1000", "mg"))
    assert equivalent(q("temperature", "80", "°C"), q("temperature", "80.0", "oC"))
    assert not equivalent(q("mass", "1", "g"), q("substance_amount", "1", "mol"))
    assert not equivalent(q("mass", "1", "g"), q("relative_centrifugal_force", "1", "g"))


def reference(facts, *, gold=False):
    from mosaic.facts import text_hash
    return {"reference_id": "regression", "source_sha256": text_hash(TEXT), "is_gold": gold, "coverage_status": "complete",
            "entities": facts["entities"], "events": facts["events"], "facts": facts["facts"]}


def test_reference_evaluation_penalizes_empty_output_and_wrong_binding():
    facts, _, _ = compiled()
    ref = reference(facts)
    assert score_reference(facts, ref, text=TEXT)["metrics"]["recall"] == 1
    empty = copy.deepcopy(facts)
    empty["facts"] = []
    assert score_reference(empty, ref, text=TEXT)["metrics"]["recall"] == 0
    wrong = copy.deepcopy(facts)
    wrong["facts"][0]["subject_id"] = "reactor"
    report = score_reference(wrong, ref, text=TEXT)
    assert report["metrics"]["fp"] == 1 and report["metrics"]["fn"] == 1
    assert report["misses"][0]["reason"] == "wrong_binding_or_scope"
    assert not report["gate_passed"]  # An assistant-authored regression fixture is not gold.


def test_partial_reference_does_not_claim_global_precision_or_bulk_success():
    facts, _, _ = compiled()
    ref = reference(facts)
    ref.update(coverage_status="partial")
    ref["facts"] = ref["facts"][:1]
    result = score_reference(facts, ref, text=TEXT)
    assert result["metrics"]["precision"] is None and result["unscored_output_facts"] == 4


def test_simultaneous_heating_and_stirring_use_native_xdl_without_cluster_labels():
    value = graph()
    sentence = "The mixture was heated at 80 °C with stirring for 2 min."
    text = TEXT.split(" The mixture")[0] + " " + sentence
    value["evidence"][-1]["quote"] = sentence
    value["events"][1]["action_surface"] = "stirring"
    value["events"].append({"event_id": "heat", "kind": "action", "expression": "heat", "action_surface": "heated",
                             "vessel_id": "reactor", "evidence_ids": ["c4"]})
    value["facts"][-1].update(subject_id="heat", event_id="heat", scope="reported_target",
        value={"value_type": "quantity", "quantity_kind": "temperature", "value": "80", "unit": "°C"})
    value["relations"].append({"relation_id": "r2", "subject_id": "heat", "relation": "same_interval", "object_id": "mix", "evidence_ids": ["c4"]})
    facts = validate_facts(value, text)
    binding = bind_facts(facts, Registry().snapshot)
    output = compile_facts(facts, binding, text=text)
    assert '<HeatChill ' in output["xml"] and 'stir="true"' in output["xml"]
    assert "op.mix" not in output["xml"] and "operation_id" not in output["xml"]
    assert check_conservation(facts, binding, output)["passed"]


def test_unimplemented_concurrency_is_retained_as_an_explicit_failure():
    value = graph()
    value["relations"] = [{"relation_id": "r2", "subject_id": "add", "relation": "during", "object_id": "mix", "evidence_ids": ["c3", "c4"]}]
    facts = validate_facts(value, TEXT)
    with pytest.raises(ValueError, match="no verified XDL lowering"):
        compile_facts(facts, bind_facts(facts, Registry().snapshot), text=TEXT)
