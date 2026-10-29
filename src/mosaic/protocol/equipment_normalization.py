"""Canonical equipment names without editing physical facts or repairing faults.

The analysis projection restores naming only. It never restores a missing node,
binding, edge, number or rating from an earlier protocol snapshot.
"""
from __future__ import annotations

import copy
import re
import unicodedata

from .io import load_library

SCHEMA = "mosaic.equipment-normalization/1"
_NAMES = ("category", "apparatus_kind", "kind", "type", "family", "category_id", "subtype_id")
_IDENTITY = ("category", "apparatus_kind", "category_id", "subtype_id")


def _key(value):
    if not isinstance(value, str):
        return ""
    return re.sub(r"[\s_-]+", "", unicodedata.normalize("NFKC", value).casefold())


def _libraries(catalog, mappings=None):
    catalog = load_library("equipment.yaml") if catalog is None else catalog
    mappings = load_library("equipment_mappings.yaml") if mappings is None else mappings
    return catalog, mappings


def _lookup(value, entries, aliases):
    """An exact normalized spelling must identify exactly one concept."""
    key = _key(value)
    matches = {identifier for identifier, entry in entries.items()
               if key and key in {_key(identifier), _key(entry["name"]),
                                 *(_key(name) for name in aliases.get(identifier, []))}}
    return next(iter(matches)) if len(matches) == 1 else None


def _classify(node, catalog, mappings):
    categories, subtypes = catalog["categories"], catalog["subtypes"]
    reasons = []
    category = None
    for field in ("category_id", "category"):
        if node.get(field) is None:
            continue
        found = _lookup(node[field], categories, mappings.get("category_aliases", {}))
        if found is None:
            reasons.append("unknown_category:" + field)
        elif category is not None and found != category:
            reasons.append("conflicting_categories")
        else:
            category = found
    names = [(field, node[field]) for field in ("subtype_id", "apparatus_kind", "kind", "type", "family")
             if node.get(field) is not None]
    found = set()
    for field, name in names:
        identifier = _lookup(name, subtypes, mappings.get("aliases", {}))
        if identifier is None:
            contextual = {item["subtype_id"] for item in mappings.get("contextual_aliases", [])
                          if _key(item["alias"]) == _key(name) and item["category_id"] == category}
            identifier = next(iter(contextual)) if len(contextual) == 1 else None
        if identifier is None:
            reasons.append("unknown_subtype:" + field)
        else:
            found.add(identifier)
    if len(found) > 1:
        reasons.append("conflicting_subtypes")
    subtype = next(iter(found)) if len(found) == 1 else None
    basis = "exact_alias" if names else None
    if not names:
        # A proposed automation template cannot establish the source vessel type.
        if node.get("binding_basis") != "unresolved_source_apparatus":
            configuration = node.get("configuration") or {}
            profile = configuration.get("profile_id", node.get("id"))
            subtype = mappings.get("profile_subtypes", {}).get(profile)
            basis = "catalog_profile" if subtype else None
        if not subtype:
            matches = {identifier for name, identifier in mappings.get("category_subtypes", {}).items()
                       if _key(name) == _key(node.get("category"))}
            subtype = next(iter(matches)) if len(matches) == 1 else None
            basis = "exact_category_type" if subtype else None
    if subtype:
        expected = subtypes[subtype]["category_id"]
        if category and category != expected:
            reasons.append("category_subtype_conflict")
        else:
            category = expected
    if reasons:
        # Conflicting context is not resolved by preferring the most familiar label.
        subtype = None
    if not subtype and not reasons:
        reasons.append("subtype_not_reported")
    return category, subtype, basis, list(dict.fromkeys(reasons))


