import pytest

from protocol_risk.api import Client, parse_json, settings
from protocol_risk.crosscheck import quantities_in_text
from protocol_risk.extract import validate_evidence
from protocol_risk.ingest import environment_atmosphere, quantity
from protocol_risk.xdl import validate_xdl


@pytest.mark.parametrize("unit,value,expected", [("LITER", 0.001, {"value": 1, "unit": "mL"}),
                                                  ("MICROLITER", 20, {"value": 0.02, "unit": "mL"}),
                                                  ("NANOMOLE", 100, {"value": 0.0001, "unit": "mmol"}),
                                                  ("HOUR", 2, {"value": 7200, "unit": "s"}),
                                                  ("KELVIN", 273.15, {"value": 0, "unit": "°C"})])
def test_unit_normalization(unit, value, expected):
    assert quantity({"units": unit, "value": value}) == expected


@pytest.mark.parametrize("value", ["NaN", "Infinity", "nonsense"])
def test_invalid_numbers_are_not_silently_normalized(value):
    assert quantity({"units": "CELSIUS", "value": value}) is None


def test_fabricated_source_evidence_is_rejected():
    raw = {"procedure": "The solution was stirred for 2 hours.", "components": []}
    errors = validate_evidence(raw, {"steps": [{"op": "Stir", "evidence": "heated to 80 C", "duration_s": 7200}]})
    assert errors


def test_undeclared_initial_reagent_is_not_accepted_without_literal_text():
    raw = {"procedure": "Add water.", "components": []}
    assert validate_evidence(raw, {"steps": [{"op": "Add", "reagent": "imagined catalyst", "evidence": "Add water."}]})


def test_workup_reuse_of_source_solvent_never_copies_the_initial_amount():
    from protocol_risk.extract import build_ir
    raw = {"id": "fixture", "procedure": "Add 1 mL water. Wash with 5 mL water.",
           "components": [{"id": "r1", "name": "water", "smiles": "O", "role": "SOLVENT",
                           "amount": {"value": 1, "unit": "mL"}, "source_path": "/inputs/water"}],
           "source": {"db": "TEST"}, "raw_sha256": "fixture", "reaction_smiles": None,
           "reaction_class": None, "yield_percent": None, "conditions": {}, "atmosphere": {}, "setup": {}}
    plan = {"steps": [{"op": "Add", "reagent": "water", "alias": "water", "amount": {"value": 1, "unit": "mL"}, "evidence": "Add 1 mL water."},
                      {"op": "Add", "reagent": "water", "alias": "water", "stage": "workup",
                       "amount": {"value": 5, "unit": "mL"}, "evidence": "Wash with 5 mL water."}]}
    assert not validate_evidence(raw, plan)
    result = build_ir(raw, plan, {})
    assert result["steps"][0]["amount"]["value"] == 1
    assert result["steps"][1]["amount"]["value"] == 5
    assert result["steps"][1]["reagent"] != result["steps"][0]["reagent"]
    assert result["reagents"][-1]["role"] == "WORKUP"
    # Repeated reaction additions are legal, but each must retain its own dose.
    plan["steps"][1]["stage"] = "reaction"
    assert not validate_evidence(raw, plan)
    plan["steps"][1]["amount"]["value"] = 1
    assert any("literal quantity" in e for e in validate_evidence(raw, plan))


def test_time_and_temperature_are_grounded_in_explicit_units():
    assert quantities_in_text("at −20 °C for 2 hours", "temp_C") == [-20]
    assert quantities_in_text("at 60 C for 18 hours", "temp_C") == [60]
    assert quantities_in_text("at −20 °C for 2 hours", "duration_s") == [7200]
    assert quantities_in_text("at room temperature overnight", "temp_C") == []


def test_missing_key_is_a_configuration_error_not_an_invented_default(tmp_path, monkeypatch):
    for key in ("API_KEY", "BASE_URL", "MODEL"):
        monkeypatch.delenv(key, raising=False)
    path = tmp_path / ".env"
    path.write_text("base_url=https://example.invalid\nmodel=test\n", encoding="utf-8")
    with pytest.raises(ValueError, match="api_key"):
        settings(path)


def test_fenced_json_and_xml_external_entities():
    assert parse_json('```json\n{"ok":true}\n```') == {"ok": True}
    with pytest.raises(ValueError, match="DOCTYPE"):
        validate_xdl('<!DOCTYPE Synthesis [<!ENTITY e SYSTEM "file:///secret">]><Synthesis/>')


def test_glovebox_gas_is_only_reconstructed_when_explicitly_named():
    assert environment_atmosphere({"environment": {"type": "GLOVE_BOX", "details": "N2 glovebox"}})["type"] == "NITROGEN"
    assert environment_atmosphere({"environment": {"type": "GLOVE_BOX"}}) is None
    assert environment_atmosphere({"environment": {"type": "FUME_HOOD", "details": "nitrogen cylinder nearby"}}) is None
