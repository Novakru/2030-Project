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
from .chemistry import ChemistryDomain, PhotochemistryDomain
from .evidence import SourceSpan
from .store import RunStore, atomic_bytes, atomic_json, file_digest


@dataclass(frozen=True)
class BuildSpec:
    output_dir: str = "data/mosaic"
    domain: str = "chemistry.batch/1"
    positives: int = 140
    per_risk: int = 12
    text_limit: int = 10
    llm_perturbations: int = 4
    max_calls: int = 60
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


def _select(domain, limit, text_limit):
    pools, text_pools = defaultdict(deque), defaultdict(list)
    for raw in read_raw():
        if domain.eligible(raw):
            name = raw["source"].get("dataset_id", raw["source"].get("url", "unknown"))
            if domain.text_ready(raw):
                text_pools[name].append(raw)
            if domain.structured_ready(raw) and len(pools[name]) < max(20, limit):
                pools[name].append(raw)
    # Start with compact procedures. Very long generic recipes often describe a
    # different scale from the record's structured quantities and need review.
    text_pools = {name: deque(sorted(rows, key=lambda r: (len(r["procedure"]), r["id"])))
                  for name, rows in text_pools.items()}
    selected, seen_texts, seen_ids = [], set(), set()
    while any(text_pools.values()) and len(selected) < min(text_limit, limit):
        for name in sorted(text_pools):
            while text_pools[name]:
                raw = text_pools[name].popleft()
                text_hash = digest(raw["procedure"])
                if text_hash not in seen_texts:
                    selected.append(raw)
                    seen_texts.add(text_hash)
                    seen_ids.add(raw["id"])
                    break
            if len(selected) >= min(text_limit, limit):
                break
    while any(pools.values()) and len(selected) < limit * 4:
        for name in sorted(pools):
            if pools[name]:
                raw = pools[name].popleft()
                if raw["id"] not in seen_ids:
                    selected.append(raw)
                    seen_ids.add(raw["id"])
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


def _extract_source(raw, domain, runner, run_id, use_model):
    stage_input = {"raw": digest(raw), "domain": domain.name, "text": use_model}
    extracted = runner.program("extraction", stage_input,
        lambda: domain.extract(copy.deepcopy(raw), runner, use_model=use_model))
    parent = runner.program("source_validation", {"extracted": digest(extracted), "raw": digest(raw)},
        lambda: domain.validate(copy.deepcopy(extracted), copy.deepcopy(raw), run_id))
    return extracted, parent


