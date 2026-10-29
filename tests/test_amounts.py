import pytest

from mosaic.protocol.amounts import local_measurements, verify_amount


@pytest.mark.parametrize("evidence,alias,expected", [
    ("Add THF (1.0 mL).", "THF", {"value": 1, "unit": "mL"}),
    ("Add ethyl benzoate (20 umol).", "ethyl benzoate", {"value": 0.02, "unit": "mmol"}),
    ("50 mg of sodium chloride was charged.", "sodium chloride", {"value": 50, "unit": "mg"}),
])
def test_literal_quantities_are_checked_independently(evidence, alias, expected):
    assert verify_amount({"id": "r1"}, expected, evidence, alias)["status"] == "matched"


@pytest.mark.parametrize("value", [0.1, 10, 1000])
def test_wrong_structured_amounts_are_rejected(value):
    assert verify_amount({"id": "r1"}, {"value": value, "unit": "mL"}, "THF (1 mL)", "THF")["status"] == "conflict"


def test_structure_metadata_cannot_supply_an_unreported_mole_quantity():
    result = verify_amount({"id": "r1", "smiles": "CCO"}, {"value": 1, "unit": "mmol"}, "ethanol (46.07 mg)", "ethanol")
    assert result["status"] == "unknown"
    assert result["comparable_quantities"] == []


@pytest.mark.parametrize("text,alias", [("catalysts (2 umol)", "catalysts"), ("THF (1 mL), later THF (2 mL)", "THF"), ("THF and water (1 mL)", "THF"), ("ligand (1.5 mol%)", "ligand"), ("sodium chloride (10-30 mg)", "sodium chloride")])
def test_generic_ambiguous_other_reagent_loading_and_range_cannot_pass(text, alias):
    assert local_measurements(text, alias)[0] == []


def test_conflicting_mass_and_moles_do_not_cherry_pick_the_matching_number():
    result = verify_amount({"id": "r1", "smiles": "CCO"}, {"value": 1, "unit": "mmol"}, "ethanol (46.07 mg, 2 mmol)", "ethanol")
    assert result["status"] == "conflict"


def test_coarse_moles_are_not_confirmed_by_inferred_molecular_weight():
    result = verify_amount({"id": "r", "smiles": "CCO"}, {"value": 0.025, "unit": "mmol"},
                           "ethanol (1.152 mg, 0.03 mmol)", "ethanol")
    assert result["status"] == "unknown"
    assert len(result["comparable_quantities"]) == 1
    assert not result["comparable_quantities"][0]["within_tolerance"]
    assert result["comparable_quantities"][0]["compatible_with_printed_rounding"]


def test_coarse_printing_alone_is_unknown_instead_of_a_fabricated_confirmation():
    result = verify_amount({"id": "r"}, {"value": 0.025, "unit": "mmol"}, "ethanol (0.03 mmol)", "ethanol")
    assert result["status"] == "unknown"


def test_formulated_mass_does_not_imply_pure_compound_moles():
    result = verify_amount({"id": "r", "smiles": "[Na+].[H-]"}, {"value": 1, "unit": "mmol"},
                           "sodium hydride (40 mg, 60 % in mineral oil)", "sodium hydride")
    assert result["status"] == "unknown"
