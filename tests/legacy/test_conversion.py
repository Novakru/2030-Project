"""Exercise the public text-to-XDL interface, with an explicit model test double."""
import copy
from pathlib import Path

import pytest

from mosaic import ConversionSpec, Runtime, convert, resume
from mosaic.protocol.xdl_document import read_document
from mosaic.protocol.io import read_json, read_jsonl
from mosaic.sources import load_text_sources
from mosaic.verification import verify_conversion


from tests.legacy.facts_fixture import TEXT, graph
from mosaic.fact_extraction import EXTRACT, VERIFY


class Model:
    def complete(self, system, prompt, cache=True):
        if system == EXTRACT:
            data = graph()
        elif system == VERIFY:
            data = {"issues": []}
        else:
            data = {"proposals": []}
        return {"data": data, "model": "explicit-test-double"}


def convert_text(tmp_path, text=TEXT, **options):
    path = tmp_path / "procedure.txt"
    path.write_text(text, encoding="utf-8")
    return convert(ConversionSpec(output_dir=str(tmp_path / "runs"), workers=1, **options),
                   runtime=Runtime(records=load_text_sources([path]), client_factory=lambda _: Model()))


def test_conversion_grows_expression_preserves_gaps_and_replays_without_http(tmp_path, monkeypatch):
    result = convert_text(tmp_path)
    assert result["converted"] == 1 and result["failures"] == 0
    root = Path(result["run_dir"])
    record = next(read_jsonl(root / "records.jsonl"))
    assert [step["op"] for step in record["steps"]] == ["Add", "Stir"]
    assert record["source_text"] == TEXT
    assert "__QUALITATIVE__" in record["xdl"] and "room temperature" in record["xdl"]
    assert result["model_calls"] == 2
    assert [s["op"] for s in read_document(record["xdl"], extensions=record["xdl_extensions"])["steps"]] == ["Add", "Stir"]
    assert verify_conversion(root)["passed"]
    before = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file() and "artifacts" not in p.parts and p.name != "manifest.json"}
    monkeypatch.setattr("requests.sessions.Session.request", lambda *a, **k: pytest.fail("HTTP during offline replay"))
    replay = resume(root, offline=True)
    assert replay["new_model_calls"] == 0
    after = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file() and "artifacts" not in p.parts and p.name != "manifest.json"}
    assert before == after


def test_invalid_conversion_retains_source_and_failure_for_review(tmp_path):
    result = convert_text(tmp_path, text="Water (5 mL) was added.")
    assert result["converted"] == 0 and result["failures"] == 1
    root = Path(result["run_dir"])
    assert read_json(root / "manifest.json")["status"] == "partial"
    assert next(read_jsonl(root / "candidates.jsonl"))["source_text"] == "Water (5 mL) was added."
    assert verify_conversion(root)["passed"]


def test_conversion_requires_explicit_text_instead_of_an_implicit_database(tmp_path):
    with pytest.raises(ValueError, match="Provide experimental procedure text"):
        convert(ConversionSpec(output_dir=str(tmp_path)))


def test_code_or_source_change_cannot_silently_reuse_frozen_run(tmp_path, monkeypatch):
    result = convert_text(tmp_path)
    monkeypatch.setattr("mosaic.engine._code_revision", lambda _=None: "changed-code")
    with pytest.raises(ValueError, match="Cannot resume after code"):
        resume(result["run_dir"], offline=True)
