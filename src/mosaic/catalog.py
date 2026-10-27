"""Evidence inventory for conservative atomic-operation reduction."""
from collections import Counter
from protocol_risk.io import load_library
from protocol_risk.symbolic import _known
from .registry import minimum_cover


def equipment_inventory(parents):
    """Ask for types that cover the batch's stated demands using cited facts only."""
    requirements, witnesses, profiles = set(), [], {}
    for parent in parents:
        nodes = parent.get("hardware", {}).get("nodes", {})
        if not isinstance(nodes, dict):
            continue
        for step in parent.get("steps", []):
            role = "heater" if step["op"] in ("HeatChill", "Stir") else None
            node_id = parent["hardware"].get("bindings", {}).get(role) if role else step.get("vessel", "reactor")
            node = nodes.get(node_id, {})
            demand = "operation:" + step["op"] + ":" + str(role or "vessel")
            requirements.add(demand)
            citations = node.get("source_evidence", [])
            evidence = [str(c.get("raw_sha256")) + ":" + str(c.get("locator")) for c in citations]
            profile = node.get("model") or node.get("apparatus_kind") or node.get("category", "unknown")
            profiles[profile] = {"category": node.get("category"), "apparatus_kind": node.get("apparatus_kind")}
            # Presence of a named vessel does not establish a controller's operating range.
            known = bool(evidence and node.get("binding_basis") == "source_reported" and not role)
            witnesses.append({"requirement": demand, "device": profile, "known": known, "evidence_ids": evidence})
            if role and step.get("controller_setpoint_C") is not None:
                low, high = _known(node, "T_min_C"), _known(node, "T_max_C")
                value = step["controller_setpoint_C"]
                witnesses[-1]["known"] = bool(evidence and low is not None and high is not None and low <= value <= high)
    cover = minimum_cover(sorted(requirements), witnesses)
    return {"cover": cover, "requirements": sorted(requirements), "profiles": profiles,
            "unknown_witnesses": sum(not w["known"] for w in witnesses),
            "policy": "Conservative type cover for stated batch demands only. Unknown controller ranges cannot cover heating; no physical instance or universal minimum claim."}

def atomic_inventory(positives, snapshots):
    library = load_library("primitives.yaml")
    definitions = library["operations"]
    used = Counter(s["op"] for p in positives for s in p["steps"])
    extracted = Counter(s["op"] for p in snapshots for s in p.get("steps", []))
    context_only = Counter(s["op"] for p in positives for s in p["steps"]
                           if s["op"] == "Atmosphere" and s.get("mode") in ("environment", "balloon"))
    unmapped = [{"id": p["id"], "actions": p.get("extraction", {}).get("unmapped_actions", [])}
               for p in snapshots if p.get("extraction", {}).get("unmapped_actions")]
    fields = {op: set(spec["required"] + spec["optional"]) for op, spec in definitions.items()}
    operations = {}
    for op, spec in definitions.items():
        elsewhere = set().union(*(v for k, v in fields.items() if k != op))
        operations[op] = {"selected_steps": used[op], "context_only_steps": context_only[op],
            "snapshot_steps": extracted[op], "required": spec["required"], "optional": spec["optional"],
            "fields_unique_in_current_registry": sorted(fields[op] - elsewhere), "risk_checks": spec["risks"],
            "state_distinction": spec["reason"], "export_mapping": spec["xdl_steps"],
            "reduction_status": "retain_pending_lossless_proof" if used[op] else "defer_removal_broader_source_coverage_needed"}
    all_fields = set().union(*fields.values())
    aliases = {"solvent": "reagent", "wash_reagent": "reagent", "quench_reagent": "reagent",
               "drying_agent": "reagent", "temperatures": "temp_C"}
    macros = {}
    for name, spec in load_library("macros.yaml")["macros"].items():
        missing = [key for key in spec.get("requires", []) if aliases.get(key, key) not in all_fields]
        macros[name] = {"expansion": spec["expansion"], "requires": spec.get("requires", []),
                       "parameters_without_primitive_field": missing, "status": "draft_not_proven_lossless",
                       "gate": "Preserve source parameters, state effects, endpoints and apparatus context; replay risk checks before admission."}
    return {"library_version": library["version"], "candidate_operations": len(definitions),
            "selected_operations_used": sum(bool(used[op]) for op in definitions),
            "selected_steps": sum(used.values()), "extraction_snapshots": len(snapshots),
            "operations": operations, "macro_candidates": macros,
            "unmapped_snapshot_records": len(unmapped), "unmapped_snapshot_actions": sum(len(r["actions"]) for r in unmapped),
            "unmapped_examples": unmapped[:5], "source_action_coverage": None,
            "source_action_coverage_status": "unproven: no independently annotated complete source-action denominator",
            "minimality_proven": False,
            "policy": "No new primitives or automatic removals. Shared fields alone do not prove equivalent state effects; selected IR coverage does not establish 98% source-action coverage."}
