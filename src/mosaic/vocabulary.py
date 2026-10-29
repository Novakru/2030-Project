"""Representation-only canonical evolution; mappings never version a concept."""
import copy
import re

from mosaic.protocol.io import digest
from mosaic.protocol.normalization import analysis_protocol, normalize_protocol, semantic_contract_hash


def evolve_canonical(snapshot, change):
    """Apply an evidence-checked registry change to a private next snapshot."""
    operations = snapshot.setdefault("canonical_operations", {})
    action = change["action"]
    if action == "admit_canonical_operation":
        identifier, contract = change.get("operation_id"), copy.deepcopy(change.get("contract"))
        if not isinstance(identifier, str) or not re.fullmatch(r"[a-z][a-z0-9_.-]+", identifier):
            raise ValueError("Canonical operations need a stable identifier")
        if not isinstance(contract, dict) or not re.fullmatch(r"[A-Z][A-Za-z0-9]+", contract.get("name", "")):
            raise ValueError("Canonical operations need a professional canonical name")
        if not change.get("counterexample") or not change.get("considered_operations"):
            raise ValueError("New semantics require a counterexample and comparison with existing concepts")
        if any(item not in operations for item in change["considered_operations"]):
            raise ValueError("Comparison cites an unknown canonical concept")
        if identifier in operations or any(item["name"] == contract["name"] for item in operations.values()):
            raise ValueError("Reuse the existing canonical ID; do not create a name variant")
        if not isinstance(contract.get("parameters"), dict) or any(
                not isinstance(contract.get(key), list) or not contract[key]
                for key in ("preconditions", "effects")) or not isinstance(contract.get("capabilities"), list):
            raise ValueError("New semantics require parameters, preconditions, effects and capability requirements")
        if contract.get("execution_supported"):
            raise ValueError("A declarative concept cannot install an instrument executor")
        contract.update(id=identifier, representation_status="admitted", execution_supported=False)
        contract["semantic_sha256"] = semantic_contract_hash(contract)
        operations[identifier] = contract
    mapping = copy.deepcopy(change.get("mapping"))
    if not isinstance(mapping, dict) or not mapping.get("id") or not mapping.get("expressions"):
        raise ValueError("Canonical changes need an explicit expression mapping")
    if any(not isinstance(word, str) or not word.strip() for word in mapping["expressions"]):
        raise ValueError("Mapping expressions must be nonempty text")
    if mapping.get("operation_id") not in operations:
        raise ValueError("Mapping target is not a canonical operation")
    mappings = snapshot.setdefault("operation_mappings", {"aliases": [], "migrations": {}, "contracts": {}})
    known = next((item for item in mappings["aliases"] if item["id"] == mapping["id"]), None)
    if known and known != mapping:
        raise ValueError("An existing mapping ID cannot be silently overwritten")
    if not known:
        mappings["aliases"].append(mapping)
    # Witnesses exercise the same deterministic module used by extraction.
    # This certifies representation roundtrip only; scientific semantics remain
    # silver and visible to human review.
    witnesses = change.get("witnesses")
    if not isinstance(witnesses, list) or not witnesses:
        raise ValueError("Canonical admission requires current-value roundtrip witnesses")
    vocabulary = {"operations": operations, "mappings": mappings}
    for witness in witnesses:
        expressions = {str(word).strip().casefold() for word in mapping["expressions"]}
        if witness.get("normalization") or not any(str(step.get("op")).strip().casefold() in expressions for step in witness.get("steps", [])):
            raise ValueError("Witness must exercise the proposed expression mapping")
        normalized = normalize_protocol(witness, vocabulary=vocabulary)
        if normalized["normalization"]["unresolved"] or analysis_protocol(normalized) != witness:
            raise ValueError("Canonical mapping witness is unresolved or loses source data")
    snapshot["canonical_mapping_revision"] = digest(mappings)
