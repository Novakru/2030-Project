"""Convert literal procedures into source-pinned, replayable XDL records."""
from __future__ import annotations

import copy
import inspect
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .agents import AgentRunner
from .evidence import SourceSpan
from .protocol.api import settings
from .protocol.io import ROOT, canonical, digest, read_json
from .registry import Registry
from .sources import text_document
from .store import RunStore, atomic_bytes, atomic_json, file_digest

ROLES = ("extractor", "critic", "apparatus_mapper", "library_curator", "operation_expander")


@dataclass(frozen=True)
class ConversionSpec:
    output_dir: str = "outputs"
    domain: str = "chemistry.extended/1"
    registry_path: str = None
    curate: bool = True
    max_calls: int = 100
    workers: int = 4
    models: dict = field(default_factory=dict)


@dataclass
class Runtime:
    records: object = None
    domain: object = None
    client_factory: object = None
    offline: bool = False
    progress: object = None
    expected_run_id: str = None
    backend_identity: str = None
    registry_snapshot: dict = None


def _code_revision(domain):
    hashes = {p.relative_to(ROOT).as_posix(): file_digest(p) for p in sorted((ROOT / "src/mosaic").rglob("*.py"))}
    hashes["domain:" + domain.name] = file_digest(inspect.getfile(type(domain)))
    return digest(hashes)


def _admit_record(protocol, raw):
    document = text_document(raw)
    if (protocol.get("raw_id") != raw["id"] or protocol.get("raw_sha256") != raw["raw_sha256"]
            or protocol.get("source") != document["source"]):
        raise ValueError("Conversion changed source identity")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,180}", protocol["id"]):
        raise ValueError("Invalid converted record identifier")
    protocol.update(record_type="positive", source_text=document["procedure"], text_sha256=document["text_sha256"])
    return protocol


