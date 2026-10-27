"""Independently replay a frozen review bundle against its source and contracts."""
from __future__ import annotations

import copy
from collections import Counter
from pathlib import Path

import jsonpatch

from protocol_risk.apparatus import source_fact_hash
from protocol_risk.crosscheck import crosscheck
from protocol_risk.ingest import iter_ord
from protocol_risk.io import ROOT, digest, read_json, read_jsonl
from protocol_risk.mutation_rules import SOFT, negative_fingerprint
from protocol_risk.native import material_contracts, missing_input, remove_statement
from protocol_risk.symbolic import evaluate
from protocol_risk.xdl import canonical_hash, export_xdl, validate_xdl
from protocol_risk.yields import target_yield

from .mutations import assess_intervention, fault_instances
from .store import RunStore
from .sources import text_document


def verify_dataset(run_dir, *, upstream=True):
    root = Path(run_dir).resolve()
    manifest = read_json(root / "manifest.json")
    RunStore(root, manifest["request"]).verify()
    bundle = manifest["result"]["review_bundle"]
    parents = {p["id"]: p for p in read_jsonl(root / bundle["positives"])}
    negatives = list(read_jsonl(root / bundle["negatives"]))
    raws = {r["id"]: r for r in read_jsonl(root / Path(bundle["positives"]).parent / "raw.jsonl")}
    issues, fingerprints, groups = [], set(), {}
    upstream_hashes = {}
    ord_ids = {r["id"] for r in raws.values() if r.get("source", {}).get("db") == "ORD"}
    if upstream and ord_ids:
        for source in read_json(ROOT / "data/sources.lock.json")["files"]:
            if digest((ROOT / source["path"]).read_bytes()) != source["sha256"]:
                raise ValueError("Upstream ORD file checksum changed")
            for raw, _ in iter_ord(ROOT / source["path"], ids=ord_ids):
                if raw.get("reaction_id") in raws:
                    upstream_hashes[raw["reaction_id"]] = digest(raw)
    for parent in parents.values():
        try:
            if groups.setdefault(parent["split_group"], parent["split"]) != parent["split"]:
                raise ValueError("One source/scaffold group crossed dataset splits")
            if parent.get("format") == "native_author_xdl":
                if digest(parent["xdl"].encode("utf-8")) != parent["raw_sha256"]:
                    raise ValueError("Native parent differs from source XML")
                continue
            if evaluate(parent).risks or export_xdl(parent) != parent["xdl"]:
                raise ValueError("Positive rules or XDL mismatch")
            validate_xdl(parent["xdl"])
            if parent["source"]["db"] not in ("ORD", "TEXT"):
                continue
            raw = raws[parent["raw_id"]]
            if digest(raw["raw"]) != parent["raw_sha256"] or upstream and raw["id"] in ord_ids and upstream_hashes.get(raw["id"]) != parent["raw_sha256"]:
                raise ValueError("Raw source snapshot or upstream hash mismatch")
            document = text_document(raw)
            if parent.get("xdl_profile") == "mosaic-xdl/1":
                from protocol_risk.extensions import read_extended_xdl, validate_extension_step
                from protocol_risk.missing import annotate_missing
                decoded = read_extended_xdl(parent["xdl"])
                if decoded["steps"] != parent["steps"] or decoded["operation_definitions"] != parent.get("operation_definitions", {}):
                    raise ValueError("Extended XDL roundtrip lost operation or parameter data")
                checked = annotate_missing(copy.deepcopy(parent))
                if checked["steps"] != parent["steps"]:
                    raise ValueError("Source-missing parameter annotations are stale")
                for step in parent["steps"]:
                    if step["op"] in parent.get("operation_definitions", {}):
                        validate_extension_step(step, parent["operation_definitions"][step["op"]], source=document["procedure"])
            if (parent.get("source_text") != document["procedure"] or parent.get("text_sha256") != document["text_sha256"]
                    or parent.get("extraction", {}).get("input_contract") != "text-only/1"):
                raise ValueError("Text-only input contract or verbatim source snapshot mismatch")
            if any(s.get("meta", {}).get("amount_source") != "procedure_text"
                   for s in parent["steps"] if s["op"] == "Add" and s.get("amount")):
                raise ValueError("Addition amount was not obtained from source text")
            if "source_setup" in parent.get("context", {}):
                raise ValueError("Structured apparatus leaked into operational context")
            if raw["id"] in ord_ids:
                observed, evidence = target_yield(raw["raw"])
                reference = parent.get("reference_metadata", {})
                if observed != reference.get("yield_percent") or evidence != reference.get("yield_evidence"):
                    raise ValueError("Independent reference yield evidence changed")
            if crosscheck(parent, raw) != parent["crosscheck"] or canonical_hash(parent) != parent["canonical_sha1"]:
                raise ValueError("Crosscheck or canonical export is stale")
            for node in parent["hardware"]["nodes"].values():
                if node.get("binding_basis") == "source_reported":
                    if node.get("verified") or source_fact_hash(node) != node["source_fact_sha256"]:
                        raise ValueError("Source apparatus fact mismatch")
                    for citation in node.get("source_evidence", []):
                        if citation["raw_sha256"] != raw["raw_sha256"]:
                            raise ValueError("Apparatus citation source mismatch")
                        if citation["locator"] == "/setup/vessel":
                            raise ValueError("Structured apparatus citation crossed text-only seam")
                        elif isinstance(citation["value"], str) and " ".join(citation["value"].split()).casefold() not in " ".join((raw.get("procedure") or "").split()).casefold():
                            raise ValueError("Apparatus quote missing from source")
        except (ValueError, KeyError, TypeError) as error:
            issues.append({"id": parent["id"], "reason": str(error)})
    for sample in negatives:
        try:
            parent = parents[sample["parent_id"]]
            child = jsonpatch.apply_patch(copy.deepcopy(parent), sample["diff"])
            if child != sample["protocol"] or child["xdl"] != sample["xdl"] or sample["split"] != parent["split"]:
                raise ValueError("Patch replay, export or split mismatch")
            risk = sample["label"]["risk_l2"]
            if sample.get("format") == "native_author_xdl":
                contract = sample["contract"]
                if contract not in material_contracts(parent["xdl"], parent["hardware"]):
                    raise ValueError("Native contract is not supported by source graph")
                if child["xdl"] != remove_statement(parent["xdl"], contract["producer_xpath"]) or not missing_input(child["xdl"], contract):
                    raise ValueError("Native single-statement omission did not replay")
                key = digest({"risk": risk, "xdl": sample["xdl"]})
            else:
                intervention = assess_intervention(parent, child)
                result = evaluate(child)
                if result.risks != ([] if risk in SOFT else [risk]):
                    raise ValueError("Wrong target risk")
                if risk not in SOFT and len(fault_instances(child, result.violations)) != 1:
                    raise ValueError("Multiple fault instances")
                if intervention != sample["mutation"]["intervention"] or export_xdl(child) != sample["xdl"]:
                    raise ValueError("Intervention or XDL mismatch")
                validate_xdl(sample["xdl"])
                key = negative_fingerprint(sample)
            if key in fingerprints:
                raise ValueError("Duplicate negative")
            fingerprints.add(key)
        except (ValueError, KeyError, TypeError, jsonpatch.JsonPatchException) as error:
            issues.append({"id": sample["id"], "reason": str(error)})
    counts = Counter(s["label"]["risk_l2"] for s in negatives)
    return {"passed": not issues, "positives_checked": len(parents), "negatives_checked": len(negatives),
            "upstream_ord_records_checked": len(upstream_hashes), "risk_counts": dict(sorted(counts.items())),
            "mechanisms": {r: dict(Counter(s["mutation"]["mechanism_id"] for s in negatives if s["label"]["risk_l2"] == r)) for r in sorted(counts)},
            "issues": issues, "scope": "Source integrity, rule checks and single-intervention replay; no experimental feasibility certificate."}
