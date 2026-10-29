"""Source gaps remain usable data without becoming fabricated numerical facts."""
import copy

import pytest

from mosaic.protocol.missing import annotate_missing, is_missing_parameter, missing_parameter


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


def test_extended_operation_parameter_envelopes_are_not_duplicated():
    record = protocol(step("Dry", "Dried overnight.", parameters={
        "duration_s": missing_parameter("Dried overnight.", "qualitative", "overnight")
    }))
    before = copy.deepcopy(record)
    annotate_missing(record)
    assert record == before
