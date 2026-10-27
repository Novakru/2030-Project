"""Conservative library evolution and exact coverage of witnessed requirements."""
from __future__ import annotations

import copy
from collections import defaultdict

from protocol_risk.io import ROOT, digest, load_library
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
        family_path = ROOT / "libraries/equipment_families.yaml"
        families = load_library("equipment_families.yaml").get("families", {}) if snapshot is None and family_path.exists() else {}
        self.snapshot = copy.deepcopy(snapshot) if snapshot is not None else {
            "schema": "mosaic.registry/1", "devices": load_library("hardware.yaml")["devices"],
            "operations": load_library("primitives.yaml")["operations"],
            "macros": load_library("macros.yaml")["macros"], "risks": load_library("risks.yaml")["risks"],
            "observations": [], "operation_candidates": [], "aliases": {}, "changes": [],
            "families": families}
        self.snapshot = copy.deepcopy(self.snapshot)
        # Older frozen runs remain readable. These are separate from the
        # executable operation contracts and manufacturer/model profiles.
        for key, default in (("operation_candidates", []), ("representation_candidates", []),
                             ("representations", {}), ("families", {}),
                             ("family_candidates", []), ("operation_observations", [])):
            self.snapshot.setdefault(key, default)

    @property
    def revision(self):
        return digest(self.snapshot)

    def evolve(self, changes, *, expected_revision, sources, policy=None):
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
            elif action == "observe_operation":
                observation = copy.deepcopy(change["observation"])
                if observation.get("verified") or observation.get("executable"):
                    raise ValueError("Operation observations cannot declare verified execution")
                observation.update(evidence=evidence, status="source_reported")
                observation.setdefault("observation_id", "op_observation_" + digest(observation)[:20])
                self._merge_candidate(next_snapshot["operation_observations"], observation, "observation_id")
            elif action == "cluster_operation":
                proposal = copy.deepcopy(change["proposal"])
                if not proposal.get("name") or not proposal.get("domain") or not proposal.get("origins"):
                    raise ValueError("Operation clusters need a domain, semantic name and origins")
                if proposal.get("verified") or proposal.get("executable"):
                    raise ValueError("A semantic cluster cannot declare verified execution")
                identity = {k: proposal.get(k) for k in ("domain", "name", "contract")}
                identity["name"] = " ".join(str(identity["name"]).split()).casefold()
                proposal.update(candidate_id="op_candidate_" + digest(identity)[:20],
                                evidence=evidence, status="candidate_not_executable",
                                automatic_core_admission=False)
                self._merge_candidate(next_snapshot["operation_candidates"], proposal, "candidate_id")
            elif action in ("propose_macro", "admit_macro"):
                proposal = copy.deepcopy(change["proposal"])
                proposal["candidate_id"] = "representation_" + digest({
                    k: proposal.get(k) for k in ("domain", "name", "contract", "expansion", "parameter_mapping")})[:20]
                proposal.update(evidence=evidence, status="candidate_not_executable")
                if action == "admit_macro":
                    if policy is None:
                        raise ValueError("Macro admission requires a domain representation verifier")
                    certificate = policy.verify_macro(proposal, next_snapshot)
                    if not isinstance(certificate, dict) or certificate.get("lossless") is not True:
                        raise ValueError("Macro representation has no lossless domain certificate")
                    proposal.update(status="admitted_representation", certificate=certificate)
                    next_snapshot["representations"][proposal["candidate_id"]] = proposal
                else:
                    self._merge_candidate(next_snapshot["representation_candidates"], proposal, "candidate_id")
            elif action in ("cluster_device_family", "propose_device_family"):
                family = copy.deepcopy(change["family"])
                if not family.get("id") or not family.get("origins"):
                    raise ValueError("Device families need an identifier and observation origins")
                if any(key in family for key in ("params", "verified", "manufacturer", "model")):
                    raise ValueError("Device clustering cannot manufacture model facts")
                family.update(evidence=evidence, status="classification_only",
                              substitution_requires="operation_requirements_and_known_profile_facts")
                if action == "cluster_device_family":
                    known = next_snapshot["families"].get(family["id"])
                    if known is None:
                        raise ValueError("Automatic classification requires a declared equipment family")
                    for key in ("origins", "evidence"):
                        known.setdefault(key, [])
                        for item in family[key]:
                            if item not in known[key]:
                                known[key].append(item)
                else:
                    self._merge_candidate(next_snapshot["family_candidates"], family, "id")
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

    @staticmethod
    def _merge_candidate(candidates, proposal, identifier):
        """Aggregate equal semantic proposals without erasing original evidence."""
        previous = next((item for item in candidates if item.get(identifier) == proposal[identifier]), None)
        if previous is None:
            candidates.append(proposal)
            return
        for key in ("origins", "evidence", "counterexamples"):
            if key not in proposal:
                continue
            previous.setdefault(key, [])
            for item in proposal.get(key, []):
                if item not in previous[key]:
                    previous[key].append(item)

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
