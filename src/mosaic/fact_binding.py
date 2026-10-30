"""Exact catalog binding. No fuzzy matching, inference of ratings or data repair."""
import re
import unicodedata
from .protocol.io import canonical


def key(value):
    return re.sub(r"[\s_-]+", "", unicodedata.normalize("NFKC", value).casefold())


def bind_facts(graph, snapshot):
    operations = snapshot["canonical_operations"]
    aliases = snapshot["operation_mappings"]["aliases"]
    output = {"events": {}, "equipment": {}, "unresolved": []}
    for event in graph["events"]:
        if event["kind"] == "observation":
            continue
        expression = key(event["expression"])
        matches = []
        for identifier, entry in operations.items():
            if expression == key(entry["name"]) and entry.get("kind") not in {"observation", "provenance"}:
                matches.append({"operation_id": identifier, "defaults": {}, "mapping_id": "name:" + identifier})
        for alias in aliases:
            if alias.get("operation_id") in operations and expression in {key(e) for e in alias.get("expressions", [])}:
                if operations[alias["operation_id"]].get("kind") in {"observation", "provenance"}:
                    continue
                if alias.get("classification") == "composition":
                    continue
                matches.append({"operation_id": alias["operation_id"], "defaults": alias.get("defaults", {}), "mapping_id": alias["id"]})
        # A more specific exact alias may carry semantic parameters (stir vs mix).
        identities = {(m["operation_id"], canonical(m["defaults"])) for m in matches}
        if len(identities) > 1:
            specific = [m for m in matches if m["defaults"]]
            identities = {(m["operation_id"], canonical(m["defaults"])) for m in specific}
            matches = specific
        if len(identities) == 1:
            chosen = matches[0]
            contract = operations[chosen["operation_id"]]
            required = [name for name, definition in contract.get("parameters", {}).items() if definition.get("required")]
            output["events"][event["event_id"]] = {**chosen, "name": contract["name"], "required_parameters": required}
        else:
            output["unresolved"].append({"kind": "operation", "object_id": event["event_id"], "expression": event["expression"]})
    catalog, mappings = snapshot["equipment_catalog"], snapshot["equipment_mappings"]
    for entity in graph["entities"]:
        if entity["kind"] != "equipment":
            continue
        expression = key(entity["expression"])
        matches = {identifier for identifier, entry in catalog["subtypes"].items()
                   if expression in {key(entry["name"]), key(entry["legacy_kind"]),
                                     *(key(e) for e in mappings.get("aliases", {}).get(identifier, []))}}
        if len(matches) == 1:
            identifier = next(iter(matches))
            entry = catalog["subtypes"][identifier]
            output["equipment"][entity["entity_id"]] = {"subtype_id": identifier, "category_id": entry["category_id"],
                    "name": entry["name"], "type": entry["legacy_kind"]}
        else:
            output["unresolved"].append({"kind": "equipment", "object_id": entity["entity_id"], "expression": entity["expression"]})
    return output
