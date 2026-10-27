"""Versioned operation inventory and conditional apparatus candidate groups."""
from collections import Counter
from protocol_risk.io import digest, load_library
from .equipment import check_substitution, classify_equipment, equipment_groups
from .registry import minimum_cover


def _snapshot(registry):
    if registry is not None:
        return registry.snapshot if hasattr(registry, "snapshot") else registry
    return {"schema": "mosaic.catalog-default/1", "devices": load_library("hardware.yaml")["devices"],
            "families": load_library("equipment_families.yaml")["families"],
            "operations": load_library("primitives.yaml")["operations"],
            "macros": load_library("macros.yaml")["macros"], "observations": []}


def equipment_inventory(parents, registry=None):
    """Describe families separately from profiles and evidence-scoped substitutions."""
    snapshot = _snapshot(registry)
    families = snapshot.get("families", load_library("equipment_families.yaml")["families"])
    observations = list(snapshot.get("observations", []))
    bindings, demands = [], {}
    operation_roles = {"HeatChill": "heater", "Stir": "heater", "Filter": "filter",
                       "Separate": "separator", "Evaporate": "rotavap", "Irradiate": "light"}
    capabilities = {"HeatChill": "heat", "Stir": "stir", "Filter": "solid_liquid_separation",
                    "Separate": "liquid_phase_separation", "Evaporate": "evaporate", "Irradiate": "irradiate"}
    for parent in parents:
        nodes = parent.get("hardware", {}).get("nodes", {})
        if not isinstance(nodes, dict):
            continue
        for node_id, node in nodes.items():
            bindings.append({"record_id": parent.get("id"), "node_id": node_id,
                "catalog_id": node.get("id"), "apparatus_kind": node.get("apparatus_kind"),
                "family": classify_equipment(node, families=families), "binding_basis": node.get("binding_basis")})
            if node.get("binding_basis") == "source_reported":
                observation = {**node, "observation_id": "obs_" + digest(node)[:20]}
                if not any(item.get("observation_id") == observation["observation_id"] for item in observations):
                    observations.append(observation)
        for step in parent.get("steps", []):
            role = operation_roles.get(step["op"])
            node_id = parent["hardware"].get("bindings", {}).get(role, role) if role else step.get("vessel", "reactor")
            node = nodes.get(node_id, {})
            requirement = {"capabilities": [capabilities.get(step["op"], "contain_material")]}
            family = classify_equipment(node, families=families)
            if family:
                requirement["family"] = family
            if step["op"] == "HeatChill" and step.get("temp_C") is not None:
                requirement.update(temperature_C=step["temp_C"], temperature_scope="sample_temperature")
            if step.get("rpm") is not None:
                requirement["rpm"] = step["rpm"]
            key = "demand_" + digest(requirement)[:16]
            demand = demands.setdefault(key, {"id": key, "requirement": requirement, "uses": []})
            demand["uses"].append({"record_id": parent.get("id"), "step_id": step.get("id", step.get("step_id")),
                                   "node_id": node_id, "operation": step["op"]})
    groups = equipment_groups(snapshot.get("devices", []), observations, families=families)
    witnesses, comparisons = [], []
    for key, demand in demands.items():
        requirement = demand["requirement"]
        candidates = [entry for entry in groups["catalog_profiles"]
                      if requirement.get("family") is None or entry.get("family") == requirement["family"]]
        for entry in candidates:
            result = check_substitution(requirement, entry, families=families)
            comparisons.append({"demand_id": key, "catalog_id": entry["catalog_id"], **result})
            witnesses.append({"requirement": key, "device": entry["catalog_id"],
                "known": result["status"] == "compatible", "evidence_ids": [str(entry.get("source_url"))]
                if entry.get("source_url") else []})
    return {"registry_revision": digest(snapshot), "groups": groups, "record_bindings": bindings,
            "cover": minimum_cover(sorted(demands), witnesses), "requirements": list(demands.values()),
            "substitutions": comparisons, "unknown_witnesses": sum(not witness["known"] for witness in witnesses),
            "policy": "Families retrieve candidates only. Cover is conditional on explicit cited demands and individual constraints; no universal substitution or minimum concurrent-instance claim."}


def atomic_inventory(positives, snapshots, registry=None):
    library = _snapshot(registry)
    definitions = library["operations"]
    used = Counter(s["op"] for p in positives for s in p["steps"])
    extracted = Counter(s["op"] for p in snapshots for s in p.get("steps", []))
    context_only = Counter(s["op"] for p in positives for s in p["steps"]
                           if s["op"] == "Atmosphere" and s.get("mode") in ("environment", "balloon"))
    unmapped = [{"id": p["id"], "actions": p.get("extraction", {}).get("unmapped_actions", [])}
               for p in snapshots if p.get("extraction", {}).get("unmapped_actions")]
    fields = {op: set(spec.get("required", []) + spec.get("optional", [])) for op, spec in definitions.items()}
    operations = {}
    for op, spec in definitions.items():
        elsewhere = set().union(*(v for k, v in fields.items() if k != op))
        operations[op] = {"selected_steps": used[op], "context_only_steps": context_only[op],
            "snapshot_steps": extracted[op], "required": spec.get("required", []), "optional": spec.get("optional", []),
            "fields_unique_in_current_registry": sorted(fields[op] - elsewhere), "risk_checks": spec.get("risks", []),
            "state_distinction": spec.get("reason"), "export_mapping": spec.get("xdl_steps", []),
            "domain": spec.get("domain"), "status": spec.get("status"),
            "reduction_status": "retain_pending_lossless_proof" if used[op] else "defer_removal_broader_source_coverage_needed"}
    all_fields = set().union(*fields.values())
    aliases = {"solvent": "reagent", "wash_reagent": "reagent", "quench_reagent": "reagent",
               "drying_agent": "reagent", "temperatures": "temp_C"}
    macros = {}
    for name, spec in library.get("macros", {}).items():
        missing = [key for key in spec.get("requires", []) if aliases.get(key, key) not in all_fields]
        macros[name] = {"expansion": spec["expansion"], "requires": spec.get("requires", []),
                       "parameters_without_primitive_field": missing, "status": "draft_not_proven_lossless",
                       "gate": "Preserve source parameters, state effects, endpoints and apparatus context; replay risk checks before admission."}
    return {"library_version": library.get("version", library.get("schema")), "registry_revision": digest(library),
            "candidate_operations": len(definitions),
            "selected_operations_used": sum(bool(used[op]) for op in definitions),
            "selected_steps": sum(used.values()), "extraction_snapshots": len(snapshots),
            "operations": operations, "macro_candidates": macros, "library_changes": library.get("changes", []),
            "representations": library.get("representations", {}),
            "representation_candidates": library.get("representation_candidates", []),
            "unregistered_operations": {op: count for op, count in used.items() if op not in definitions},
            "unmapped_snapshot_records": len(unmapped), "unmapped_snapshot_actions": sum(len(r["actions"]) for r in unmapped),
            "unmapped_examples": unmapped[:5], "source_action_coverage": None,
            "source_action_coverage_status": "unproven: no independently annotated complete source-action denominator",
            "minimality_proven": False,
            "policy": "Inventory uses the pinned evolved registry. Additions/aliases/macros retain evidence and migration history. Shared fields do not prove equal state effects, and selected IR coverage does not prove complete source-action coverage or universal minimality."}
