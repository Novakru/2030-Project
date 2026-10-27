"""Source gaps remain usable data without becoming fabricated numerical facts."""
import copy

import pytest

from protocol_risk.missing import annotate_missing, is_missing_parameter, missing_parameter
from protocol_risk.symbolic import evaluate


def protocol(*steps, text=None):
    return {
        "id": "test", "source_text": text or " ".join(step.get("meta", {}).get("evidence", "") for step in steps),
        "steps": list(steps), "reagents": [{"id": "ethanol", "name": "ethanol", "role": "SOLVENT"}],
        "hardware": {
            "nodes": {
                "reactor": {"category": "vessel", "verified": True, "params": {"capacity_mL": 10}},
                "product": {"category": "vessel", "verified": True, "params": {"capacity_mL": 10}},
                "heater": {"category": "heater_stirrer", "verified": True, "params": {}},
            }, "edges": [["reactor", "product"]], "bindings": {"heater": "heater"},
        },
    }


def step(op, evidence, **fields):
    return {"id": fields.pop("id", "s1"), "op": op, "meta": {"evidence": evidence}, **fields}


def addition(value=None, *, id="add", vessel="reactor"):
    fields = {"reagent": "ethanol", "vessel": vessel, "id": id}
    if value is not None:
        fields["amount"] = {"value": value, "unit": "mL"}
    return step("Add", "Ethanol was added." if value is None else f"ethanol ({value} mL) was added.", **fields)


def test_unreported_initial_contents_are_unknown_rather_than_proven_empty():
    p = protocol(step("Transfer", "The stock was transferred.", from_vessel="reactor", to_vessel="product",
                      amount={"value": 1, "unit": "mL"}))
    assert "D1" in evaluate(p).risks
    p["context"] = {"initial_material_state": "unknown_unless_reported"}
    result = evaluate(p)
    assert "D1" not in result.risks
    assert any(item["reason"] == "initial_material_state_not_reported" for item in result.unknowns)


def test_missing_factory_validates_status_and_literal_qualifier():
    gap = missing_parameter("Stirred overnight.", "qualitative", "overnight")
    assert gap == {"status": "qualitative", "marker": "__QUALITATIVE__", "evidence": "Stirred overnight.", "raw": "overnight"}
    assert is_missing_parameter(gap)
    assert not is_missing_parameter({**gap, "marker": "__NOT_REPORTED__"})
    with pytest.raises(ValueError, match="literally"):
        missing_parameter("Stirred overnight.", "qualitative", "12 hours")
    with pytest.raises(ValueError, match="status"):
        missing_parameter("Stirred.", "whatever")


@pytest.mark.parametrize("op,fields", [
    ("Add", ["amount"]), ("HeatChill", ["temp_C"]),
    ("Stir", ["duration_s"]), ("Wait", ["duration_s"]),
    ("Irradiate", ["duration_s"]), ("Transfer", ["from_vessel", "to_vessel", "amount"]),
    ("Separate", ["keep_phase"]), ("Purify", ["method"]),
])
def test_required_core_fields_get_separate_idempotent_gap_entries(op, fields):
    record = protocol(step(op, "An operation was performed."))
    assert annotate_missing(record) is record
    assert set(record["steps"][0]["missing_parameters"]) == set(fields)
    assert all(record["steps"][0]["missing_parameters"][field]["marker"] == "__NOT_REPORTED__" for field in fields)
    before = copy.deepcopy(record)
    annotate_missing(record)
    assert record == before
    assert all(field not in record["steps"][0] for field in fields)


def test_overnight_and_room_temperature_preserve_source_words():
    record = protocol(step("Stir", "Stirred overnight.", id="s1"),
                      step("HeatChill", "Heated at room temperature.", id="s2"))
    annotate_missing(record)
    assert record["steps"][0]["missing_parameters"]["duration_s"]["raw"] == "overnight"
    assert record["steps"][1]["missing_parameters"]["temp_C"]["raw"] == "room temperature"
    assert "duration_s" not in record["steps"][0]
    assert "temp_C" not in record["steps"][1]
    assert "12" not in str(record)


@pytest.mark.parametrize("op,evidence,fields", [
    ("Stir", "Stirred for 2 h.", {}),
    ("HeatChill", "Heated at 80 C.", {}),
    ("Add", "ethanol (2 mL) was added.", {"reagent": "ethanol"}),
    ("Add", "ethanol (0 mL) was added.", {"reagent": "ethanol"}),
    ("Transfer", "Transferred 2 mL.", {"from_vessel": "reactor", "to_vessel": "product"}),
])
def test_a_missing_marker_cannot_hide_explicit_source_numbers(op, evidence, fields):
    with pytest.raises(ValueError, match="explicit source"):
        annotate_missing(protocol(step(op, evidence, **fields)))


def test_reagent_quantity_checks_do_not_borrow_another_reagents_dose():
    record = protocol(step("Add", "ethanol and water (2 mL) were added.", reagent="ethanol"))
    annotate_missing(record)
    assert record["steps"][0]["missing_parameters"]["amount"]["status"] == "not_reported"


