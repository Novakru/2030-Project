"""Deterministically migrate a frozen batch, replaying faults after parent normalization."""
import copy
from collections import Counter
from pathlib import Path

import jsonpatch

from protocol_risk.io import digest, load_library, read_json, read_jsonl
from protocol_risk.normalization import analysis_protocol
from protocol_risk.symbolic import evaluate

from .canonical import finalize_negative, finalize_protocol
from .catalog import atomic_inventory, equipment_inventory
from .engine import _code_revision, _write_records
from .extended_chemistry import ExtendedChemistryDomain
from .mutations import assess_intervention
from .store import RunStore, atomic_bytes, atomic_json, file_digest


def _inputs(source):
    manifest = read_json(source / "manifest.json")
    RunStore(source, manifest["request"]).verify()
    bundle = manifest["result"]["review_bundle"]
    folder = source / Path(bundle["positives"]).parent
    return {"result": manifest["result"], "request": manifest["request"],
            "source_manifest_sha256": file_digest(source / "manifest.json"),
            "parents": list(read_jsonl(source / bundle["positives"])),
            "negatives": list(read_jsonl(source / bundle["negatives"])),
            "candidates": list(read_jsonl(source / bundle["candidates"])),
            "raws": list(read_jsonl(folder / "raw.jsonl")),
            "failures": list(read_jsonl(folder / "quarantined.jsonl")),
            "registry": read_json(source / manifest["result"]["library_registry"]),
            "evolution": read_json(source / manifest["result"]["library_evolution"])}


