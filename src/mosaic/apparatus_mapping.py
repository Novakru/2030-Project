"""Bind quoted apparatus mentions, keeping observations apart from requirements."""
import copy
import re

from .protocol.apparatus import source_fact_hash
from .protocol.crosscheck import quantities_in_text
from .protocol.equipment_normalization import _key
from .protocol.io import digest


def bind_mentions(protocol, mentions, document, registry):
    """Only explicit numbers become source facts; new types can remain unresolved."""
    result = copy.deepcopy(protocol)
    hardware = result["hardware"]
    catalog = registry.snapshot["equipment_catalog"]
    issues = []
    for mention in mentions:
        quote = mention.get("quote")
        name = mention.get("identity") or mention.get("kind")
        if not isinstance(quote, str) or quote not in document["procedure"] or not isinstance(name, str) or not _key(name):
            issues.append("Invalid apparatus source mention")
            continue
        if _key(name) not in _key(quote):
            # A semantic kind is useful as a proposal, but is not a quoted fact.
            name = mention.get("kind")
            if not isinstance(name, str) or _key(name) not in _key(quote):
                issues.append("Apparatus name has no literal source support")
                continue
        basis = "source_reported" if re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)", quote, re.I) else "operation_requirement"
        category_id = mention.get("category_id")
        category = catalog["categories"].get(category_id, {}).get("legacy_category")
        params, parameters = {}, mention.get("parameters", {})
        if parameters and not isinstance(parameters, dict):
            issues.append("Apparatus parameters are not an object")
            continue
        for key, value in (parameters or {}).items():
            # Apparatus observations are operating facts, never model ratings.
            if key != "capacity_mL" or not isinstance(value, dict):
                issues.append("Unimplemented apparatus parameter: " + str(key))
                continue
            evidence = value.get("evidence", "")
            number = value.get("value")
            # Volume must be immediately attached to the apparatus name.
            adjacent = re.search(r"(\d+(?:\.\d+)?)\s*(mL|[uµμ]L|L)\s+" + re.escape(name), evidence, re.I)
            if (basis != "source_reported" or not adjacent or evidence not in quote
                    or not isinstance(number, (int, float)) or isinstance(number, bool)
                    or number not in quantities_in_text(adjacent[0], "mL")):
                issues.append("Apparatus capacity is not an adjacent literal source quantity")
                continue
            params[key] = number
        scope = "unknown"
        if "capacity_mL" in params:
            if re.search(r"per\s+well|each\s+well", quote, re.I):
                scope = "per_well"
            elif not re.search(r"plate|block", name, re.I):
                scope = "single_reaction_vessel"
        node = {"apparatus_kind": name, "category": category, "params": params,
                "capacity_scope": scope,
                "binding_basis": basis, "verified": False, "source_parameters": list(params),
                "source_evidence": [{"source_url": document.get("source", {}).get("url"),
                    "raw_sha256": document["raw_sha256"], "locator": "/procedure", "value": quote}],
                "verification": {"status": basis, "human_verified": False}}
        identifier = "apparatus_" + digest({"source": document["id"], "name": name, "quote": quote})[:16]
        node["id"] = identifier
        node["source_fact_sha256"] = source_fact_hash(node)
        named = [key for key in hardware["nodes"] if _key(key) == _key(name)]
        target = named[0] if len(named) == 1 else None
        if mention.get("role") == "reaction_container" and target is None:
            previous = hardware["nodes"].get("reactor", {})
            if previous.get("binding_basis") == "unresolved_source_apparatus":
                target = "reactor"
            elif _key(previous.get("apparatus_kind")) == _key(name):
                hardware.setdefault("reference_aliases", {})[name] = "reactor"
                continue
            elif (previous.get("apparatus_kind") in {"flask", "vial"}
                  and _key(previous["apparatus_kind"]) in _key(name)
                  and any(name in fact.get("value", "") for fact in previous.get("source_evidence", []))):
                # Refine the same quoted vessel, retaining its independently parsed facts.
                target = "reactor"
                node["params"] = {**previous.get("params", {}), **node["params"]}
                node["capacity_scope"] = previous.get("capacity_scope", node["capacity_scope"])
                node["source_parameters"] = sorted(node["params"])
                node["source_fact_sha256"] = source_fact_hash(node)
        target = target or identifier
        hardware["nodes"][target] = node
        hardware.setdefault("reference_aliases", {})[name] = target
        # No connection or specific device-to-step binding is invented here.
    hardware.setdefault("source_issues", []).extend({"reason": issue} for issue in issues)
    return result
