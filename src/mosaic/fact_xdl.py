"""Lower facts to ordinary XDL elements; evidence and catalog IDs stay outside XML."""
from collections import defaultdict
import re

from lxml import etree

from .facts import ordered_events, validate_facts
from .protocol.io import load_library

MARKERS = {"not_reported": "__NOT_REPORTED__", "ambiguous": "__AMBIGUOUS__", "qualitative": "__QUALITATIVE__"}
_ATTRS = {"duration": "time", "duration_s": "time", "temperature": "temp", "temp_C": "temp",
          "rotation_speed": "stir_speed", "speed": "stir_speed", "substance_amount": "amount"}


def property_name(fact):
    attribute = fact["attribute"]
    if attribute in {"operation_id", "category_id", "subtype_id", "cluster", "contract", "normalization"}:
        raise ValueError("Catalog metadata is not an experimental XDL property")
    value = fact["value"]
    if attribute in {"dose", "amount"} and value["value_type"] == "quantity":
        return {"mass": "mass", "volume": "volume", "substance_amount": "amount", "molar_amount": "amount", "amount_of_substance": "amount"}.get(value["quantity_kind"], attribute)
    return _ATTRS.get(attribute, attribute)


def literal(value):
    if value["value_type"] == "quantity":
        magnitude = value["value"] + ("–" + value["upper_value"] if value.get("upper_value") is not None else "")
        return magnitude + " " + value["unit"]
    if value["value_type"] == "text":
        return value["text"]
    if value["value_type"] == "reference":
        return value["ref"]
    return MARKERS[value["status"]]