def _normalize_node(node, catalog, mappings):
    output = copy.deepcopy(node)
    if output.get("normalization", {}).get("schema") == SCHEMA:
        return output
    if not isinstance(output.get("configuration", {}), dict):
        raise ValueError("Equipment configuration must be an object")
    original_names = {field: copy.deepcopy(output[field]) for field in _NAMES if field in output}
    for field in ("model", "manufacturer"):
        if field in output:
            original_names[field] = copy.deepcopy(output[field])
    category, subtype, basis, reasons = _classify(output, catalog, mappings)
    configuration_present = "configuration" in output
    configuration = copy.deepcopy(output.get("configuration", {}))
    added = []
    for field in ("model", "manufacturer"):
        if field in output:
            if field not in configuration:
                configuration[field] = output[field]
                added.append(field)
            elif configuration[field] != output[field]:
                reasons.append("conflicting_configuration:" + field)
            del output[field]
    if output.get("id") in mappings.get("profile_subtypes", {}) and "profile_id" not in configuration:
        configuration["profile_id"] = output["id"]
        added.append("profile_id")
    if configuration or configuration_present:
        output["configuration"] = configuration
    for field in _NAMES:
        output.pop(field, None)
    output.update(category_id=category, subtype_id=subtype,
                  category=catalog["categories"][category]["name"] if category else None,
                  apparatus_kind=catalog["subtypes"][subtype]["name"] if subtype else None)
    output["normalization"] = {"schema": SCHEMA, "status": "unresolved" if reasons else "resolved",
        "basis": basis, "mapping_id": "equipment.identity." + subtype if subtype else None,
        "original_names": original_names, "reasons": reasons,
        "canonical_identity": {field: output[field] for field in _IDENTITY},
        "configuration_present": configuration_present, "added_configuration_keys": added}
    return output


def normalize_equipment(hardware, *, catalog=None, mappings=None):
    """Return a canonical copy, preserving topology, supplied facts and source pins.

    Unknown names are kept under ``normalization.original_names`` with unresolved
    status. There is no model call, fuzzy match or implicit hardware repair.
    """
    catalog, mappings = _libraries(catalog, mappings)
    output = copy.deepcopy(hardware)
    if not isinstance(output, dict) or not isinstance(output.get("nodes", {}), dict):
        raise ValueError("Equipment normalization requires a hardware object with a nodes object")
    if "nodes" in output:
        output["nodes"] = {key: _normalize_node(node, catalog, mappings) for key, node in output["nodes"].items()}
    return output


def analysis_node(node, *, catalog=None):
    """Project names for legacy checks, keeping every current physical value.

    Changes to canonical identity invalidate its old source-evidence pin. A label
    edit cannot quietly retrieve the former subtype from provenance.
    """
    output = copy.deepcopy(node)
    provenance = output.get("normalization", {})
    if provenance.get("schema") != SCHEMA:
        return output
    catalog = load_library("equipment.yaml") if catalog is None else catalog
    valid = provenance.get("canonical_identity") == {field: output.get(field) for field in _IDENTITY}
    configuration = output.get("configuration", {})
    if valid:
        for field in _NAMES:
            output.pop(field, None)
        output.update({field: copy.deepcopy(value) for field, value in provenance.get("original_names", {}).items()
                       if field not in ("model", "manufacturer")})
        for field in ("model", "manufacturer"):
            if field in provenance.get("original_names", {}) and field in configuration:
                output[field] = copy.deepcopy(configuration[field])
    else:
        subtype = catalog["subtypes"].get(output.get("subtype_id"))
        category = catalog["categories"].get(output.get("category_id"))
        output["apparatus_kind"] = subtype["legacy_kind"] if subtype else output.get("apparatus_kind")
        if category:
            output["category"] = (subtype or {}).get("legacy_category", category["legacy_category"])
        output.pop("source_fact_sha256", None)
        output.pop("category_id", None)
        output.pop("subtype_id", None)
    for field in provenance.get("added_configuration_keys", []):
        if field == "profile_id" and configuration.get(field) != node.get("id"):
            continue
        configuration.pop(field, None)
    if not configuration and not provenance.get("configuration_present"):
        output.pop("configuration", None)
    output.pop("normalization", None)
    return output


