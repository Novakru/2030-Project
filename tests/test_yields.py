import copy

import pytest

from protocol_risk.yields import target_yield


def product(value, desired=None):
    row = {"reaction_role": "PRODUCT", "measurements": [{"type": "YIELD", "percentage": {"value": value}}]}
    if desired is not None:
        row["is_desired_product"] = desired
    return row


def reaction(*products):
    return {"outcomes": [{"products": list(products)}]}


def test_high_yield_byproduct_cannot_turn_target_failure_into_success():
    raw = reaction(product(2, True), product(95, False))
    value, evidence = target_yield(raw)
    assert value == 2
    assert evidence["target_source_path"] == "/outcomes/0/products/0"
    assert evidence["measurements"][0]["source_path"].endswith("/measurements/0")


def test_explicit_target_is_preferred_to_an_unflagged_product():
    assert target_yield(reaction(product(4, True), product(80)))[0] == 4


@pytest.mark.parametrize("products,status", [
    ((product(4), product(80)), "ambiguous_target"),
    ((product(4, True), product(80, True)), "ambiguous_target"),
    ((product(80, False),), "missing_target"),
    ((), "missing_target"),
])
def test_ambiguous_or_excluded_targets_abstain(products, status):
    value, evidence = target_yield(reaction(*products))
    assert value is None and evidence["status"] == status


def test_conflicting_yields_are_not_maximized_and_source_is_preserved():
    raw = reaction(product(90, True))
    raw["outcomes"][0]["products"][0]["measurements"].append({"type": "YIELD", "percentage": {"value": 62}})
    before = copy.deepcopy(raw)
    value, evidence = target_yield(raw)
    assert value is None and evidence["status"] == "conflicting_measurements"
    assert raw == before


@pytest.mark.parametrize("value", [-1, 101, float("inf"), float("nan"), True, "50", None])
def test_invalid_percentages_cannot_become_training_labels(value):
    result, evidence = target_yield(reaction(product(value, True)))
    assert result is None and evidence["status"] == "invalid_percentage"


@pytest.mark.parametrize("value", [0, 100])
def test_real_boundary_percentages_are_preserved(value):
    assert target_yield(reaction(product(value)))[0] == value
