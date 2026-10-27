import copy

import pytest

from mosaic.chemistry import ChemistryDomain
from mosaic.engine import _select
from mosaic.supplements import build_supplements
from protocol_risk.ingest import read_raw
from protocol_risk.io import digest


def test_complete_text_does_not_require_structured_addition_order():
    raw = {"temperature": {"value": 80}, "reaction_smiles": "C>>CO", "yield_percent": 70,
           "conditions": {}, "components": [{"amount": {"value": 1, "unit": "mmol"}, "addition_order": None}],
           "procedure": "A source procedure with explicit input actions. " * 12}
    domain = ChemistryDomain()
    assert domain.eligible(raw) and domain.text_ready(raw)
    assert not domain.structured_ready(raw)
    raw["procedure"] = "A generic record note."
    assert not domain.eligible(raw)


def test_selection_retains_real_microreactor_text_and_no_duplicate_sources():
    selected = _select(ChemistryDomain(), 140, 40)
    assert len({r["id"] for r in selected}) == len(selected)
    assert any("microreactor" in (r.get("procedure") or "").lower() for r in selected[:40])
    assert all(digest(r["raw"]) == r["raw_sha256"] for r in selected)


def test_supplements_have_exact_replay_and_two_native_omission_operations():
    import jsonpatch
    batch = build_supplements("fixture_run", 12)
    assert batch["counts"] == {"B5": 10, "B2": 12, "B3": 12, "D2": 12}
    parents = {p["id"]: p for p in batch["parents"]}
    mechanisms = {s["mutation"]["mechanism_id"] for s in batch["negatives"]}
    assert {"D2.omitted_transfer", "D2.omitted_filterthrough"} <= mechanisms
    for sample in batch["negatives"]:
        assert jsonpatch.apply_patch(copy.deepcopy(parents[sample["parent_id"]]), sample["diff"]) == sample["protocol"]
        assert not sample["benchmark_eligible"]
        assert sample["split"] == parents[sample["parent_id"]]["split"]