def analysis_equipment(hardware, *, catalog=None):
    """Project current nodes only; intentionally missing nodes and links stay missing."""
    output = copy.deepcopy(hardware)
    if "nodes" in output:
        output["nodes"] = {key: analysis_node(node, catalog=catalog) for key, node in output["nodes"].items()}
    return output


def conditional_substitutes(requirement, candidates, *, catalog=None, mappings=None):
    """Check explicit substitution rules separately from exact alias resolution.

    Requirements identify canonical ``subtype_id`` (or an exact ``family`` alias)
    and ordinary functional demands accepted by ``check_substitution``. Every
    candidate is returned, including unknown/incompatible ones, with reasons.
    """
    from mosaic.equipment import check_substitution

    catalog, mappings = _libraries(catalog, mappings)
    requested = requirement.get("subtype_id", requirement.get("family"))
    subtype = _lookup(requested, catalog["subtypes"], mappings.get("aliases", {}))
    category = requirement.get("category_id")
    if category is not None:
        category = _lookup(category, catalog["categories"], mappings.get("category_aliases", {}))
    demands = {key: copy.deepcopy(value) for key, value in requirement.items()
               if key not in {"category_id", "subtype_id", "family"}}
    rows = candidates.values() if isinstance(candidates, dict) else candidates
    results = []
    for index, candidate in enumerate(rows):
        normalized = _normalize_node(candidate, catalog, mappings)
        target = normalized.get("subtype_id")
        rule = None
        if subtype and target:
            for possible in mappings.get("substitution_rules", []):
                if (possible["relation"] == "same_subtype" and subtype == target
                        or possible["relation"] == "conditional" and subtype in possible.get("subtypes", [])
                        and target in possible.get("subtypes", [])):
                    rule = possible
                    break
        analyzed = analysis_node(normalized, catalog=catalog)
        if target:
            # Alias equivalence is already established; old family spellings are
            # irrelevant to the independent physical-constraint check.
            analyzed["apparatus_kind"] = catalog["subtypes"][target]["legacy_kind"]
            analyzed.pop("kind", None)
            analyzed.pop("type", None)
            analyzed.pop("family", None)
        result = check_substitution(demands, analyzed)
        extra = []
        if normalized["normalization"].get("canonical_identity") != {
                field: normalized.get(field) for field in _IDENTITY}:
            extra.append({"field": "canonical_identity", "status": "unknown", "required": None,
                          "actual": target, "reason": "Canonical identity was edited; previous evidence cannot certify it"})
        if not rule:
            extra.append({"field": "substitution_rule", "status": "unknown", "required": subtype,
                          "actual": target, "reason": "No explicit substitution relation; shared category is insufficient"})
        elif any(key not in demands for key in rule.get("required_demands", [])) or (
                rule.get("any_demands") and not any(key in demands for key in rule["any_demands"])):
            extra.append({"field": "substitution_requirements", "status": "unknown", "required": rule,
                          "actual": sorted(demands), "reason": "Conditional alternative lacks required functional demands"})
        if requirement.get("category_id") is not None and (category is None or category != normalized.get("category_id")):
            extra.append({"field": "category_id", "status": "unknown" if category is None else "incompatible",
                          "required": category, "actual": normalized.get("category_id"), "reason": "Canonical category does not match"})
        result["checks"].extend(extra)
        result["unknowns"].extend(row for row in extra if row["status"] == "unknown")
        result["incompatibilities"].extend(row for row in extra if row["status"] == "incompatible")
        result["status"] = "incompatible" if result["incompatibilities"] else "unknown" if result["unknowns"] else "compatible"
        results.append({"candidate_id": candidate.get("id", str(index)), "rule_id": rule["id"] if rule else None,
                        "subtype_id": target, **result})
    return results
