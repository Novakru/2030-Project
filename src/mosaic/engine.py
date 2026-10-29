"""Build/resume one source-pinned batch; every consumer uses its manifest."""
from __future__ import annotations

from collections import Counter, defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path
import re
import copy

from protocol_risk.api import settings
from protocol_risk.ingest import read_raw
from protocol_risk.io import ROOT, canonical, digest, read_json

from .agents import AgentRunner
from .evidence import SourceSpan
from .registry import Registry
from .sources import text_document
from .store import RunStore, atomic_bytes, atomic_json, file_digest


@dataclass(frozen=True)
class BuildSpec:
    output_dir: str = "data/mosaic"
    domain: str = "chemistry.extended/1"
    positives: int = 100
    per_risk: int = 10
    source_limit: int = 0
    registry_path: str = None
    curate: bool = True
    include_reference_supplements: bool = False
    llm_perturbations: int = 4
    max_calls: int = 500
    workers: int = 4
    models: dict = field(default_factory=dict)


@dataclass
class Runtime:
    records: object = None
    domain: object = None
    client_factory: object = None
    offline: bool = False
    progress: object = None
    source_archive_sha256: str = None
    expected_run_id: str = None
    backend_identity: str = None
    registry_snapshot: dict = None


def _select(domain, limit, source_limit=0):
    """Round-robin distinct literal procedures; reference fields never select a path."""
    pools = defaultdict(list)
    for raw in read_raw():
        if domain.eligible(raw):
            name = raw["source"].get("dataset_id", raw["source"].get("url", "unknown"))
            pools[name].append(raw)
    # Prefer substantive text over purification-only fragments, using text alone.
    def priority(raw):
        text = raw["procedure"]
        return (not bool(re.search(r"\b(?:added|charged|mixed|dissolved)\b", text, re.I)),
                not bool(re.search(r"\b(?:mg|mmol|mL|µL|μL)\b", text)),
                not 400 <= len(text) <= 3500, len(text), raw["id"])

    pools = {name: deque(sorted(rows, key=priority)) for name, rows in pools.items()}
    selected, seen_texts = [], set()
    cap = source_limit or limit * 4
    while any(pools.values()) and len(selected) < cap:
        for name in sorted(pools):
            while pools[name]:
                raw = pools[name].popleft()
                text_hash = digest(" ".join(raw["procedure"].split()))
                if text_hash not in seen_texts:
                    selected.append(raw)
                    seen_texts.add(text_hash)
                    break
            if len(selected) >= cap:
                break
    return selected


def _code_revision(domain):
    import inspect
    files = sorted((ROOT / "src/mosaic").glob("*.py")) + sorted((ROOT / "src/protocol_risk").glob("*.py"))
    hashes = {p.relative_to(ROOT).as_posix(): file_digest(p) for p in files}
    hashes["domain:" + domain.name] = file_digest(inspect.getfile(type(domain)))
    return digest(hashes)


def _write_records(store, relative, records):
    payload = "".join(canonical(record) + "\n" for record in records).encode("utf-8")
    path = store.root / relative
    if path.exists() and path.read_bytes() != payload:
        raise ValueError("Refusing to overwrite a frozen dataset snapshot")
    if not path.exists():
        atomic_bytes(path, payload)
    store.track_file("dataset/" + Path(relative).name, relative)


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


def _admit_parent(parent, raw):
    document = text_document(raw)
    if (parent.get("raw_id") != raw["id"] or parent.get("raw_sha256") != raw["raw_sha256"]
            or parent.get("source") != document["source"]):
        raise ValueError("Domain output changed source identity")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,180}", parent["id"]):
        raise ValueError("Invalid generated record identifier")
    parent.update(record_type="positive", source_text=document["procedure"], text_sha256=document["text_sha256"])
    parent.setdefault("split_group", parent["raw_id"])
    split_value = int(digest(parent["split_group"])[:8], 16) % 100
    parent["split"] = "train" if split_value < 70 else "val" if split_value < 85 else "test"
    return parent


