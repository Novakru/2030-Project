"""Conservative library evolution and exact coverage of witnessed requirements."""
from __future__ import annotations

import copy
from collections import defaultdict

from protocol_risk.io import digest, load_library
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
    """A run pins a snapshot; proposals do not silently modify the domain vocabulary."""
    def __init__(self, snapshot=None):
        self.snapshot = copy.deepcopy(snapshot) if snapshot is not None else {
            "schema": "mosaic.registry/1", "devices": load_library("hardware.yaml")["devices"],
            "operations": load_library("primitives.yaml")["operations"],
            "macros": load_library("macros.yaml")["macros"], "risks": load_library("risks.yaml")["risks"],
            "observations": [], "operation_candidates": [], "aliases": {}, "changes": []}
        self.snapshot = copy.deepcopy(self.snapshot)

    @property
    def revision(self):
        return digest(self.snapshot)

    def evolve(self, changes, *, expected_revision, sources):
        if expected_revision != self.revision:
            raise ValueError("Registry revision conflict")
        next_snapshot = copy.deepcopy(self.snapshot)
        for change in changes:
            evidence = change.get("evidence", [])
            if not evidence:
                raise ValueError("Library changes require source evidence")
            for citation in evidence:
                validate_span(citation, sources)
            action = change.get("action")
            if action == "observe_device":
                observation = copy.deepcopy(change["device"])
                if observation.get("verified") is True:
                    raise ValueError("An automatic observation cannot declare human verification")
                observation.update(evidence=evidence, status="source_reported", verified=False)
                observation["observation_id"] = "obs_" + digest(observation)[:20]
                if not any(o["observation_id"] == observation["observation_id"] for o in next_snapshot["observations"]):
                    next_snapshot["observations"].append(observation)
            elif action == "propose_operation":
                if not change.get("counterexample"):
                    raise ValueError("New operation proposals need an existing-representation counterexample")
                proposal = {"name": change["name"], "evidence": evidence, "counterexample": change["counterexample"],
                            "status": "candidate_not_executable", "automatic_core_admission": False}
                if proposal not in next_snapshot["operation_candidates"]:
                    next_snapshot["operation_candidates"].append(proposal)
            elif action == "alias_identical_operation":
                left, right = change["from"], change["to"]
                operations = next_snapshot["operations"]
                if left == right or left not in operations or right not in operations or operations[left] != operations[right]:
                    raise ValueError("Automatic operation alias requires an identical full contract")
                cursor, visited = right, {left}
                while cursor in next_snapshot["aliases"]:
                    if cursor in visited:
                        raise ValueError("Operation aliases cannot form a cycle")
                    visited.add(cursor)
                    cursor = next_snapshot["aliases"][cursor]
                if cursor in visited:
                    raise ValueError("Operation aliases cannot form a cycle")
                next_snapshot["aliases"][left] = right
            else:
                raise ValueError("Unsupported registry action")
            receipt = {"action": action, "change_sha256": digest(change), "evidence": evidence}
            if receipt not in next_snapshot["changes"]:
                next_snapshot["changes"].append(receipt)
        return Registry(next_snapshot)

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