def compile_facts(graph, bindings, *, text):
    graph = validate_facts(graph, text)
    if bindings["unresolved"]:
        raise ValueError("Unresolved vocabulary: " + ", ".join(i["expression"] for i in bindings["unresolved"]))
    entities = {e["entity_id"]: e for e in graph["entities"]}
    events = {e["event_id"]: e for e in graph["events"]}
    facts = defaultdict(list)
    for fact in graph["facts"]:
        facts[fact["event_id"]].append(fact)
    root = etree.Element("Synthesis")
    etree.SubElement(root, "Metadata", description="Source-grounded extended XDL; expert review pending.")
    hardware, reagents, params, procedure = [etree.SubElement(root, tag) for tag in ("Hardware", "Reagents", "Parameters", "Procedure")]
    result = {"extensions": {"schema": "mosaic.xdl-extensions/1", "steps": {}, "equipment": {}},
              "hardware_config": {}, "observations": {}, "context": {}, "fact_locations": {},
              "event_locations": {}, "entity_locations": {}, "relations": graph["relations"], "missing_parameters": []}
    standards = load_library("xdl_steps.yaml")["steps"]
    for entity in entities.values():
        identifier = entity["entity_id"]
        if entity["kind"] == "equipment":
            equipment = bindings["equipment"][identifier]
            etree.SubElement(hardware, "Component", id=identifier, type=equipment["type"])
            result["extensions"]["equipment"][equipment["type"]] = {"description": equipment["name"]}
            result["hardware_config"][identifier] = {"properties": {}}
            result["entity_locations"][identifier] = {"kind": "hardware", "id": identifier, "type": equipment["type"]}
        else:
            # XDL identifies a reagent by name; duplicate instances may share it.
            if entity["name"] not in {node.get("name") for node in reagents}:
                etree.SubElement(reagents, "Reagent", name=entity["name"])
            result["entity_locations"][identifier] = {"kind": "reagent", "name": entity["name"]}

    def unknown(identifier, prop, status="not_reported"):
        name = "p_" + identifier + "_" + prop + MARKERS[status]
        if not any(p.get("id") == name for p in params):
            etree.SubElement(params, "Parameter", id=name, type="str")
            result["missing_parameters"].append({"parameter_id": name, "status": status})
        return name

    def assign(fact, attrs, *, prop=None, position, event_id, subject_id):
        prop = prop or property_name(fact)
        if not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", prop):
            raise ValueError("Invalid experimental parameter name")
        base, suffix = prop, 2
        while prop in attrs:
            prop, suffix = base + "_" + str(suffix), suffix + 1
        value = fact["value"]
        attrs[prop] = unknown(fact["fact_id"], prop, value["status"]) if value["value_type"] == "missing" or value["status"] == "qualitative" else literal(value)
        if value["value_type"] == "reference" and entities.get(value["ref"], {}).get("kind") in {"material", "sample"}:
            attrs[prop] = entities[value["ref"]]["name"]
        # Qualitative literal remains visible as a declared experimental property.
        if value["status"] == "qualitative":
            attrs[prop + "_description"] = literal(value)
        attrs[prop + "_scope"] = fact["scope"]
        if value["value_type"] == "quantity" and value["quantity_kind"] in {"relative_loading", "equivalents"}:
            attrs[prop + "_basis"] = value.get("basis_ref") or unknown(fact["fact_id"], "basis")
        result["fact_locations"][fact["fact_id"]] = {"kind": "step", "position": position, "property": prop,
            "event_id": event_id, "subject_id": subject_id}

    # same_interval heat+mix has a native lowering; other concurrent physical
    # actions are explicitly rejected instead of silently serialized.
    merged, skipped = {}, set()
    for relation in graph["relations"]:
        if relation["relation"] not in {"during", "same_interval"}:
            continue
        a, b = events[relation["subject_id"]], events[relation["object_id"]]
        if "observation" in {a["kind"], b["kind"]}:
            continue
        ids = {bindings["events"][e["event_id"]]["operation_id"] for e in (a, b)}
        thermal = {"op.heat", "op.cool", "op.temperature", "op.hold_temperature"}
        if relation["relation"] == "same_interval" and "op.mix" in ids and ids & thermal and a["vessel_id"] == b["vessel_id"]:
            heat, mix = (a, b) if bindings["events"][a["event_id"]]["operation_id"] in thermal else (b, a)
            method = bindings["events"][mix["event_id"]]["defaults"].get("method")
            if method != "stir":
                raise ValueError("Concurrent thermal/mixing method has no verified XDL lowering")
            merged[heat["event_id"]] = mix["event_id"]
            skipped.add(mix["event_id"])
        else:
            raise ValueError("Concurrent physical events have no verified XDL lowering: " + relation["relation_id"])

    for event in ordered_events(graph):
        identifier = event["event_id"]
        if event["kind"] == "observation" or identifier in skipped:
            continue
        bound = bindings["events"][identifier]
        tag = bound["name"]
        if bound["operation_id"] == "op.mix":
            tag = {"stir": "Stir", "shake": "Shake", "vortex": "Vortex"}.get(bound["defaults"].get("method"), "MixContents")
        local_facts = list(facts[identifier])
        if identifier in merged:
            local_facts += facts[merged[identifier]]
        if bound["operation_id"] in {"op.heat", "op.cool", "op.temperature", "op.hold_temperature"}:
            tag = "HeatChill" if any(property_name(f) == "time" for f in local_facts) else "HeatChillToTemp"
        participants = event["participant_ids"] if tag == "Add" else [None]
        participants = participants or [None]
        for participant in participants:
            position, attrs = len(procedure), {}
            if event["vessel_id"]:
                attrs["vessel"] = event["vessel_id"]
            if participant:
                attrs["reagent"] = entities[participant]["name"]
            if identifier in merged:
                attrs["stir"] = "true"
            for prop, value in bound.get("defaults", {}).items():
                if prop == "method" and bound["operation_id"] == "op.mix" and value in {"stir", "shake", "vortex"}:
                    continue
                if not isinstance(value, (str, bool)):
                    raise ValueError("A semantic mapping cannot supply experimental numeric values")
                attrs[prop] = str(value).lower() if isinstance(value, bool) else value
            for i, equipment_id in enumerate(event["equipment_ids"]):
                attrs["apparatus_" + str(i + 1)] = equipment_id
            if tag != "Add":
                for i, entity_id in enumerate(event["participant_ids"]):
                    attrs["material_" + str(i + 1)] = entities[entity_id]["name"]
            for fact in local_facts:
                if fact["category"] != "process":
                    continue
                subject = fact["subject_id"]
                if participant and subject in event["participant_ids"] and subject != participant:
                    continue
                if fact["fact_id"] in result["fact_locations"]:
                    continue
                prop = property_name(fact)
                # Identity already has an independently readable reagent binding.
                if fact["attribute"] == "identity" and subject == participant:
                    result["fact_locations"][fact["fact_id"]] = {"kind": "step", "position": position, "property": "reagent", "event_id": identifier, "subject_id": subject}
                    continue
                if subject in entities and subject != participant and subject != event["vessel_id"]:
                    prefix = "subject_" + subject
                    attrs[prefix] = entities[subject]["name"] if entities[subject]["kind"] != "equipment" else subject
                    prop = prefix + "_" + prop
                assign(fact, attrs, prop=prop, position=position, event_id=fact["event_id"], subject_id=subject)
            standard = standards.get(tag, {})
            required_props = {*standard.get("required", []), *(_ATTRS.get(p, p) for p in bound.get("required_parameters", []))}
            for required in sorted(required_props):
                if required not in attrs:
                    attrs[required] = unknown(identifier, required)
            extra = set(attrs) - set(standard.get("properties", []))
            if not standard or extra:
                declaration = result["extensions"]["steps"].setdefault(tag, {"properties": [], "required": [], "extends": tag if standard else None})
                declaration["properties"] = sorted(set(declaration["properties"]) | set(attrs))
                declaration["required"] = sorted(set(declaration["required"]) | required_props)
            etree.SubElement(procedure, tag, **attrs)
            result["event_locations"].setdefault(identifier, []).append(position)
            if identifier in merged:
                result["event_locations"][merged[identifier]] = [position]
    for fact in graph["facts"]:
        identifier = fact["fact_id"]
        if identifier in result["fact_locations"]:
            continue
        if fact["category"] == "process":
            raise ValueError("Process fact has no physical output location: " + identifier)
        if fact["category"] == "equipment":
            subject = fact["subject_id"]
            if subject not in result["hardware_config"]:
                raise ValueError("Equipment configuration has no reported component")
            destination = result["hardware_config"][subject]["properties"]
            prop = fact["attribute"] + "__" + identifier
            destination[prop] = {"value": fact["value"], "scope": fact["scope"], "attribute": fact["attribute"]}
            result["fact_locations"][identifier] = {"kind": "hardware_config", "subject_id": subject, "property": prop}
        else:
            section = "observations" if fact["category"] == "observation" else "context"
            result[section][identifier] = fact
            result["fact_locations"][identifier] = {"kind": section}
    if not len(params):
        root.remove(params)
    result["xml"] = etree.tostring(root, encoding="unicode", pretty_print=True)
    # Grammar checking is separate from semantic conservation.
    from .protocol.xdl_document import read_document
    read_document(result["xml"], extensions=result["extensions"])
    return result
