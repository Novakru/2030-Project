"""Normalize source expressions and export conventional XDL with JSON sidecars."""

from mosaic.protocol.normalization import normalize_protocol, validate_normalized
from mosaic.protocol.io import load_library
from mosaic.protocol.xdl import canonical_hash
from mosaic.protocol.xdl_document import PROFILE, compile_document


def registry_vocabulary(registry):
    snapshot = (registry.snapshot if hasattr(registry, "snapshot") else registry) or {}
    return {"operations": snapshot.get("canonical_operations") or load_library("atomic_operations.yaml")["operations"],
            "mappings": snapshot.get("operation_mappings") or load_library("operation_mappings.yaml"),
            "equipment": snapshot.get("equipment_catalog") or load_library("equipment.yaml"),
            "equipment_mappings": snapshot.get("equipment_mappings") or load_library("equipment_mappings.yaml")}


def finalize_protocol(protocol, *, vocabulary=None):
    result = normalize_protocol(protocol, vocabulary=vocabulary)
    if vocabulary and "hardware" in result:
        from .protocol.equipment_normalization import normalize_equipment
        result["hardware"] = normalize_equipment(result["hardware"], catalog=vocabulary.get("equipment"),
                                                  mappings=vocabulary.get("equipment_mappings"))
    validate_normalized(result)
    if result.get("normalization", {}).get("unresolved"):
        raise ValueError("Unresolved canonical concepts require library evolution")
    result["xdl_profile"] = PROFILE
    document = compile_document(result)
    result["xdl"] = document["xml"]
    result["xdl_extensions"] = document["extensions"]
    result["xdl_bindings"] = document["bindings"]
    result["canonical_sha1"] = canonical_hash(result)
    result.setdefault("quality", {}).update(naming_standard="mosaic-canonical/1",
        xdl_profile=PROFILE, xdl_profile_schema_passed=True, canonical_names_checked=True)
    return result