@pytest.mark.parametrize("op,evidence,fields,key", [
    ("Stir", "Stirred for 1-2 h.", {}, "duration_s"),
    ("HeatChill", "Heated at 20-30 C.", {}, "temp_C"),
    ("Add", "ethanol (1-2 mL) was added.", {"reagent": "ethanol"}, "amount"),
])
def test_numeric_range_remains_ambiguous_not_an_invented_setpoint(op, evidence, fields, key):
    record = protocol(step(op, evidence, **fields))
    annotate_missing(record)
    assert record["steps"][0]["missing_parameters"][key]["status"] == "ambiguous"
    assert record["steps"][0]["missing_parameters"][key]["raw"] in evidence
    assert key not in record["steps"][0]


def test_unrelated_reagents_range_does_not_mask_an_explicit_dose():
    record = protocol(step("Add", "ethanol (2 mL) and water (1-2 mL) were added.", reagent="ethanol"))
    with pytest.raises(ValueError, match="explicit source amount"):
        annotate_missing(record)


def test_missing_parameter_evidence_must_belong_to_the_record():
    with pytest.raises(ValueError, match="exact quote"):
        annotate_missing(protocol(step("Wait", "Waited overnight."), text="A different procedure."))


def test_known_values_are_unchanged_and_cannot_be_overridden_by_gap_entries():
    record = protocol(addition(0))
    before = copy.deepcopy(record)
    annotate_missing(record)
    assert record == before
    assert evaluate(record).risks == ["D4"]
    record["steps"][0]["missing_parameters"] = {"amount": missing_parameter(record["source_text"])}
    with pytest.raises(ValueError, match="known amount"):
        annotate_missing(record)
    assert "D4" in evaluate(record).risks


def test_extended_operation_parameter_envelopes_are_not_duplicated():
    record = protocol(step("Dry", "Dried overnight.", parameters={
        "duration_s": missing_parameter("Dried overnight.", "qualitative", "overnight")
    }))
    before = copy.deepcopy(record)
    annotate_missing(record)
    assert record == before


def test_unquantified_addition_yields_unknown_quantity_and_not_d4():
    record = annotate_missing(protocol(addition()))
    result = evaluate(record)
    assert result.risks == []
    assert any(item.get("parameter") == "amount" for item in result.unknowns)
    assert any(item["rule"] == "A1" and item["reason"] == "inventory_quantity_unknown" for item in result.unknowns)


def test_known_overfill_is_still_proved_with_another_unquantified_addition():
    result = evaluate(annotate_missing(protocol(addition(id="unknown"), addition(11, id="known"))))
    assert result.risks == ["A1"]
    assert any(item["rule_id"] == "A1.capacity" for item in result.violations)


def test_transfer_without_quantity_propagates_unknown_to_both_vessels():
    record = protocol(addition(8),
        step("Transfer", "Transferred the solution.", id="move_unknown", from_vessel="reactor", to_vessel="product"),
        step("Transfer", "Transferred 6 mL.", id="move_known", from_vessel="reactor", to_vessel="product", amount={"value": 6, "unit": "mL"}),
        step("Stir", "Stirred for 1 min.", id="mix", vessel="product", duration_s=60))
    result = evaluate(annotate_missing(record))
    assert result.risks == []
    assert any(item["reason"] == "transfer_quantity_unknown" for item in result.unknowns)
    assert any(item["rule"] == "A1" and item.get("step_id") == "mix" for item in result.unknowns)


@pytest.mark.parametrize("fields", [{}, {"from_vessel": "reactor"}, {"to_vessel": "product"}])
def test_transfer_missing_references_abstains_without_key_error_or_d3(fields):
    result = evaluate(annotate_missing(protocol(step("Transfer", "Transferred the solution.", **fields))))
    assert result.risks == []
    assert any(item.get("parameter") in ("from_vessel", "to_vessel") for item in result.unknowns)


def test_an_explicit_undeclared_transfer_vessel_still_triggers_d3():
    result = evaluate(protocol(step("Transfer", "Transferred the solution.", from_vessel="not_declared", to_vessel="product")))
    assert result.risks == ["D3"]


def test_opaque_extension_invalidates_state_instead_of_behaving_as_a_noop():
    record = protocol(addition(8), step("Wash", "Washed the contents.", id="wash", parameters={"vessel": {"value": "reactor", "evidence": "contents"}}),
                      addition(4, id="new_add"), step("Stir", "Stirred for 1 min.", id="mix", duration_s=60))
    record["operation_definitions"] = {"Wash": {"effects": ["phase_composition_changed"]}}
    result = evaluate(record)
    assert result.risks == []
    assert any(item["reason"] == "extension_effect_semantics_unknown" and item["vessels"] == ["reactor"] for item in result.unknowns)
    assert any(item["rule"] == "A1" and item.get("step_id") == "mix" for item in result.unknowns)


def test_opaque_extension_keeps_previously_proved_violations():
    record = protocol(addition(11), step("Wash", "Washed the contents.", id="wash", vessel="reactor"))
    record["operation_definitions"] = {"Wash": {}}
    result = evaluate(record)
    assert result.risks == ["A1"]
    assert result.violations[0]["values"]["step_id"] == "add"


@pytest.mark.parametrize("value", [False, float("nan"), float("inf"), "__NOT_REPORTED__"])
def test_invalid_reported_quantities_do_not_turn_into_unknown_source_gaps(value):
    record = protocol(addition(1))
    record["steps"][0]["amount"]["value"] = value
    assert evaluate(record).risks == ["D4"]
