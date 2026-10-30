import copy
from pathlib import Path

import pytest

from mosaic.agents import AgentRunner
from mosaic.engine import ConversionSpec, Runtime, convert
from mosaic.fact_extraction import EXTRACT, VERIFY, FORMAT_REPAIR, REPAIR, extract_facts, apply_repair
from mosaic.facts import validate_facts
from mosaic.sources import text_document
from mosaic.store import RunStore
from mosaic.protocol.io import read_jsonl
from tests.facts_fixture import TEXT, graph


ISSUE = {"issue_id": "wrong_scope", "kind": "wrong_scope", "object_ids": ["mass"],
         "quote": "24.2 mg", "reason": "This is an added portion, not nominal vessel capacity.", "blocking": True}


def run(tmp_path, replies):
    calls = []

    class Client:
        def complete(self, system, prompt, cache=True):
            calls.append(system)
            response = replies[len(calls) - 1]
            return {"data": copy.deepcopy(response), "model": "test-double"}

    store = RunStore(tmp_path / "run", {"case": "bounded"})
    runner = AgentRunner(store, max_calls=3, client_factory=lambda _: Client())
    result = extract_facts(text_document({"id": "source", "procedure": TEXT, "raw_sha256": "test"}), runner)
    assert store.verify()
    return result, calls


def test_normal_path_uses_two_calls(tmp_path):
    result, calls = run(tmp_path, [graph(), {"issues": []}])
    assert calls == [EXTRACT, VERIFY]
    assert result["semantic_status"] == "model_checked_not_gold"


def test_malformed_extractor_uses_shared_repair_then_verifier(tmp_path):
    result, calls = run(tmp_path, [{"invalid_json_text": "broken"}, graph(), {"issues": []}])
    assert calls == [EXTRACT, FORMAT_REPAIR, VERIFY]
    assert result["repair"]["kind"] == "structure"


def test_malformed_verifier_uses_same_one_repair_budget(tmp_path):
    result, calls = run(tmp_path, [graph(), {"issues": "invalid"}, {"issues": []}])
    assert calls == [EXTRACT, VERIFY, FORMAT_REPAIR]
    assert result["repair"]["kind"] == "verifier_structure"


def test_format_and_semantic_repairs_cannot_each_consume_an_attempt(tmp_path):
    result, calls = run(tmp_path, [{"invalid_json_text": "broken"}, graph(), {"issues": [ISSUE]}])
    assert len(calls) == 3 and result["audit"]["issues"] == [ISSUE]


def test_local_repair_keeps_ids_and_unrelated_facts_and_is_not_reverified(tmp_path):
    value = graph()
    value["facts"][0]["scope"] = "nominal_capacity"
    patch = {"patch": [{"op": "replace", "path": "/facts/0/scope", "value": "added_portion"}], "addressed_issue_ids": ["wrong_scope"]}
    result, calls = run(tmp_path, [value, {"issues": [ISSUE]}, patch])
    assert calls == [EXTRACT, VERIFY, REPAIR]
    assert result["facts"]["facts"][0]["scope"] == "added_portion"
    assert result["repair"]["independently_reverified"] is False


def test_local_repair_cannot_change_unrelated_objects_or_source():
    value = validate_facts(graph(), TEXT)
    patch = {"patch": [{"op": "replace", "path": "/facts/1/scope", "value": "invented"}], "addressed_issue_ids": ["wrong_scope"]}
    with pytest.raises(ValueError, match="unrelated"):
        apply_repair(value, patch, TEXT, [ISSUE])
    patch["patch"] = [{"op": "replace", "path": "/source", "value": "invented"}]
    with pytest.raises(ValueError, match="outside"):
        apply_repair(value, patch, TEXT, [ISSUE])


def test_failed_verification_keeps_typed_facts_and_source_for_review(tmp_path):
    class Client:
        def complete(self, system, prompt, cache=True):
            if system == VERIFY:
                raise RuntimeError("simulated transport failure")
            return {"data": graph(), "model": "test-double"}

    result = convert(ConversionSpec(output_dir=str(tmp_path), curate=False), runtime=Runtime(
        records=[{"id": "source", "procedure": TEXT}], client_factory=lambda _: Client()))
    assert result["converted"] == 0 and result["failures"] == 1
    candidate = next(read_jsonl(Path(result["run_dir"]) / "candidates.jsonl"))
    assert candidate["source_text"] == TEXT and len(candidate["facts"]["facts"]) == 5
    assert candidate["mosaic"]["conversion_failure"]["category"] == "transport"


def test_program_failure_never_triggers_another_extraction(tmp_path, monkeypatch):
    calls = []

    class Client:
        def complete(self, system, prompt, cache=True):
            calls.append(system)
            return {"data": graph() if system == EXTRACT else {"issues": []}, "model": "test-double"}

    def fail(*args, **kwargs):
        raise TypeError("simulated compiler defect")

    monkeypatch.setattr("mosaic.engine.compile_facts", fail)
    result = convert(ConversionSpec(output_dir=str(tmp_path)), runtime=Runtime(
        records=[{"id": "source", "procedure": TEXT}], client_factory=lambda _: Client()))
    failure = next(read_jsonl(Path(result["run_dir"]) / "failures.jsonl"))
    assert calls == [EXTRACT, VERIFY] and failure["category"] == "program_defect"