def convert(spec: ConversionSpec, *, runtime=None):
    runtime = runtime or Runtime()
    if spec.max_calls < 0 or not 1 <= spec.workers <= 16 or set(spec.models) - set(ROLES):
        raise ValueError("Invalid call budget, concurrency or model role")
    from .extended_chemistry import ExtendedChemistryDomain
    domain = runtime.domain or ExtendedChemistryDomain()
    if domain.name != spec.domain:
        raise ValueError("No implementation registered for domain " + spec.domain)
    records = copy.deepcopy(list(runtime.records)) if runtime.records is not None else []
    if not records:
        raise ValueError("Provide experimental procedure text; implicit database inputs are disabled")
    if len({r["id"] for r in records}) != len(records):
        raise ValueError("Source identifiers must be unique")
    for raw in records:
        if raw.get("raw") is not None and digest(raw["raw"]) != raw.get("raw_sha256"):
            raise ValueError("Source record hash mismatch: " + raw["id"])
        raw.setdefault("raw_sha256", digest({"text": raw["procedure"]}))
        text_document(raw)
    registry = (Registry(runtime.registry_snapshot) if runtime.registry_snapshot is not None else
                Registry(read_json(spec.registry_path)) if spec.registry_path else domain.registry())
    domain = domain.with_registry(registry) if hasattr(domain, "with_registry") else domain
    paths = {str(i) + ":" + Path(p).name: Path(p) for i, p in enumerate(domain.library_paths())}
    library_files = {name: file_digest(path) for name, path in paths.items()}
    default = "injected-client"
    backend = runtime.backend_identity or ("injected-client" if runtime.client_factory else "program-only")
    if not runtime.offline and runtime.client_factory is None and spec.max_calls:
        config = settings()
        default = config["model"]
        actual_backend = digest({"base_url": config["base_url"]})
        if runtime.backend_identity and actual_backend != runtime.backend_identity:
            raise ValueError("Configured backend changed since this run")
        backend = actual_backend
    models = {role: spec.models.get(role, default) for role in ROLES}
    request_spec = {k: v for k, v in asdict(spec).items() if k not in {"output_dir", "registry_path"}}
    request_spec["models"] = models
    request = {"schema": "mosaic.conversion/1", "spec": request_spec,
               "sources": [{"id": r["id"], "sha256": digest(r)} for r in records],
               "registry_revision": registry.revision, "library_files": library_files,
               "code_revision": _code_revision(domain), "backend_identity": backend}
    run_id = "mosaic_" + digest(request)[:20]
    if runtime.expected_run_id and runtime.expected_run_id != run_id:
        raise ValueError("Cannot resume after code, libraries, configuration or source inputs changed")
    store = RunStore(Path(spec.output_dir) / run_id, request)
    runner = AgentRunner(store, models=models, max_calls=spec.max_calls, offline=runtime.offline,
                         client_factory=runtime.client_factory)
    prior_calls = runner.calls
    runner.program("registry", registry.revision, lambda: registry.snapshot)
    records = runner.program("sources", request["sources"], lambda: records)
    converted, failures, observations, snapshots = [], [], [], []
    sources = {r["id"]: r["procedure"] for r in records}

    def collect(raw, outcome=None, error=None):
        extracted, protocol = outcome or (None, None)
        if error is not None:
            stage_input = _extraction_input(raw, domain)
            cached = store.find("program/extraction", stage_input)
            extracted = cached[0] if cached else None
            saved = store.find("quarantine", stage_input)
            failure = saved[0] if saved else {"raw_id": raw["id"], "stage": "extraction_or_validation",
                                             "error": str(error)[:600], "text_attempted": True}
            failures.append(failure)
            if not saved:
                store.save("quarantine", stage_input, failure, engine="program")
        else:
            converted.append(_admit_record(protocol, raw))
        if extracted and isinstance(extracted.get("protocol"), dict):
            snapshots.append(extracted["protocol"])
            observations.extend(_observations(protocol or extracted["protocol"], text_document(raw), registry))
            for mention in extracted.get("notes", {}).get("apparatus_proposals", []):
                quote = mention.get("quote")
                if isinstance(quote, str) and quote and quote in raw["procedure"]:
                    observations.append({"kind": "device", "device": {"kind": mention.get("kind"),
                        "identity": {"manufacturer": None, "model": None}, "params": {},
                        "parameter_scope": mention.get("scope"), "verified": False},
                        "evidence": [SourceSpan.locate(raw["id"], raw["procedure"], quote).to_dict()]})

    with ThreadPoolExecutor(max_workers=spec.workers) as executor:
        pending = [(raw, executor.submit(_extract_source, raw, domain, runner, run_id)) for raw in records]
        for raw, future in pending:
            try:
                collect(raw, outcome=future.result())
            except (ValueError, RuntimeError, KeyError, TypeError) as error:
                collect(raw, error=error)
            if runtime.progress:
                runtime.progress({"converted": len(converted), "total": len(records),
                                  "failed": len(failures), "model_calls": runner.calls})

    def curate():
        from .evolution import maintain_library
        evolved, report = maintain_library(registry, observations, sources=sources,
                                          runner=runner if spec.curate else None, domain=domain)
        return {"snapshot": evolved.snapshot, "report": report}

    maintenance = runner.program("library_maintenance", {"revision": registry.revision, "observations": observations}, curate)
    evolved = Registry(maintenance["snapshot"])
    retry_ids = set(maintenance["report"].get("retryable_source_ids", [])) & {f["raw_id"] for f in failures}
    retried = []
    if retry_ids and hasattr(domain, "with_registry"):
        retry_domain = domain.with_registry(evolved)
        for raw in records:
            if raw["id"] not in retry_ids:
                continue
            try:
                extracted, protocol = _extract_source(raw, retry_domain, runner, run_id)
                converted.append(_admit_record(protocol, raw))
                failures = [f for f in failures if f["raw_id"] != raw["id"]]
                retried.append({"raw_id": raw["id"], "status": "represented_after_verified_library_change"})
            except (ValueError, RuntimeError, KeyError, TypeError) as error:
                retried.append({"raw_id": raw["id"], "status": "still_unresolved", "error": str(error)[:600]})
    maintenance["report"]["bounded_retries"] = retried
    if evolved.revision != registry.revision:
        from .canonical import finalize_protocol, registry_vocabulary
        converted = runner.program("evolved_vocabulary_binding", {"records": digest(converted), "registry": evolved.revision},
            lambda: [finalize_protocol(record, vocabulary=registry_vocabulary(evolved)) for record in converted])
    for protocol in converted:
        protocol.setdefault("mosaic", {}).update(registry_revision=registry.revision, observation_revision=evolved.revision)
    if any(file_digest(paths[k]) != v for k, v in library_files.items()) or _code_revision(domain) != request["code_revision"]:
        raise ValueError("Code or libraries changed during conversion; refusing mixed-version output")
    candidates = _review_candidates(failures, records, snapshots, run_id, evolved.revision)
    for name, values in (("records", converted), ("sources", records), ("failures", failures), ("candidates", candidates)):
        _write_records(store, name + ".jsonl", values)
    for protocol in converted:
        relative = "xdl/" + protocol["id"] + ".xdl"
        payload, path = protocol["xdl"].encode("utf-8"), store.root / relative
        if path.exists() and path.read_bytes() != payload:
            raise ValueError("Refusing to overwrite frozen XDL")
        if not path.exists():
            atomic_bytes(path, payload)
        store.track_file("xdl/" + protocol["id"], relative)
    inventories = domain.inventories(converted, snapshots, evolved.snapshot) if hasattr(domain, "inventories") else {}
    inventories["xdl_extensions"] = {"schema": "mosaic.xdl-sidecars/1", "records": {
        record["id"]: {"extensions": record["xdl_extensions"], "bindings": record["xdl_bindings"]}
        for record in converted}}
    inventories.update(library_registry=evolved.snapshot, library_evolution=maintenance["report"])
    for name, value in inventories.items():
        atomic_json(store.root / (name + ".json"), value)
        store.track_file("library/" + name, name + ".json")
    result = {"run_id": run_id, "run_dir": str(store.root), "converted": len(converted), "total": len(records),
              "failures": len(failures), "model_calls": runner.calls, "new_model_calls": runner.calls - prior_calls,
              "input_contract": "text-only/1", "registry_revision": evolved.revision,
              "library_registry": "library_registry.json", "library_evolution": "library_evolution.json",
              "review_bundle": {"records": "records.jsonl", "candidates": "candidates.jsonl"}}
    store.finish("partial" if failures else "complete", result)
    store.verify()
    atomic_json(Path(spec.output_dir) / "current.json", {"run_id": run_id, "manifest": run_id + "/manifest.json"})
    return result


