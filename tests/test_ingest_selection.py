import pytest

from protocol_risk.ingest import iter_ord, read_raw
from protocol_risk.io import ROOT, read_json


def test_selective_reads_preserve_the_same_complete_source_record():
    if not (ROOT / "data/raw/reactions.parquet").exists():
        pytest.skip("Ingest data first")
    full = next(read_raw())
    selected = list(read_raw(ids={full["id"]}))
    assert len(selected) == 1 and selected[0] == full
    source = next(s for s in read_json(ROOT / "data/sources.lock.json")["files"] if s["path"] == full["source"]["file"])
    raw = list(iter_ord(ROOT / source["path"], ids={full["id"]}))
    assert len(raw) == 1 and raw[0][0] == full["raw"]
