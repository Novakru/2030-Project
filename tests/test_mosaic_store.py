import pytest

from mosaic.evidence import SourceSpan, chunk_document
from mosaic.store import RunStore, atomic_json


def test_interrupted_run_reopens_exact_artifact_and_rejects_different_input(tmp_path):
    directory = tmp_path / "run"
    store = RunStore(directory, {"source": "pinned-source", "domain": "chemistry/1"})
    store.save("extract", {"record": "a"}, {"steps": [{"op": "Wait", "duration_s": 60}]}, engine="program")
    resumed = RunStore(directory, {"source": "pinned-source", "domain": "chemistry/1"})
    result, receipt = resumed.find("extract", {"record": "a"})
    assert result == {"steps": [{"op": "Wait", "duration_s": 60}]}
    assert receipt["engine"] == "program" and resumed.find("extract", {"record": "b"}) is None
    with pytest.raises(ValueError, match="request changed"):
        RunStore(directory, {"source": "changed-source", "domain": "chemistry/1"})


def test_corrupted_stage_output_is_not_silently_reused(tmp_path):
    store = RunStore(tmp_path, {"source": "a"})
    store.save("extract", "a", {"steps": []}, engine="replay")
    path = tmp_path / store.manifest["events"][0]["artifact"]
    atomic_json(path, {"steps": [{"op": "invented"}]})
    with pytest.raises(ValueError, match="modified"):
        RunStore(tmp_path, {"source": "a"})


def test_result_cannot_redirect_a_verified_run_to_untracked_records(tmp_path):
    store = RunStore(tmp_path, {"source": "a"})
    store.finish("complete", {"review_bundle": {"positives": "frozen.jsonl"}})
    store.manifest["result"]["review_bundle"]["positives"] = "other.jsonl"
    atomic_json(store.manifest_path, store.manifest)
    with pytest.raises(ValueError, match="result was modified"):
        RunStore(tmp_path, {"source": "a"})


def test_tracking_an_unchanged_frozen_export_is_idempotent(tmp_path):
    from mosaic.store import atomic_bytes
    store = RunStore(tmp_path, {"source": "a"})
    atomic_bytes(tmp_path / "record.xdl", b"<Synthesis/>")
    store.track_file("xdl/record", "record.xdl")
    count = len(store.manifest["events"])
    store.track_file("xdl/record", "record.xdl")
    assert len(store.manifest["events"]) == count
    assert store.verify()


def test_windows_transient_lock_retries_atomic_replace(tmp_path, monkeypatch):
    import os
    import mosaic.store as module
    if os.name != "nt":
        pytest.skip("Windows file-sharing semantics")
    replace = os.replace
    calls = []
    def locked_once(source, target):
        calls.append(target)
        if len(calls) == 1:
            raise PermissionError("simulated transient file lock")
        replace(source, target)
    monkeypatch.setattr(module.os, "replace", locked_once)
    module.atomic_bytes(tmp_path / "artifact.json", b"new bytes")
    assert len(calls) == 2 and (tmp_path / "artifact.json").read_bytes() == b"new bytes"


def test_exact_source_offsets_survive_unicode_and_overlapping_chunks():
    text = "\u53cd\u5e94\uff1a5 mL vial. Mix, then wait. 5 mL vial."
    span = SourceSpan.locate("doc", text, "5 mL vial.", start=text.rfind("5 mL vial."))
    assert text[span.start:span.end] == "5 mL vial." and span.start > text.find("5 mL vial.")
    chunks = chunk_document("doc", text, size=16, overlap=4)
    assert chunks[0]["start"] == 0 and chunks[-1]["end"] == len(text)
    assert all(text[c["start"]:c["end"]] == c["quote"] for c in chunks)
    with pytest.raises(ValueError, match="does not match"):
        SourceSpan.locate("doc", text, "invented quote")