def resume(run_dir, *, offline=False, client_factory=None, runtime=None):
    root = Path(run_dir).resolve()
    manifest = read_json(root / "manifest.json")
    request = manifest["request"]
    if request.get("schema") != "mosaic.conversion/1":
        raise ValueError("This is a legacy dataset batch; convert its source text with mosaic extract")
    stored = RunStore(root, request)
    stored.verify()
    sources = stored.find("program/sources", request["sources"])
    registry = stored.find("program/registry", request["registry_revision"])
    if sources is None or registry is None:
        raise ValueError("Run has no frozen source or registry receipt")
    runtime = runtime or Runtime()
    runtime.records, runtime.offline, runtime.registry_snapshot = sources[0], offline, registry[0]
    runtime.client_factory = client_factory or runtime.client_factory
    runtime.expected_run_id, runtime.backend_identity = root.name, request["backend_identity"]
    return convert(ConversionSpec(output_dir=str(root.parent), **request["spec"]), runtime=runtime)


def _write_records(store, relative, records):
    payload = "".join(canonical(record) + "\n" for record in records).encode("utf-8")
    path = store.root / relative
    if path.exists() and path.read_bytes() != payload:
        raise ValueError("Refusing to overwrite a frozen dataset snapshot")
    if not path.exists():
        atomic_bytes(path, payload)
    store.track_file("output/" + Path(relative).name, relative)

def _extraction_input(raw, domain):
    document = text_document(raw)
    return {"document": digest(document), "domain": domain.name, "registry_revision": domain.registry().revision}

