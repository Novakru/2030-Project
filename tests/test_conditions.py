from protocol_risk.conditions import SuccessIndex, fingerprint, protocol_key, raw_key
from tests.chemistry_fixtures import reference
from protocol_risk.extract import structured_plan


def test_success_filter_compares_conditions_independently_of_component_ids(tmp_path):
    raw = {"id": "r", "reaction_smiles": "CCO>>CC=O", "reaction_class": "oxidation", "raw_sha256": "stub",
           "source": {}, "setup": {}, "conditions": {}, "atmosphere": {"type": "AIR"}, "yield_percent": 80,
           "components": [{"id": "r1", "name": "ethanol", "smiles": "CCO", "role": "REACTANT",
                           "amount": {"value": 1, "unit": "mmol"}, "addition_order": 1, "input_key": "a", "source_path": "/inputs/a"}],
           "temperature": {"value": 25, "unit": "°C"}, "duration": {"value": 3600, "unit": "s"}}
    protocol = structured_plan(raw)
    assert raw_key(raw) == protocol_key(protocol)
    index = SuccessIndex(tmp_path / "index.sqlite")
    try:
        assert index.build([raw]) == 1
        assert index.match(protocol)
        protocol["steps"][-1]["duration_s"] = 1
        assert index.match(protocol) is None
    finally:
        index.close()


def test_duplicate_solvent_additions_are_aggregated():
    water = {"name": "water", "smiles": "O", "role": "SOLVENT"}
    first = fingerprint("A>>B", [(water, {"value": 1, "unit": "mL"}), (water, {"value": 2, "unit": "mL"})], 20, 100, "AIR")
    second = fingerprint("A>>B", [(water, {"value": 3, "unit": "mL"})], 20, 100, "AIR")
    assert first == second


def test_zero_dose_catalyst_is_equivalent_to_absence_for_success_filtering():
    solvent = {"name": "water", "smiles": "O", "role": "SOLVENT"}
    catalyst = {"name": "palladium", "smiles": "[Pd]", "role": "CATALYST"}
    one = fingerprint("A>>B", [(solvent, {"value": 1, "unit": "mL"}), (catalyst, {"value": 0, "unit": "mmol"})], 25, 100, "AIR")
    two = fingerprint("A>>B", [(solvent, {"value": 1, "unit": "mL"})], 25, 100, "AIR")
    assert one == two
