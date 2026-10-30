"""Frozen, bounded text → facts → library binding → XDL batches."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import copy
from dataclasses import asdict, dataclass, field
from pathlib import Path
import time
import sys
from importlib.metadata import version

from .agents import AgentRunner
from .evaluation import REFERENCE_RECALL_MIN, check_conservation
from .fact_binding import bind_facts
from .fact_evolution import maintain_facts_library
from .fact_extraction import extract_facts
from .fact_xdl import compile_facts
from .facts import validate_facts
from .protocol.api import settings
from .protocol.io import ROOT, canonical, digest, read_json
from .registry import Registry
from .sources import text_document
from .store import RunStore, atomic_bytes, atomic_json, file_digest

ROLES = ("extractor", "verifier", "repairer", "library_curator")


class CompilationDefect(ValueError):
    """A structurally valid fact was lost or invented by deterministic export."""


@dataclass(frozen=True)
class ConversionSpec:
    output_dir: str = "outputs"
    domain: str = "experimental.facts/1"
    registry_path: str | None = None
    curate: bool = True
    max_calls: int | None = None
    max_seconds: int = 900
    workers: int = 3
    models: dict = field(default_factory=dict)


@dataclass
class Runtime:
    records: object = None
    client_factory: object = None
    offline: bool = False
    progress: object = None
    expected_run_id: str | None = None
    backend_identity: str | None = None
    registry_snapshot: dict | None = None


def _code_revision(_=None):
    return digest({p.relative_to(ROOT).as_posix(): file_digest(p) for p in sorted((ROOT / "src/mosaic").rglob("*.py"))})


def _pin(document):
    return {"source_id": document["id"], "text_sha256": document["text_sha256"]}


def convert(spec: ConversionSpec, *, runtime=None):
    runtime = runtime or Runtime()
    records = copy.deepcopy(list(runtime.records or []))
    if not records:
        raise ValueError("Provide experimental procedure text; implicit database inputs are disabled")
    max_calls = 3 * len(records) + 2 if spec.max_calls is None else spec.max_calls
    if max_calls < 0 or spec.max_seconds <= 0 or not 1 <= spec.workers <= 16 or set(spec.models) - set(ROLES):
        raise ValueError("Invalid call budget, concurrency, deadline or model role")
    if spec.domain != "experimental.facts/1":
        raise ValueError("Unsupported facts contract: " + spec.domain)
    if len({r["id"] for r in records}) != len(records):
        raise ValueError("Source identifiers must be unique")
    for raw in records:
        if raw.get("raw") is not None and digest(raw["raw"]) != raw.get("raw_sha256"):
            raise ValueError("Source record hash mismatch: " + raw["id"])
        raw.setdefault("raw_sha256", digest({"text": raw["procedure"]}))
        text_document(raw)
    registry = Registry(runtime.registry_snapshot) if runtime.registry_snapshot is not None else Registry(read_json(spec.registry_path)) if spec.registry_path else Registry()
    library_paths = sorted((ROOT / "libraries").glob("*.yaml")) + [ROOT / "requirements.lock.txt", ROOT / "pyproject.toml"]
    library_files = {p.relative_to(ROOT).as_posix(): file_digest(p) for p in library_paths}
    evaluation_files = {p.relative_to(ROOT).as_posix(): file_digest(p) for p in sorted((ROOT / "evaluation").rglob("*.json"))}
    default, backend = "injected-client", runtime.backend_identity or "injected-client"
    if not runtime.offline and runtime.client_factory is None and max_calls:
        config = settings()
        default, backend = config["model"], digest({"base_url": config["base_url"]})
        if runtime.backend_identity and backend != runtime.backend_identity:
            raise ValueError("Configured backend changed since this run")
    models = {role: spec.models.get(role, default) for role in ROLES}
    request_spec = {k: v for k, v in asdict(spec).items() if k not in {"output_dir", "registry_path"}}
    request_spec["models"] = models
    request = {"schema": "mosaic.conversion/2", "spec": request_spec,
        "sources": [{"id": r["id"], "sha256": digest(r)} for r in records],
        "registry_revision": registry.revision, "library_files": library_files, "evaluation_files": evaluation_files,
        "code_revision": _code_revision(), "backend_identity": backend, "completion_limit": max_calls,
        "record_completion_limit": 3, "batch_curation_completion_limit": 2,
        "runtime_versions": {"python": sys.version.split()[0], **{name: version(name) for name in ("requests", "PyYAML", "lxml", "jsonpatch", "pydantic", "pydantic_core")}},
        "rubric": {"structure": 1, "compilation_conservation": 1, "critical_errors": 0,
                   "reference_required_recall": REFERENCE_RECALL_MIN, "expert_reference_required_for_bulk": True}}
    run_id = "mosaic_" + digest(request)[:20]
    if runtime.expected_run_id and runtime.expected_run_id != run_id:
        raise ValueError("Cannot resume after code, libraries, evaluation, configuration or source inputs changed")
    store = RunStore(Path(spec.output_dir) / run_id, request)
    if store.manifest["status"] != "running":
        store.verify()
        return {**store.manifest["result"], "new_model_calls": 0}
    started = time.monotonic()
    runner = AgentRunner(store, models=models, max_calls=max_calls, offline=runtime.offline,
                         client_factory=runtime.client_factory, max_seconds=spec.max_seconds)
    prior_calls = runner.calls
    runner.program("registry", registry.revision, lambda: registry.snapshot)
    records = runner.program("sources", request["sources"], lambda: records)
    bundles, failures, converted = {}, [], []
    sources = {r["id"]: r["procedure"] for r in records}

    def extraction(raw):
        document = text_document(raw)
        return runner.program("fact_extraction", _pin(document), lambda: extract_facts(document, runner))

    with ThreadPoolExecutor(max_workers=spec.workers) as executor:
        pending = [(raw, executor.submit(extraction, raw)) for raw in records]
        for raw, future in pending:
            try:
                bundles[raw["id"]] = future.result()
            except Exception as error:
                failures.append(_failure(raw, "fact_extraction", error))
            if runtime.progress:
                runtime.progress({"facts_complete": len(bundles), "total": len(records), "failed": len(failures), "model_calls": runner.calls})
    observed_bundles = dict(bundles)
    for raw in records:
        if raw["id"] not in observed_bundles:
            receipt = store.find("program/typed_facts", _pin(text_document(raw)))
            if receipt:
                observed_bundles[raw["id"]] = {"facts": receipt[0], "verification_status": "incomplete"}
    maintenance = runner.program("library_maintenance", {"facts": digest(observed_bundles), "registry": registry.revision},
        lambda: _maintain(registry, observed_bundles, sources, runner if spec.curate else None))
    evolved = Registry(maintenance["snapshot"])
    for raw in records:
        if raw["id"] not in bundles:
            continue
        try:
            bundle = bundles[raw["id"]]
            protocol = runner.program("compilation", {"facts": digest(bundle), "registry": evolved.revision},
                lambda: _record(raw, bundle, evolved, run_id))
            converted.append(protocol)
        except Exception as error:
            failures.append(_failure(raw, "binding_or_compilation", error))
    candidates = []
    for failure in failures:
        raw = next(r for r in records if r["id"] == failure["raw_id"])
        receipt = store.find("program/typed_facts", _pin(text_document(raw)))
        bundle = bundles.get(raw["id"], {"facts": receipt[0] if receipt else None})
        candidates.append(_candidate(raw, bundle, failure, run_id))
    if _code_revision() != request["code_revision"] or any(file_digest(ROOT / p) != checksum for p, checksum in library_files.items()):
        raise ValueError("Code or libraries changed during conversion; refusing mixed-version output")
    for name, values in (("records", converted), ("sources", records), ("failures", failures), ("candidates", candidates),
                         ("facts", [{"raw_id": source_id, **bundle} for source_id, bundle in bundles.items()])):
        _write_records(store, name + ".jsonl", values)
    for record in converted:
        path = "xdl/" + record["id"] + ".xdl"
        atomic_bytes(store.root / path, record["xdl"].encode("utf-8"))
        store.track_file("xdl/" + record["id"], path)
        sidecar = {"record_id": record["id"], "text_sha256": record["text_sha256"],
                   **{k: v for k, v in record["compiled"].items() if k != "xml"}}
        relative = "xdl/" + record["id"] + ".json"
        atomic_json(store.root / relative, sidecar)
        store.track_file("sidecar/" + record["id"], relative)
    operation_inventory, equipment_inventory = _inventories(observed_bundles, evolved)
    for name, data in (("library_registry", evolved.snapshot), ("library_evolution", maintenance["report"]),
                       ("atomic_operations", operation_inventory), ("equipment_inventory", equipment_inventory)):
        atomic_json(store.root / (name + ".json"), data)
        store.track_file("library/" + name, name + ".json")
    engineering = {"schema": "mosaic.batch-evaluation/1", "input_count": len(records), "converted": len(converted),
        "failed": len(failures), "end_to_end_representation_rate": len(converted) / len(records),
        "fact_conservation": [dict(raw_id=r["raw_id"], **r["compilation_check"]) for r in converted],
        "errors": failures, "model_audit_issues": sum(len(b["audit"]["issues"]) for b in bundles.values()),
        "expert_reference_scored": False, "extraction_accuracy": None, "bulk_gate_passed": False,
        "gate_reason": "Expert-confirmed complete references are required; representation is not factual accuracy.",
        "wall_seconds": round(time.monotonic() - started, 3), "usage": _usage(store)}
    atomic_json(store.root / "evaluation.json", engineering)
    store.track_file("evaluation", "evaluation.json")
    result = {"run_id": run_id, "run_dir": str(store.root), "converted": len(converted), "total": len(records),
        "failures": len(failures), "model_calls": runner.calls, "new_model_calls": runner.calls - prior_calls,
        "input_contract": "text-only/1", "facts_contract": "mosaic.facts/1", "registry_revision": evolved.revision,
        "library_registry": "library_registry.json", "library_evolution": "library_evolution.json",
        "evaluation": "evaluation.json", "review_bundle": {"records": "records.jsonl", "candidates": "candidates.jsonl"}}
    store.finish("partial" if failures else "complete", result)
    store.verify()
    atomic_json(Path(spec.output_dir) / "current.json", {"run_id": run_id, "manifest": run_id + "/manifest.json"})
    return result


def _maintain(registry, bundles, sources, runner):
    evolved, report = maintain_facts_library(registry, bundles, sources, runner)
    return {"snapshot": evolved.snapshot, "report": report}


def _failure(raw, stage, error):
    from .agents import CallBudgetExceeded
    kind = "program_defect" if isinstance(error, CompilationDefect) else "budget" if isinstance(error, CallBudgetExceeded) else "transport" if isinstance(error, RuntimeError) else "contract_or_representation" if isinstance(error, ValueError) else "program_defect"
    return {"raw_id": raw["id"], "stage": stage, "error_class": type(error).__name__, "category": kind, "error": str(error)[:3000]}


def _record(raw, bundle, registry, run_id):
    document = text_document(raw)
    graph = validate_facts(bundle["facts"], document["procedure"])
    if not any(event["kind"] != "observation" for event in graph["events"]):
        raise ValueError("Source has no represented physical action")
    bindings = bind_facts(graph, registry.snapshot)
    compiled = compile_facts(graph, bindings, text=document["procedure"])
    check = check_conservation(graph, bindings, compiled)
    if not check["passed"]:
        raise CompilationDefect("Compilation conservation failed: " + canonical(check["issues"]))
    from .protocol.xdl_document import read_document
    decoded = read_document(compiled["xml"], extensions=compiled["extensions"])
    steps = []
    for index, step in enumerate(decoded["steps"]):
        event_ids = [e for e, positions in compiled["event_locations"].items() if index in positions]
        evidence_ids = [i for event in graph["events"] if event["event_id"] in event_ids for i in event["evidence_ids"]]
        quotes = [e["quote"] for e in graph["evidence"] if e["evidence_id"] in evidence_ids]
        steps.append({"id": "s" + str(index + 1), **step, "event_ids": event_ids, "meta": {"evidence": "\n".join(quotes)}})
    blockers = ["expert_review_pending"]
    if bundle["audit"]["issues"]:
        blockers.append("model_audit_findings_require_review")
    return {"id": "mosaic_pos_" + digest([run_id, raw["id"]])[:20], "record_type": "positive",
        "raw_id": raw["id"], "raw_sha256": document["raw_sha256"], "source": document["source"],
        "source_text": document["procedure"], "text_sha256": document["text_sha256"], "facts": graph,
        "bindings": bindings, "steps": steps, "reagents": [dict(id=e["entity_id"], name=e["name"]) for e in graph["entities"] if e["kind"] != "equipment"],
        "hardware": {"nodes": {i: {**binding, "configuration": compiled["hardware_config"][i]} for i, binding in bindings["equipment"].items()}},
        "xdl": compiled["xml"], "xdl_extensions": compiled["extensions"], "compiled": compiled, "compilation_check": check,
        "quality": {"tier": "silver", "manual_review": "pending", "gold_blockers": blockers,
                    "missing_parameters": compiled["missing_parameters"], "execution_ready": False, "scientific_accuracy_certified": False},
        "crosscheck": {"tier": "silver", "checks": {"fact_conservation": check["passed"]}, "gold_blockers": blockers},
        "extraction": {k: v for k, v in bundle.items() if k != "facts"},
        "mosaic": {"schema": "mosaic.facts-record/1", "run_id": run_id, "registry_revision": registry.revision}}


def _candidate(raw, bundle, failure, run_id):
    document = text_document(raw)
    return {"id": "mosaic_unresolved_" + digest([run_id, raw["id"]])[:20], "raw_id": raw["id"],
        "record_type": "other", "source_text": document["procedure"], "source": document["source"],
        "raw_sha256": document["raw_sha256"], "text_sha256": document["text_sha256"], **bundle,
        "quality": {"tier": "silver", "manual_review": "pending", "gold_blockers": [failure["category"]],
                    "conversion_status": "incomplete_not_a_positive"},
        "mosaic": {"schema": "mosaic.facts-record/1", "run_id": run_id, "conversion_failure": failure}}


def _write_records(store, relative, records):
    payload = "".join(canonical(record) + "\n" for record in records).encode("utf-8")
    path = store.root / relative
    if path.exists() and path.read_bytes() != payload:
        raise ValueError("Refusing to overwrite frozen output: " + relative)
    atomic_bytes(path, payload)
    store.track_file("output/" + relative, relative)


def _usage(store):
    counts, tokens, transport = {}, {}, 0
    for event in store.manifest["events"]:
        if event["engine"] in {"llm", "llm_failed", "cache_replay"}:
            role = event["stage"].split("/")[-1]
            counts[role] = counts.get(role, 0) + 1
            from .protocol.io import read_json
            receipt = read_json(store.root / event["artifact"])
            transport += receipt.get("transport_attempts", 0)
            for key, value in event["usage"].items():
                if isinstance(value, int) and event["engine"] == "llm":
                    tokens[key] = tokens.get(key, 0) + value
    return {"completions_by_role": counts, "tokens": tokens, "http_attempts": transport,
            "cache_replays": sum(e["engine"] == "cache_replay" for e in store.manifest["events"])}


def _inventories(bundles, registry):
    from collections import Counter
    operations, equipment, unresolved = Counter(), Counter(), []
    for source_id, bundle in bundles.items():
        binding = bind_facts(bundle["facts"], registry.snapshot)
        operations.update(item["operation_id"] for item in binding["events"].values())
        equipment.update(item["subtype_id"] for item in binding["equipment"].values())
        unresolved.extend({"source_id": source_id, **item} for item in binding["unresolved"])
    return ({"operations": registry.snapshot["canonical_operations"], "observed_event_counts": dict(operations),
             "unresolved": [u for u in unresolved if u["kind"] == "operation"]},
            {"catalog": registry.snapshot["equipment_catalog"], "observed_instance_counts": dict(equipment),
             "unresolved": [u for u in unresolved if u["kind"] == "equipment"]})


def resume(run_dir, *, offline=False, client_factory=None, runtime=None):
    root = Path(run_dir).resolve()
    request = read_json(root / "manifest.json")["request"]
    if request["schema"] != "mosaic.conversion/2":
        raise ValueError("Legacy conversion receipts remain readable but cannot resume under the new Facts contract")
    store = RunStore(root, request)
    store.verify()
    sources = store.find("program/sources", request["sources"])
    registry = store.find("program/registry", request["registry_revision"])
    if not sources or not registry:
        raise ValueError("Run has no frozen source or registry receipt")
    runtime = runtime or Runtime()
    runtime.records, runtime.offline, runtime.registry_snapshot = sources[0], offline, registry[0]
    runtime.client_factory = client_factory or runtime.client_factory
    runtime.expected_run_id, runtime.backend_identity = root.name, request["backend_identity"]
    return convert(ConversionSpec(output_dir=str(root.parent), **request["spec"]), runtime=runtime)
