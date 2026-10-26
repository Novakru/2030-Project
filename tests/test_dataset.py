"""Audit exported data, not just the code's individual helper functions."""
import copy

import jsonpatch
import pytest

from protocol_risk.conditions import SuccessIndex
from protocol_risk.io import ROOT, digest, read_jsonl
from protocol_risk.perturb import negative_fingerprint
from protocol_risk.symbolic import evaluate
from protocol_risk.xdl import export_xdl, validate_xdl


@pytest.fixture(scope="module")
def positives():
    path = ROOT / "data/positives.jsonl"
    if not path.exists():
        pytest.skip("Build dataset first")
    return list(read_jsonl(path))


def test_one_hundred_real_raw_and_xdl_pairs(positives):
    assert len(positives) >= 100
    for p in positives:
        assert p["source"]["db"] == "ORD"
        assert p["yield_percent"] > 30
        assert (ROOT / "data/raw/protocols" / (p["raw_id"] + ".json")).exists()
        assert evaluate(p).risks == []
        assert validate_xdl(p["xdl"])
        assert export_xdl(p) == p["xdl"]
        if p["quality"]["manual_review"] == "pending" or p["quality"]["hardware_verification"] == "pending":
            assert p["quality"]["tier"] != "gold"
            assert not p["quality"]["full_feasibility_certified"]


def test_every_source_derived_negative_replays_with_one_target_class(positives):
    mapping = {p["id"]: p for p in positives}
    seen, content_hashes = set(), set()
    for n in read_jsonl(ROOT / "data/negatives.jsonl"):
        parent = mapping[n["parent_id"]]
        assert n["id"] not in seen
        seen.add(n["id"])
        fingerprint = negative_fingerprint(n)
        assert fingerprint not in content_hashes
        content_hashes.add(fingerprint)
        child = jsonpatch.apply_patch(copy.deepcopy(parent), n["diff"])
        assert child == n["protocol"]
        assert n["split"] == parent["split"]
        assert evaluate(child).risks == ([] if n["label"]["label_type"] == "soft" else [n["label"]["risk_l2"]])
        assert n["xdl"] == export_xdl(child)
        if n["benchmark_eligible"]:
            assert parent["quality"]["tier"] == "gold"
            if n["label"]["label_type"] == "soft":
                assert n["label"]["calibrated"] and n["label"]["p_infeasible"] is not None


def test_soft_candidates_do_not_match_known_successes(positives):
    index = SuccessIndex()
    try:
        for n in read_jsonl(ROOT / "data/negatives.jsonl"):
            if n["label"]["label_type"] == "soft":
                assert index.match(n["protocol"]) is None
    finally:
        index.close()


def test_scaffold_groups_and_parents_never_cross_splits(positives):
    groups = {}
    for p in positives:
        assert groups.setdefault(p["split_group"], p["split"]) == p["split"]