def build(spec: BuildSpec, *, runtime=None):
    runtime = runtime or Runtime()
    if min(spec.positives, spec.per_risk) <= 0 or min(spec.text_limit, spec.llm_perturbations, spec.max_calls) < 0 or not 1 <= spec.workers <= 16:
        raise ValueError("Invalid dataset size or call budget")
    domains = {d.name: d for d in (ChemistryDomain(), PhotochemistryDomain())}
    domain = runtime.domain or domains.get(spec.domain)
    if domain is None or domain.name != spec.domain:
        raise ValueError("No implementation registered for domain " + spec.domain)
    records = list(runtime.records) if runtime.records is not None else _select(domain, spec.positives, spec.text_limit)
    if not records:
        raise ValueError("No eligible source records")
    if len({r["id"] for r in records}) != len(records):
        raise ValueError("Source identifiers must be unique")
    if any(r.get("raw") is not None and digest(r["raw"]) != r.get("raw_sha256") for r in records):
        raise ValueError("Source record hash mismatch")
    registry = domain.registry()
    library_paths = {str(i) + ":" + Path(p).name: Path(p) for i, p in enumerate(domain.library_paths())}
    library_files = {name: file_digest(path) for name, path in library_paths.items()}
    roles = ("extractor", "critic", "apparatus_mapper", "perturber")
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
    request_spec = {k: v for k, v in asdict(spec).items() if k != "output_dir"}
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
    records = runner.program("sources", request["sources"], lambda: records)
    parents, failures, source_texts, changes = [], [], {}, []
    reactions, seen_texts, model_records = Counter(), set(), []
    for raw in records:
        text_hash = digest(raw.get("procedure"))
        if len(raw.get("procedure") or "") > 400 and text_hash not in seen_texts and len(model_records) < spec.text_limit:
            model_records.append(raw)
            seen_texts.add(text_hash)
    executor = ThreadPoolExecutor(max_workers=spec.workers)
    pending = {r["id"]: executor.submit(_extract_source, r, domain, runner, run_id, True) for r in model_records}
    try:
        for raw in records:
            if len(parents) >= spec.positives:
                break
            if raw.get("raw") is not None and digest(raw["raw"]) != raw.get("raw_sha256"):
                raise ValueError("Source record hash mismatch: " + raw["id"])
            if raw.get("reaction_smiles") and reactions[raw["reaction_smiles"]] >= 3:
                continue
            use_model = raw["id"] in pending
            stage_input = {"raw": digest(raw), "domain": spec.domain, "text": use_model}
            extracted = None
            try:
                extracted, parent = pending[raw["id"]].result() if use_model else _extract_source(raw, domain, runner, run_id, False)
                if (parent.get("raw_id") != raw["id"] or parent.get("raw_sha256") != raw["raw_sha256"]
                        or parent.get("source") != raw["source"]):
                    raise ValueError("Domain output changed source identity")
                if not re.fullmatch(r"[A-Za-z0-9_-]{1,180}", parent["id"]):
                    raise ValueError("Invalid generated record identifier")
                parent["record_type"] = "positive"
                parent.setdefault("split_group", parent["raw_id"])
                split_value = int(digest(parent["split_group"])[:8], 16) % 100
                parent["split"] = "train" if split_value < 70 else "val" if split_value < 85 else "test"
                parents.append(parent)
                reactions[raw.get("reaction_smiles")] += 1
                text = raw.get("procedure") or ""
                source_texts[raw["id"]] = text
                for node in parent.get("hardware", {}).get("nodes", {}).values():
                    if node.get("binding_basis") != "source_reported":
                        continue
                    for citation in node.get("source_evidence", []):
                        quote = citation.get("value")
                        if isinstance(quote, dict):
                            source_id = raw["id"] + "/setup"
                            source_texts[source_id] = canonical(raw.get("setup", {}).get("vessel", {}))
                            quote = canonical(quote)
                        else:
                            source_id = raw["id"]
                        evidence_text = source_texts.get(source_id, "")
                        if not isinstance(quote, str) or quote not in evidence_text:
                            continue
                        changes.append({"action": "observe_device", "device": {
                            "identity": {"manufacturer": None, "model": node.get("model")},
                            "kind": node.get("apparatus_kind"), "params": node.get("params", {}),
                            "parameter_scope": node.get("capacity_scope"), "verified": False},
                            "evidence": [SourceSpan.locate(source_id, evidence_text, quote).to_dict()]})
                        break
            except (ValueError, RuntimeError, KeyError, TypeError) as error:
                cached_extraction = store.find("program/extraction", stage_input)
                extracted = cached_extraction[0] if cached_extraction else None
                if extracted:
                    source_texts[raw["id"]] = raw.get("procedure") or ""
                    for action in extracted.get("protocol", {}).get("extraction", {}).get("unmapped_actions", []):
                        quote = action.get("evidence") if isinstance(action, dict) else None
                        if quote and quote in source_texts[raw["id"]]:
                            changes.append({"action": "propose_operation", "name": "unmapped_" + digest(quote)[:12],
                                "counterexample": {"raw_id": raw["id"], "unmapped_action": action, "failure": str(error)[:600]},
                                "evidence": [SourceSpan.locate(raw["id"], source_texts[raw["id"]], quote).to_dict()]})
                failure = {"raw_id": raw["id"], "stage": "extraction_or_validation", "error": str(error)[:600], "text_attempted": use_model}
                failures.append(failure)
                store.save("quarantine", stage_input, failure, engine="program")
            if runtime.progress:
                runtime.progress({"accepted": len(parents), "target": spec.positives, "failed": len(failures), "model_calls": runner.calls})
    finally:
        executor.shutdown(wait=True, cancel_futures=True)
    evolved = registry.evolve(changes, expected_revision=registry.revision, sources=source_texts) if changes else registry
    runner.program("library_maintenance", {"revision": registry.revision, "changes": changes},
        lambda: {"revision": evolved.revision, "snapshot": evolved.snapshot, "compact": evolved.compact_device_observations()})
    for parent in parents:
        parent.setdefault("mosaic", {}).update(registry_revision=registry.revision, observation_revision=evolved.revision)
    negatives, mutation_report = runner.program("perturbation", {"parents": digest(parents), "per_risk": spec.per_risk, "llm_limit": spec.llm_perturbations},
        lambda: domain.mutate(parents, runner, per_risk=spec.per_risk, llm_limit=spec.llm_perturbations))
    for sample in negatives:
        parent = next(p for p in parents if p["id"] == sample["parent_id"])
        sample["split"], sample["split_group"] = parent["split"], parent["split_group"]
        sample["record_type"] = "negative"
    primary_count = len(parents)
    supplement_report = {}
    if hasattr(domain, "supplements"):
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
    _write_records(store, folder + "/positives.jsonl", parents)
    _write_records(store, folder + "/negatives.jsonl", negatives)
    _write_records(store, folder + "/quarantined.jsonl", failures)
    selected_ids = {p.get("raw_id") for p in parents}
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
    if isinstance(domain, ChemistryDomain):
        from .catalog import atomic_inventory, equipment_inventory
        inventory = atomic_inventory([p for p in parents if "steps" in p], [p for p in parents if "steps" in p])
        atomic_json(store.root / folder / "atomic_operations.json", inventory)
        store.track_file("library/atomic_operations", folder + "/atomic_operations.json")
        atomic_json(store.root / folder / "equipment_inventory.json", equipment_inventory(parents))
        store.track_file("library/equipment_inventory", folder + "/equipment_inventory.json")
    counts = Counter(n["label"]["risk_l2"] for n in negatives)
    gaps = {risk: spec.per_risk - counts[risk] for risk in registry.snapshot["risks"] if counts[risk] < spec.per_risk}
    result = {"run_id": run_id, "run_dir": str(store.root), "positives": len(parents), "negatives": len(negatives),
              "primary_positives": primary_count, "supplement_counts": supplement_report.get("counts", {}),
              "positive_shortfall": max(0, spec.positives - primary_count), "risk_shortfalls": gaps,
              "model_calls": runner.calls, "replayed_stages": dict(runner.replayed), "failures": len(failures),
              "mutation_report": mutation_report, "registry_revision": evolved.revision,
              "review_bundle": {"positives": folder + "/positives.jsonl", "negatives": folder + "/negatives.jsonl"}}
    status = "complete" if not result["positive_shortfall"] and not gaps else "partial"
    store.finish(status, result)
    store.verify()
    atomic_json(Path(spec.output_dir) / "current.json", {"run_id": run_id, "manifest": run_id + "/manifest.json"})
    return result


def resume(run_dir, *, offline=False, client_factory=None, runtime=None):
    run_dir = Path(run_dir).resolve()
    manifest = read_json(run_dir / "manifest.json")
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
    runtime.client_factory = client_factory or runtime.client_factory
    runtime.source_archive_sha256, runtime.expected_run_id = archive_sha256, run_dir.name
    runtime.backend_identity = manifest["request"]["backend_identity"]
    return build(spec, runtime=runtime)