def _observations(protocol, document, registry):
    """The curator receives quoted observations, never reference measurements."""
    from protocol_risk.normalization import analysis_protocol, is_normalized
    if is_normalized(protocol):
        protocol = analysis_protocol(protocol)
    text, source_id = document["procedure"], document["id"]
    observations = []
    for step in protocol.get("steps", []):
        quote = step.get("meta", {}).get("evidence")
        if isinstance(quote, str) and quote and quote in text:
            observations.append({"kind": "operation", "name": step["op"],
                "contract": registry.snapshot["operations"].get(step["op"]),
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


def build(spec: BuildSpec, *, runtime=None):
    runtime = runtime or Runtime()
    if spec.positives <= 0 or min(spec.per_risk, spec.source_limit, spec.llm_perturbations, spec.max_calls) < 0 or not 1 <= spec.workers <= 16:
        raise ValueError("Invalid dataset size or call budget")
    from .chemistry import ChemistryDomain, PhotochemistryDomain
    from .extended_chemistry import ExtendedChemistryDomain
    domains = {d.name: d for d in (ExtendedChemistryDomain(), ChemistryDomain(), PhotochemistryDomain())}
    domain = runtime.domain or domains.get(spec.domain)
    if domain is None or domain.name != spec.domain:
        raise ValueError("No implementation registered for domain " + spec.domain)
    records = list(runtime.records) if runtime.records is not None else _select(domain, spec.positives, spec.source_limit)
    if not records:
        raise ValueError("No eligible source records")
    if len({r["id"] for r in records}) != len(records):
        raise ValueError("Source identifiers must be unique")
    if any(r.get("raw") is not None and digest(r["raw"]) != r.get("raw_sha256") for r in records):
        raise ValueError("Source record hash mismatch")
    for raw in records:
        text_document(raw)  # Even injected adapters receive text documents exclusively.
    registry = (Registry(runtime.registry_snapshot) if runtime.registry_snapshot is not None else
                Registry(read_json(Path(spec.registry_path))) if spec.registry_path else domain.registry())
    if hasattr(domain, "with_registry"):
        domain = domain.with_registry(registry)
    library_paths = {str(i) + ":" + Path(p).name: Path(p) for i, p in enumerate(domain.library_paths())}
    library_files = {name: file_digest(path) for name, path in library_paths.items()}
    roles = ("extractor", "critic", "apparatus_mapper", "perturber", "library_curator", "operation_expander")
    default = "gpt-5.6-terra"
    backend_identity = runtime.backend_identity or ("injected-client" if runtime.client_factory else "program-only")
    if not runtime.offline and runtime.client_factory is None and spec.max_calls:
        config = settings()
        default = config["model"]
        current_backend = digest({"base_url": config["base_url"]})
        if runtime.backend_identity and current_backend != runtime.backend_identity:
            raise ValueError("Configured backend changed since this run")
        backend_identity = current_backend
    models = {role: spec.models.get(role, default) for role in roles}
    request_spec = {k: v for k, v in asdict(spec).items() if k not in ("output_dir", "registry_path")}
    request_spec["models"] = models
    request = {"spec": request_spec, "sources": [{"id": r["id"], "sha256": digest(r)} for r in records],
               "registry_revision": registry.revision, "library_files": library_files,
               "code_revision": _code_revision(domain), "backend_identity": backend_identity}
    archive_sha256 = runtime.source_archive_sha256
    if runtime.records is None:
        archive_sha256 = file_digest(ROOT / "data/raw/reactions.parquet")
    if archive_sha256:
        request["raw_archive_sha256"] = archive_sha256
    run_id = "mosaic_" + digest(request)[:20]
    if runtime.expected_run_id and run_id != runtime.expected_run_id:
        raise ValueError("Cannot resume after code, library, request or source inputs changed")
    store = RunStore(Path(spec.output_dir) / run_id, request)
    runner = AgentRunner(store, models=models, max_calls=spec.max_calls, offline=runtime.offline, client_factory=runtime.client_factory)
    prior_model_calls = runner.calls
    runner.program("registry", registry.revision, lambda: registry.snapshot)
    records = runner.program("sources", request["sources"], lambda: records)
    parents, failures, observations, snapshots = [], [], [], []
    source_texts = {raw["id"]: raw["procedure"] for raw in records}
    executor = ThreadPoolExecutor(max_workers=spec.workers)
    queue, pending = iter(records), deque()

    def submit_next():
        raw = next(queue, None)
        if raw is not None:
            pending.append((raw, executor.submit(_extract_source, raw, domain, runner, run_id)))

    for _ in range(spec.workers):
        submit_next()
    try:
        while pending and len(parents) < spec.positives:
            raw, future = pending.popleft()
            if raw.get("raw") is not None and digest(raw["raw"]) != raw.get("raw_sha256"):
                raise ValueError("Source record hash mismatch: " + raw["id"])
            document = text_document(raw)
            stage_input = _extraction_input(raw, domain)
            extracted, parent = None, None
            try:
                extracted, parent = future.result()
                parents.append(_admit_parent(parent, raw))
            except (ValueError, RuntimeError, KeyError, TypeError) as error:
                cached_extraction = store.find("program/extraction", stage_input)
                extracted = cached_extraction[0] if cached_extraction else None
                saved_failure = store.find("quarantine", stage_input)
                failure = saved_failure[0] if saved_failure else {"raw_id": raw["id"], "stage": "extraction_or_validation",
                                                               "error": str(error)[:600], "text_attempted": True}
                failures.append(failure)
                if not saved_failure:
                    store.save("quarantine", stage_input, failure, engine="program")
            if extracted and isinstance(extracted.get("protocol"), dict):
                snapshots.append(extracted["protocol"])
                observations.extend(_observations(parent or extracted["protocol"], document, registry))
                for mention in extracted.get("notes", {}).get("apparatus_proposals", []):
                    quote = mention.get("quote")
                    if isinstance(quote, str) and quote in document["procedure"]:
                        observations.append({"kind": "device", "device": {"kind": mention.get("kind"),
                            "identity": {"manufacturer": None, "model": None}, "params": {},
                            "parameter_scope": mention.get("scope"), "verified": False},
                            "evidence": [SourceSpan.locate(raw["id"], document["procedure"], quote).to_dict()]})
            if len(parents) < spec.positives:
                submit_next()
            if runtime.progress:
                runtime.progress({"accepted": len(parents), "target": spec.positives, "failed": len(failures), "model_calls": runner.calls})
    finally:
        for _, future in pending:
            future.cancel()
        executor.shutdown(wait=True, cancel_futures=True)
    def curate():
        from .evolution import maintain_library
        evolved, report = maintain_library(registry, observations, sources=source_texts,
                                          runner=runner if spec.curate else None, domain=domain)
        return {"revision": evolved.revision, "snapshot": evolved.snapshot, "report": report}

    maintenance = runner.program("library_maintenance", {"revision": registry.revision, "observations": observations}, curate)
    evolved = Registry(maintenance["snapshot"])
    retry_ids = set(maintenance["report"].get("retryable_source_ids", [])) & {f["raw_id"] for f in failures}
    if retry_ids and hasattr(domain, "with_registry"):
        retry_domain = domain.with_registry(evolved)
        retried = []
        for raw in records:
            if raw["id"] not in retry_ids or len(parents) >= spec.positives:
                continue
            try:
                extracted, parent = _extract_source(raw, retry_domain, runner, run_id)
                parents.append(_admit_parent(parent, raw))
                failures = [f for f in failures if f["raw_id"] != raw["id"]]
                retried.append({"raw_id": raw["id"], "status": "represented_after_verified_library_change"})
            except (ValueError, RuntimeError, KeyError, TypeError) as error:
                retry_input = _extraction_input(raw, retry_domain)
                failure = store.find("quarantine", retry_input)
                reason = failure[0]["error"] if failure else str(error)[:600]
                if not failure:
                    store.save("quarantine", retry_input, {"raw_id": raw["id"], "stage": "representation_retry",
                               "error": reason, "text_attempted": True}, engine="program")
                retried.append({"raw_id": raw["id"], "status": "still_unresolved", "error": reason})
        maintenance["report"]["bounded_retries"] = retried
    for parent in parents:
        parent.setdefault("mosaic", {}).update(registry_revision=registry.revision, observation_revision=evolved.revision)
    negatives, mutation_report = runner.program("perturbation", {"parents": digest(parents), "per_risk": spec.per_risk, "llm_limit": spec.llm_perturbations},
        lambda: domain.mutate(parents, runner, per_risk=spec.per_risk, llm_limit=spec.llm_perturbations) if spec.per_risk and parents else ([], {}))
    for sample in negatives:
        parent = next(p for p in parents if p["id"] == sample["parent_id"])
        sample["split"], sample["split_group"] = parent["split"], parent["split_group"]
        sample["record_type"] = "negative"
    primary_count = len(parents)
    supplement_report = {}
    if spec.include_reference_supplements and hasattr(domain, "supplements"):
        supplement_report = runner.program("source_supplements", {"run": run_id, "per_risk": spec.per_risk},
            lambda: domain.supplements(run_id, spec.per_risk))
        parents.extend(supplement_report["parents"])
        negatives.extend(supplement_report["negatives"])
    if any(file_digest(library_paths[name]) != value for name, value in library_files.items()):
        raise ValueError("Libraries changed during the run; refusing a mixed-version dataset")
    if _code_revision(domain) != request["code_revision"]:
        raise ValueError("Program changed during the run; resume with its original code or start a new batch")
    snapshot = digest({"parents": parents, "negatives": negatives})[:20]
    folder = "datasets/" + snapshot
    candidates = _review_candidates(failures, records, snapshots, run_id, evolved.revision)
    _write_records(store, folder + "/positives.jsonl", parents)
    _write_records(store, folder + "/negatives.jsonl", negatives)
    _write_records(store, folder + "/quarantined.jsonl", failures)
    _write_records(store, folder + "/extraction_candidates.jsonl", candidates)
    # Failed conversions are part of the source corpus too. Retain their exact
    # raw snapshots so an expert can reproduce every quarantine/library proposal.
    selected_ids = {p.get("raw_id") for p in parents} | {f["raw_id"] for f in failures}
    _write_records(store, folder + "/raw.jsonl", [raw for raw in records if raw["id"] in selected_ids])
    for record in parents + negatives:
        if isinstance(record.get("xdl"), str):
            relative = folder + "/xdl/" + record["id"] + ".xdl"
            path, payload = store.root / relative, record["xdl"].encode("utf-8")
            if path.exists() and path.read_bytes() != payload:
                raise ValueError("Refusing to overwrite a frozen XDL export")
            if not path.exists():
                atomic_bytes(path, payload)
            store.track_file("xdl/" + record["id"], relative)
    inventories = domain.inventories(parents, snapshots, evolved.snapshot) if hasattr(domain, "inventories") else {}
    inventories.update(library_registry=evolved.snapshot, library_evolution=maintenance["report"])
    for name, inventory in inventories.items():
        atomic_json(store.root / folder / (name + ".json"), inventory)
        store.track_file("library/" + name, folder + "/" + name + ".json")
    counts = Counter(n["label"]["risk_l2"] for n in negatives)
    gaps = {risk: spec.per_risk - counts[risk] for risk in registry.snapshot.get("risks", {}) if counts[risk] < spec.per_risk}
    result = {"run_id": run_id, "run_dir": str(store.root), "positives": len(parents), "negatives": len(negatives),
              "primary_positives": primary_count, "supplement_counts": supplement_report.get("counts", {}),
              "positive_shortfall": max(0, spec.positives - primary_count), "risk_shortfalls": gaps,
              "model_calls": runner.calls, "replayed_stages": dict(runner.replayed), "failures": len(failures),
              "new_model_calls": runner.calls - prior_model_calls,
              "mutation_report": mutation_report, "registry_revision": evolved.revision,
              "input_contract": "text-only/1", "text_primary_positives": primary_count,
              "raw_source_records": sum(raw["id"] in selected_ids for raw in records),
              "extraction_candidates": len(candidates),
              "library_registry": folder + "/library_registry.json", "library_evolution": folder + "/library_evolution.json",
              "review_bundle": {"positives": folder + "/positives.jsonl", "negatives": folder + "/negatives.jsonl",
                                "candidates": folder + "/extraction_candidates.jsonl"}}
    status = "complete" if not result["positive_shortfall"] and not gaps else "partial"
    store.finish(status, result)
    store.verify()
    atomic_json(Path(spec.output_dir) / "current.json", {"run_id": run_id, "manifest": run_id + "/manifest.json"})
    return result


def resume(run_dir, *, offline=False, client_factory=None, runtime=None):
    run_dir = Path(run_dir).resolve()
    manifest = read_json(run_dir / "manifest.json")
    if manifest["request"].get("migration"):
        from .migration import migrate
        return migrate(replay_run=run_dir)
    spec = BuildSpec(output_dir=str(run_dir.parent), **manifest["request"]["spec"])
    stored = RunStore(run_dir, manifest["request"])
    source_batch = stored.find("program/sources", manifest["request"]["sources"])
    if source_batch is None:
        raise ValueError("Run stopped before its source snapshot was written")
    records = source_batch[0]
    # Preserve the original source-adapter identity, including the full archive pin.
    archive_sha256 = manifest["request"].get("raw_archive_sha256")
    if archive_sha256 and archive_sha256 != file_digest(ROOT / "data/raw/reactions.parquet"):
        raise ValueError("Cannot resume after the source archive changed")
    runtime = runtime or Runtime()
    runtime.records, runtime.offline = records, offline
    frozen_registry = stored.find("program/registry", manifest["request"]["registry_revision"])
    if frozen_registry is None:
        raise ValueError("Run has no frozen input registry")
    runtime.registry_snapshot = frozen_registry[0]
    runtime.client_factory = client_factory or runtime.client_factory
    runtime.source_archive_sha256, runtime.expected_run_id = archive_sha256, run_dir.name
    runtime.backend_identity = manifest["request"]["backend_identity"]
    return build(spec, runtime=runtime)
