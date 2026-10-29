"""Normalize source expressions and export a self-contained XDL representation."""

from mosaic.protocol.normalization import normalize_protocol, validate_normalized
from mosaic.protocol.io import load_library
from mosaic.protocol.xdl import canonical_hash, export_xdl, validate_xdl


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
