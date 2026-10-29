"""Finalize canonical parents and rebuild children without repairing interventions."""
import copy

import jsonpatch

from protocol_risk.normalization import normalize_protocol, validate_normalized
from protocol_risk.io import load_library
from protocol_risk.xdl import canonical_hash, export_xdl, validate_xdl


def registry_vocabulary(registry):
    snapshot = (registry.snapshot if hasattr(registry, "snapshot") else registry) or {}
    return {"operations": snapshot.get("canonical_operations") or load_library("atomic_operations.yaml")["operations"],
            "mappings": snapshot.get("operation_mappings") or load_library("operation_mappings.yaml"),
            "equipment": snapshot.get("equipment_catalog") or load_library("equipment.yaml"),
            "equipment_mappings": snapshot.get("equipment_mappings") or load_library("equipment_mappings.yaml")}


def finalize_protocol(protocol, *, vocabulary=None):
    result = normalize_protocol(protocol, vocabulary=vocabulary)
    validate_normalized(result)
    if result.get("normalization", {}).get("unresolved"):
        raise ValueError("Unresolved canonical concepts require library evolution")
    result["xdl_profile"] = "mosaic-canonical/1"
    result.pop("xdl", None)
    result["xdl"] = export_xdl(result)
    validate_xdl(result["xdl"])
    result["canonical_sha1"] = canonical_hash(result)
    result.setdefault("quality", {}).update(naming_standard="mosaic-canonical/1",
        xdl_profile="mosaic-canonical/1", canonical_names_checked=True)
    return result


def finalize_negative(sample, parent, *, vocabulary=None):
    result = copy.deepcopy(sample)
    vocabulary = copy.deepcopy(vocabulary or {})
    operations = vocabulary.get("operations") or copy.deepcopy(load_library("atomic_operations.yaml")["operations"])
    operations.update({contract["id"]: contract for contract in parent.get("operation_definitions", {}).values()})
    mappings = vocabulary.get("mappings") or copy.deepcopy(load_library("operation_mappings.yaml"))
    for rule in parent.get("normalization", {}).get("mapping_rules", {}).values():
        if rule.get("contract_hash"):
            if rule["contract_hash"] not in mappings["contracts"]:
                mappings["contracts"][rule["contract_hash"]] = rule["mapping"]
        else:
            if not any(item["id"] == rule["mapping"]["id"] for item in mappings["aliases"]):
                mappings["aliases"].append({**rule["mapping"], "expressions": [rule["expression"]]})
    vocabulary.update(operations=operations, mappings=mappings)
    result["protocol"] = finalize_protocol(sample["protocol"], vocabulary=vocabulary)
    result["xdl"] = result["protocol"]["xdl"]
    result["diff"] = jsonpatch.make_patch(parent, result["protocol"]).patch
    if jsonpatch.apply_patch(copy.deepcopy(parent), result["diff"]) != result["protocol"]:
        raise ValueError("Canonical intervention did not replay")
    return result