def _extract_source(raw, domain, runner, run_id):
    document = text_document(raw)
    stage_input = _extraction_input(raw, domain)
    quarantined = runner.store.find("quarantine", stage_input)
    if quarantined:
        raise ValueError(quarantined[0]["error"])
    extracted = runner.program("extraction", stage_input,
        lambda: domain.extract(copy.deepcopy(document), runner, use_model=True))
    parent = runner.program("source_validation", {"extracted": digest(extracted), "raw": digest(raw)},
        lambda: domain.validate(copy.deepcopy(extracted), copy.deepcopy(raw), run_id))
    return extracted, parent

def _observations(protocol, document, registry):
    """The curator receives quoted observations, never reference measurements."""
    from mosaic.protocol.normalization import analysis_protocol, is_normalized
    if is_normalized(protocol):
        protocol = analysis_protocol(protocol)
    text, source_id = document["procedure"], document["id"]
    observations = []
    for step in protocol.get("steps", []):
        quote = step.get("meta", {}).get("evidence")
        if isinstance(quote, str) and quote and quote in text:
            observations.append({"kind": "operation", "name": step["op"],
                "contract": registry.snapshot["operations"].get(step["op"]),
                "witness": {"steps": [copy.deepcopy(step)], "operation_definitions":
                    {step["op"]: copy.deepcopy(protocol["operation_definitions"][step["op"]])}
                    if step["op"] in protocol.get("operation_definitions", {}) else {}},
                **({"extension_definition": protocol["operation_definitions"][step["op"]]}
                   if step["op"] in protocol.get("operation_definitions", {}) else {}),
                "evidence": [SourceSpan.locate(source_id, text, quote).to_dict()]})
    for action in protocol.get("extraction", {}).get("unmapped_actions", []):
        quote = action.get("evidence") if isinstance(action, dict) else action
        if isinstance(quote, str) and quote and quote in text:
            observations.append({"kind": "operation", "text": quote,
                "name": action.get("action", action.get("op")) if isinstance(action, dict) else None,
                "evidence": [SourceSpan.locate(source_id, text, quote).to_dict()]})
    for node in protocol.get("hardware", {}).get("nodes", {}).values():
        if node.get("binding_basis") != "source_reported":
            continue
        for citation in node.get("source_evidence", []):
            quote = citation.get("value")
            if isinstance(quote, str) and quote and quote in text:
                observations.append({"kind": "device", "device": {
                    "identity": {"manufacturer": None, "model": node.get("model")},
                    "kind": node.get("apparatus_kind"), "params": node.get("params", {}),
                    "parameter_scope": node.get("capacity_scope"), "verified": False},
                    "evidence": [SourceSpan.locate(source_id, text, quote).to_dict()]})
                break
    return observations

def _review_candidates(failures, records, snapshots, run_id, revision):
    """Keep incomplete conversions reviewable without counting them as positives."""
    raws = {r["id"]: r for r in records}
    proposed = {p.get("raw_id"): p for p in snapshots}
    candidates = []
    for failure in failures:
        document = text_document(raws[failure["raw_id"]])
        candidate = copy.deepcopy(proposed.get(document["id"], {}))
        candidate.update(id="mosaic_unresolved_" + digest([run_id, document["id"]])[:20],
            record_type="other", raw_id=document["id"], raw_sha256=document["raw_sha256"],
            source=document["source"], source_text=document["procedure"], text_sha256=document["text_sha256"])
        candidate.pop("xdl", None)
        candidate["quality"] = {"tier": "silver", "manual_review": "pending",
            "conversion_status": "incomplete_not_a_positive", "source_input_contract": "text-only/1",
            "gold_blockers": ["incomplete_text_representation"], "full_feasibility_certified": False}
        candidate["crosscheck"] = {"tier": "silver", "missing": [failure["error"]],
                                  "gold_blockers": ["incomplete_text_representation"]}
        candidate["mosaic"] = {"schema": "mosaic.ir/2", "run_id": run_id,
                               "registry_revision": revision, "conversion_failure": failure}
        candidates.append(candidate)
    return candidates