def migrate(source_run=None, *, output_dir=None, replay_run=None):
    domain = ExtendedChemistryDomain()
    libraries = {str(i) + ":" + Path(path).name: file_digest(path)
                 for i, path in enumerate(domain.library_paths())}
    revision = _code_revision(domain)
    if replay_run:
        directory = Path(replay_run).resolve()
        manifest = read_json(directory / "manifest.json")
        request = manifest["request"]
        if request["code_revision"] != revision or request["library_files"] != libraries:
            raise ValueError("Migration code or libraries changed; create a new migration")
        store = RunStore(directory, request)
        source = store.find("migration/input", request["migration_input_sha256"])
        if source is None:
            raise ValueError("Migration input receipt is missing")
        inputs = source[0]
    else:
        source = Path(source_run).resolve()
        inputs = _inputs(source)
        request = {"spec": inputs["request"]["spec"], "sources": inputs["request"]["sources"],
                   "code_revision": revision, "library_files": libraries,
                   "migration": {"schema": "mosaic.canonical-migration/1",
                                 "source_run_id": inputs["result"]["run_id"],
                                 "source_manifest_sha256": inputs["source_manifest_sha256"]},
                   "migration_input_sha256": digest(inputs)}
        directory = Path(output_dir or source.parent) / ("mosaic_" + digest(request)[:20])
        store = RunStore(directory, request)
        if store.find("migration/input", request["migration_input_sha256"]) is None:
            store.save("migration/input", request["migration_input_sha256"], inputs, engine="program")
    if digest(inputs) != request["migration_input_sha256"]:
        raise ValueError("Migration input differs from its pin")
    run_id = store.root.name
    parents, before = [], {}
    for original in inputs["parents"]:
        parent = finalize_protocol(original)
        parent.setdefault("mosaic", {}).update(run_id=run_id, migrated_from=inputs["result"]["run_id"])
        parent = finalize_protocol(parent)
        old_result, new_result = evaluate(original), evaluate(parent)
        if (old_result.violations, old_result.unknowns) != (new_result.violations, new_result.unknowns):
            raise ValueError("Normalization changed parent risk analysis: " + original["id"])
        before[parent["id"]] = original
        parents.append(parent)
    by_id = {parent["id"]: parent for parent in parents}
    negatives = []
    operational = {"steps", "reagents", "hardware", "context", "initial_contents"}
    for original in inputs["negatives"]:
        parent = by_id[original["parent_id"]]
        # Apply only the old intentional operational change to the CURRENT
        # analysis projection of a parent that is already canonical.
        patch = jsonpatch.make_patch(before[parent["id"]], original["protocol"]).patch
        patch = [entry for entry in patch if entry["path"].strip("/").split("/")[0] in operational]
        child = jsonpatch.apply_patch(analysis_protocol(parent), patch)
        for field in ("quality", "crosscheck"):
            child[field] = copy.deepcopy(original["protocol"].get(field, {}))
        sample = finalize_negative({**copy.deepcopy(original), "protocol": child}, parent)
        old_result, new_result = evaluate(original["protocol"]), evaluate(sample["protocol"])
        if (old_result.violations, old_result.unknowns) != (new_result.violations, new_result.unknowns):
            raise ValueError("Normalization changed intentional fault analysis: " + original["id"])
        if assess_intervention(parent, sample["protocol"]) != original["mutation"]["intervention"]:
            raise ValueError("Normalization changed intervention: " + original["id"])
        negatives.append(sample)
    registry = copy.deepcopy(inputs["registry"])
    registry.update(schema="mosaic.registry/2", canonical_operations=load_library("atomic_operations.yaml")["operations"],
                    operation_mappings=load_library("operation_mappings.yaml"),
                    equipment_catalog=load_library("equipment.yaml"), equipment_mappings=load_library("equipment_mappings.yaml"))
    registry["source_operation_contracts"] = {**registry.get("source_operation_contracts", {}),
                                            **registry.pop("extension_operations", {})}
    # Historical source contracts are migration evidence, not public vocabulary.
    registry["extension_operations"] = {}
    folder = "datasets/" + digest({"parents": parents, "negatives": negatives})[:20]
    records = {"positives": parents, "negatives": negatives, "extraction_candidates": inputs["candidates"],
               "quarantined": inputs["failures"], "raw": inputs["raws"]}
    for name, rows in records.items():
        _write_records(store, folder + "/" + name + ".jsonl", rows)
    for record in parents + negatives:
        relative = folder + "/xdl/" + record["id"] + ".xdl"
        payload = record["xdl"].encode("utf-8")
        path = store.root / relative
        if path.exists() and path.read_bytes() != payload:
            raise ValueError("Migration replay changed frozen XML")
        atomic_bytes(path, payload)
        store.track_file("xdl/" + record["id"], relative)
    mappings = load_library("operation_mappings.yaml")
    report = {"schema": "mosaic.canonical-migration/1", "source_run_id": inputs["result"]["run_id"],
              "parents_normalized_first": len(parents), "negative_interventions_replayed": len(negatives),
              "risk_violations_and_unknowns_unchanged": True, "no_llm_calls": True,
              "canonical_operations": len(registry["canonical_operations"]),
              "legacy_names": len(mappings.get("migrations", [])),
              "canonical_usage": dict(Counter(step["op"] for p in parents for step in p["steps"])),
              "classifications": dict(Counter(step["normalization"].get("classification") for p in parents for step in p["steps"]))}
    evolution = copy.deepcopy(inputs["evolution"])
    evolution.update(before_revision=digest(inputs["registry"]), after_revision=digest(registry),
                     canonical_migration=report,
                     historical_curator=copy.deepcopy(evolution["curator"]),
                     curator={"role": "library_curator", "status": "not_called_during_deterministic_migration"})
    products = {"atomic_operations": atomic_inventory(parents, [], registry),
                "equipment_inventory": equipment_inventory(parents, registry), "library_registry": registry,
                "library_evolution": evolution, "normalization_report": report,
                "operation_migrations": mappings}
    for name, value in products.items():
        relative = folder + "/" + name + ".json"
        path = store.root / relative
        if path.exists() and read_json(path) != value:
            raise ValueError("Migration replay changed frozen inventory")
        atomic_json(path, value)
        store.track_file("library/" + name, relative)
    result = {**inputs["result"], "run_id": run_id, "run_dir": str(store.root),
              "model_calls": 0, "new_model_calls": 0, "replayed_stages": {}, "naming_standard": "mosaic-canonical/1",
              "registry_revision": digest(registry),
              "migration": report, "library_registry": folder + "/library_registry.json",
              "library_evolution": folder + "/library_evolution.json",
              "review_bundle": {"positives": folder + "/positives.jsonl", "negatives": folder + "/negatives.jsonl",
                                "candidates": folder + "/extraction_candidates.jsonl"}}
    if _code_revision(domain) != revision:
        raise ValueError("Program changed while migrating")
    store.finish("partial" if result["positive_shortfall"] or result["risk_shortfalls"] else "complete", result)
    store.verify()
    atomic_json(store.root.parent / "current.json", {"run_id": run_id, "manifest": run_id + "/manifest.json"})
    return result
