"""Conservative library evolution and exact coverage of witnessed requirements."""
from __future__ import annotations

import copy
from collections import defaultdict

from mosaic.protocol.io import digest, load_library
from .evidence import validate_span


def minimum_cover(requirements, witnesses):
    """Minimize device types for an explicit evidence matrix, not physical instances.

    The domain verifier supplies witnesses. Unknown claims never provide coverage.
    This solver makes no simultaneous scheduling or apparatus-graph guarantee.
    """
    required = set(requirements)
    coverage = defaultdict(set)
    for witness in witnesses:
        if witness.get("requirement") not in required:
            raise ValueError("Witness refers to an undeclared requirement")
        if witness.get("known") is True and witness.get("evidence_ids") and witness.get("device"):
            coverage[witness["device"]].add(witness["requirement"])
    available = set().union(*coverage.values()) if coverage else set()
    missing = sorted(required - available)
    if missing:
        return {"status": "incomplete", "devices": [], "uncovered": missing, "optimal": False}
    if not required:
        return {"status": "covered", "devices": [], "uncovered": [], "optimal": True}
    # Bitset-free branch-and-bound stays small for this project's ~20 device types.
    names = sorted(coverage)
    best = names[:]
    by_requirement = {r: [n for n in names if r in coverage[n]] for r in required}

    def search(remaining, chosen):
        nonlocal best
        if not remaining:
            if len(chosen) < len(best) or len(chosen) == len(best) and sorted(chosen) < best:
                best = sorted(chosen)
            return
        if len(chosen) >= len(best):
            return
        target = min(remaining, key=lambda r: (len(by_requirement[r]), r))
        for name in by_requirement[target]:
            if name not in chosen:
                search(remaining - coverage[name], chosen + [name])

    search(required, [])
    return {"status": "covered", "devices": best, "uncovered": [], "optimal": True,
            "scope": "Minimum types for supplied validated witnesses; not minimum concurrent instances or universal hardware sufficiency."}


class Registry:
    """Evidence-checked transactions over four public semantic catalogs."""
    def __init__(self, snapshot=None):
        self.snapshot = copy.deepcopy(snapshot) if snapshot is not None else {
            "schema": "mosaic.registry/2", "devices": load_library("hardware.yaml")["devices"],
            "canonical_operations": load_library("atomic_operations.yaml")["operations"],
            "operation_mappings": load_library("operation_mappings.yaml"),
            "equipment_catalog": load_library("equipment.yaml"),
            "equipment_mappings": load_library("equipment_mappings.yaml"),
            "observations": [], "changes": []}

    @property
    def revision(self):
        return digest(self.snapshot)

    def evolve(self, changes, *, expected_revision, sources):
        if expected_revision != self.revision:
            raise ValueError("Registry revision conflict")
        snapshot = copy.deepcopy(self.snapshot)
        for change in changes:
            evidence = change.get("evidence", [])
            if not evidence:
                raise ValueError("Library changes require source evidence")
            for citation in evidence:
                validate_span(citation, sources)
            action = change.get("action")
            if action == "admit_fact_expression":
                from .fact_evolution import admit_expression
                admit_expression(snapshot, change)
            elif action in {"admit_equipment_subtype", "map_equipment_alias", "admit_equipment_substitution"}:
                from .equipment_evolution import evolve_equipment
                evolve_equipment(snapshot, change)
            elif action == "observe_device":
                observation = copy.deepcopy(change["device"])
                if observation.get("verified"):
                    raise ValueError("An automatic observation cannot declare human verification")
                observation.update(evidence=evidence, status="source_reported", verified=False)
                observation["observation_id"] = "obs_" + digest(observation)[:20]
                if observation not in snapshot["observations"]:
                    snapshot["observations"].append(observation)
            else:
                raise ValueError("Unsupported registry action")
            receipt = {"action": action, "change_sha256": digest(change), "evidence": evidence}
            if receipt not in snapshot["changes"]:
                snapshot["changes"].append(receipt)
        return Registry(snapshot)

    def compact_device_observations(self):
        """Merge evidence only for exact identified models and identical declared facts."""
        groups, anonymous = {}, []
        for observation in self.snapshot["observations"]:
            identity = observation.get("identity", {})
            if not identity.get("manufacturer") or not identity.get("model"):
                anonymous.append(copy.deepcopy(observation))
                continue
            key = digest({"identity": identity, "params": observation.get("params"),
                          "parameter_scope": observation.get("parameter_scope"),
                          "wetted_materials": observation.get("wetted_materials")})
            if key not in groups:
                groups[key] = {"profile": copy.deepcopy(observation), "observation_ids": [], "evidence": []}
            group = groups[key]
            group["observation_ids"].append(observation["observation_id"])
            for item in observation["evidence"]:
                if item not in group["evidence"]:
                    group["evidence"].append(item)
        return {"identified_models": list(groups.values()), "unidentified_observations": anonymous,
                "policy": "Unknown model identities remain separate. Different parameter scopes or values never merge automatically."}
