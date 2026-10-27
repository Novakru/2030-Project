"""Acceptance checks consume the same manifest as generation and publication."""
import copy
from pathlib import Path

import jsonpatch
import pytest

from mosaic.verification import verify_dataset
from protocol_risk.conditions import SuccessIndex
from protocol_risk.io import ROOT, read_json, read_jsonl


@pytest.fixture(scope="module")
def batch():
    pointer = ROOT / "data/mosaic/current.json"
    if not pointer.exists():
        pytest.skip("Generate a MOSAIC batch first")
    manifest_path = pointer.parent / read_json(pointer)["manifest"]
    manifest = read_json(manifest_path)
    if manifest.get("result", {}).get("input_contract") != "text-only/1":
        pytest.skip("Legacy mixed-source batch: regenerate with the text-only generator")
    bundle = manifest["result"]["review_bundle"]
    return manifest_path.parent, list(read_jsonl(manifest_path.parent / bundle["positives"])), list(read_jsonl(manifest_path.parent / bundle["negatives"])), bundle


def test_source_text_and_xdl_pairs_are_consistent(batch):
    root, parents, _, bundle = batch
    raw_path = root / Path(bundle["positives"]).parent / "raw.jsonl"
    raws = {r["id"]: r for r in read_jsonl(raw_path)}
    observed = [p for p in parents if p["source"]["db"] == "ORD"]
    assert observed
    for parent in observed:
        assert parent["raw_id"] in raws
        assert parent["source_text"] == raws[parent["raw_id"]]["procedure"]
        assert parent["extraction"]["input_contract"] == "text-only/1"
        assert parent["quality"]["tier"] == "silver"
        assert (root / Path(bundle["positives"]).parent / "xdl" / (parent["id"] + ".xdl")).read_text(encoding="utf-8") == parent["xdl"]


def test_source_hashes_and_every_negative_intervention_replay(batch):
    result = verify_dataset(batch[0])
    assert result["passed"], result["issues"]


def test_quota_one_hundred_real_raw_and_xdl_pairs(batch):
    root, parents, _, bundle = batch
    raws = list(read_jsonl(root / Path(bundle["positives"]).parent / "raw.jsonl"))
    observed = [p for p in parents if p["source"]["db"] == "ORD"]
    assert len(raws) >= 100
    assert len(observed) >= 100, f"Only {len(observed)}/100 literal-text conversions passed"


def test_quota_ten_examples_for_each_of_twenty_risks(batch):
    from collections import Counter
    from protocol_risk.io import load_library
    counts = Counter(sample["label"]["risk_l2"] for sample in batch[2])
    risks = load_library("risks.yaml")
    # The requested coverage remains a separate, explicit acceptance gate.
    required = risks["risks"]
    missing = {risk: counts[risk] for risk in required if counts[risk] < 10}
    assert not missing, f"Risk quotas still unmet: {missing}"


def test_soft_candidates_do_not_match_known_successes(batch, tmp_path):
    from protocol_risk.ingest import read_raw
    index = SuccessIndex(tmp_path / "success.sqlite")
    try:
        index.build(read_raw())
        for sample in batch[2]:
            if sample["label"]["label_type"] == "soft":
                assert index.match(sample["protocol"]) is None
                assert sample["label"]["calibrated"] is False
                assert not sample["benchmark_eligible"]
    finally:
        index.close()


def test_scaffold_groups_and_parents_never_cross_splits(batch):
    groups = {}
    parents = {p["id"]: p for p in batch[1]}
    for parent in parents.values():
        assert groups.setdefault(parent["split_group"], parent["split"]) == parent["split"]
    for sample in batch[2]:
        assert sample["split"] == parents[sample["parent_id"]]["split"]
