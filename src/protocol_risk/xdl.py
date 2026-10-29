"""A documented XDL 2 subset; IR annotations stay in JSON sidecars."""
from __future__ import annotations

import copy
import json
from pathlib import Path

from lxml import etree

from .io import ROOT, digest, load_library

PROFILE = "protocol-risk-xdl2-subset-v1"


def _num(number):
    return format(float(number), ".12g")


def _value(number, unit):
    return _num(number) + " " + unit


def export_xdl(protocol):
    from .canonical_xdl import PROFILE as CANONICAL_PROFILE, export_canonical_xdl
    if protocol.get("xdl_profile") == CANONICAL_PROFILE:
        return export_canonical_xdl(protocol)
    from .extensions import PROFILE as EXTENDED_PROFILE, export_extended_xdl
    if protocol.get("xdl_profile") == EXTENDED_PROFILE:
        return export_extended_xdl(protocol)
    if protocol.get("xdl_profile") not in {None, PROFILE}:
        raise ValueError("Unknown XDL profile: " + str(protocol["xdl_profile"]))
    root = etree.Element("Synthesis")
    description = ("Authored symbolic control; not an observed experiment." if protocol.get("source", {}).get("db") == "AUTHORED_CONTROL"
                   else "Source-grounded protocol representation; hardware execution requires compilation and review.")
    if protocol.get("quality", {}).get("tier") == "perturbed":
        description = "Intentionally perturbed source-derived procedure; experimental outcome not observed."
    etree.SubElement(root, "Metadata", description=description,
                     publication=protocol.get("source", {}).get("publication_url") or protocol.get("source", {}).get("url") or "",
                     reaction_class=protocol.get("reaction_class") or "")
    hardware = etree.SubElement(root, "Hardware")
    for name, node in sorted(protocol["hardware"]["nodes"].items()):
        category = node.get("category", "vessel")
        # Hardware section is virtual; the physical graph and limits are sidecar data.
        kind = {"vessel": "reactor", "heater_stirrer": "heater", "light_source": "light"}.get(category, category)
        facts = json.dumps({"component": name, "params": node.get("params", {}),
                            "wetted_materials": node.get("wetted_materials"), "verified": node.get("verified", False)}, ensure_ascii=False, sort_keys=True)
        hardware.append(etree.Comment(("Analysis binding: " + facts).replace("--", "—").rstrip("-")))
        etree.SubElement(hardware, "Component", id=name, type=kind)
    reagents = etree.SubElement(root, "Reagents")
    names = {r["id"]: r["id"] for r in protocol["reagents"]}
    for r in protocol["reagents"]:
        # Stable IDs are names in XDL; chemical names and identifiers are in sidecars/comments.
        reagents.append(etree.Comment((r["id"] + ": " + r["name"]).replace("--", "—").rstrip("-")))
        role = {"SOLVENT": "solvent", "REACTANT": "substrate", "CATALYST": "catalyst"}.get(r.get("role"), "reagent")
        etree.SubElement(reagents, "Reagent", name=r["id"], role=role)
    procedure = etree.SubElement(root, "Procedure")
    if protocol.get("initial_contents"):
        procedure.append(etree.Comment(("Analysis initial contents (preloaded; quantity may be unknown): " + json.dumps(protocol["initial_contents"], ensure_ascii=False, sort_keys=True)).replace("--", "—").rstrip("-")))
    if protocol.get("representation_scope"):
        procedure.append(etree.Comment(("Representation scope: " + protocol["representation_scope"]).replace("--", "—").rstrip("-")))
    for note in protocol.get("unresolved_instructions", []):
        procedure.append(etree.Comment(("Unresolved source instruction: " + note).replace("--", "—").rstrip("-")))
    context = protocol.get("context", {})
    declared_context = {key: context[key] for key in ("pressure_control", "reflux", "pure_solvent", "ignition_source", "vapor_exposed", "oxygen_present", "purpose", "inert_required") if key in context}
    procedure.append(etree.Comment(("Analysis context: " + json.dumps(declared_context, ensure_ascii=False, sort_keys=True)).replace("--", "—").rstrip("-")))
    if protocol.get("context", {}).get("pressure_control") not in (None, "UNKNOWN"):
        procedure.append(etree.Comment("Pressure-control context: " + protocol["context"]["pressure_control"]))
    for step in protocol["steps"]:
        op = step["op"]
        vessel = step.get("vessel", "reactor")
        evidence = step.get("meta", {}).get("evidence")
        if evidence:
            procedure.append(etree.Comment(evidence.replace("--", "—").rstrip("-")))
        if "controller_setpoint_C" in step:
            procedure.append(etree.Comment("Analysis controller setpoint: " + _value(step["controller_setpoint_C"], "°C")))
        attrs, tag = {}, op
        if op == "Add":
            if not step.get("amount"):
                raise ValueError(f"{step['id']}: cannot export unquantified Add")
            amount = step["amount"]
            attrs = {"vessel": vessel, "reagent": names.get(step["reagent"], step["reagent"]),
                     "amount": _value(amount["value"], amount["unit"])}
        elif op == "Transfer":
            attrs = {"from_vessel": step["from_vessel"], "to_vessel": step["to_vessel"],
                     "amount": _value(step["amount"]["value"], step["amount"]["unit"])}
        elif op == "HeatChill":
            attrs = {"vessel": vessel, "temp": _value(step["temp_C"], "°C")}
            if "duration_s" in step:
                attrs["time"] = _value(step["duration_s"], "s")
            else:
                tag = "HeatChillToTemp"
            if step.get("stir"):
                attrs["stir"] = "true"
        elif op == "Stir":
            attrs = {"vessel": vessel, "time": _value(step["duration_s"], "s")}
        elif op == "Wait":
            attrs = {"time": _value(step["duration_s"], "s")}
        elif op == "Atmosphere":
            mode = step.get("mode")
            if mode in ("environment", "balloon"):
                procedure.append(etree.Comment(f"Atmosphere context (no purge operation inferred): {step['gas']}; {mode}"))
                continue
            if mode not in ("purge", "evac_refill"):
                raise ValueError("Unknown atmosphere mode")
            tag = "Purge" if mode == "purge" else "EvacuateAndRefill"
            attrs = {"vessel": vessel, "gas": step["gas"]}
            if mode == "purge" and "duration_s" in step:
                attrs["time"] = _value(step["duration_s"], "s")
        elif op == "Filter":
            attrs = {"vessel": vessel}
            if step.get("keep") == "filtrate":
                attrs["filtrate_vessel"] = step.get("to_vessel", "filtrate")
        elif op == "Separate":
            if step.get("keep_phase") not in ("top", "bottom"):
                raise ValueError("Product phase not specified; no faithful Separate export")
            attrs = {"purpose": "extract", "from_vessel": vessel, "separation_vessel": "separator",
                     "to_vessel": step.get("to_vessel", "product"), "product_phase": step["keep_phase"]}
        elif op == "Evaporate":
            attrs = {"vessel": vessel}
            for field, attr, unit in (("temp_C", "temp", "°C"), ("pressure_mbar", "pressure", "mbar"), ("duration_s", "time", "s")):
                if field in step:
                    attrs[attr] = _value(step[field], unit)
        elif op == "Purify":
            if step.get("method") != "chromatography":
                raise ValueError("Only documented RunColumn mapping is available for chromatography")
            tag = "RunColumn"
            attrs = {"from_vessel": vessel, "to_vessel": step.get("to_vessel", "product"), "column": "column"}
        elif op == "Irradiate":
            attrs = {"vessel": vessel, "time": _value(step["duration_s"], "s")}
            if "wavelength_nm" in step:
                attrs["wavelength"] = _num(step["wavelength_nm"])
            if "color" in step:
                attrs["color"] = step["color"]
        else:
            raise ValueError(f"Unsupported standard XDL export: {op}")
        if "rpm" in step:
            attrs["stir_speed"] = _num(step["rpm"])
        etree.SubElement(procedure, tag, **attrs)
    return etree.tostring(root, encoding="unicode", pretty_print=True)


def validate_xdl(xml):
    from .extensions import NS as EXTENDED_NS, PROFILE as EXTENDED_PROFILE, validate_extended_xdl
    parser = etree.XMLParser(resolve_entities=False, no_network=True)
    doc = etree.fromstring(xml.encode("utf-8"), parser)
    if doc.getroottree().docinfo.doctype:
        raise ValueError("DOCTYPE is not allowed")
    profile = doc.get("{" + EXTENDED_NS + "}profile")
    from .canonical_xdl import PROFILE as CANONICAL_PROFILE, validate_canonical_xdl
    if profile == CANONICAL_PROFILE:
        return validate_canonical_xdl(xml)
    if profile is not None or EXTENDED_NS in doc.nsmap.values():
        if profile != EXTENDED_PROFILE:
            raise ValueError("Unknown or missing MOSAIC XDL profile")
        return validate_extended_xdl(xml)
    schema = etree.XMLSchema(etree.parse(str(ROOT / "schemas/xdl2_subset.xsd"), parser))
    schema.assertValid(doc)
    return True


def canonical_hash(protocol):
    # Provenance/comments/IDs do not make otherwise identical protocols unique.
    from .normalization import is_normalized, semantic_contract_hash
    if is_normalized(protocol):
        positions = {step["id"]: index for index, step in enumerate(protocol["steps"])}
        def semantics(value):
            if isinstance(value, list):
                return [semantics(item) for item in value]
            if isinstance(value, dict):
                return {key: semantics(item) for key, item in value.items()
                        if key not in {"meta", "normalization", "evidence", "origins", "source", "op"}}
            return value
        steps = []
        for step in protocol["steps"]:
            item = semantics(step)
            item.pop("id", None)
            if "requires" in item:
                item["requires"] = [positions.get(ref, ref) for ref in item["requires"]]
            steps.append(item)
        contracts = {definition["id"]: semantic_contract_hash(definition)
                     for definition in protocol.get("operation_definitions", {}).values()}
        relations = [{key: positions.get(value, value) if key in {"from", "to"} else semantics(value)
                      for key, value in relation.items() if key != "group_id"}
                     for relation in protocol.get("temporal_relations", [])]
        return digest({"steps": steps, "contracts": contracts, "temporal_relations": relations,
                       "context": semantics(protocol.get("context", {})),
                       "initial_contents": protocol.get("initial_contents", {})}, "sha1")
    clean = copy.deepcopy(protocol)
    from .extensions import PROFILE as EXTENDED_PROFILE, definition_semantic_hash
    extended = clean.get("xdl_profile") == EXTENDED_PROFILE
    reagent_map = {r["id"]: r.get("smiles") or r["name"] for r in clean["reagents"]}
    steps = []
    step_positions = {s["id"]: i for i, s in enumerate(clean["steps"])}
    for s in clean["steps"]:
        s = {k: v for k, v in s.items() if k not in ("meta", "id")}
        if "reagent" in s:
            s["reagent"] = reagent_map.get(s["reagent"], s["reagent"])
        if "requires" in s:
            s["requires"] = [step_positions.get(identifier, identifier) for identifier in s["requires"]]
        if extended:
            for field in ("parameters", "missing_parameters"):
                if isinstance(s.get(field), dict):
                    s[field] = {key: {k: v for k, v in value.items() if k not in {"evidence", "origins", "source"}}
                                if isinstance(value, dict) else value for key, value in s[field].items()}
        steps.append(s)
    initial = {vessel: [{"reagent": reagent_map.get(item["reagent"], item["reagent"]), "amount": item.get("amount")} for item in items]
               for vessel, items in clean.get("initial_contents", {}).items()}
    semantic = {"steps": steps, "context": {k: clean.get("context", {}).get(k) for k in
                    ("reflux", "pressure_control", "pure_solvent", "ignition_source")}}
    if initial:
        semantic["initial_contents"] = initial
    if extended:
        definitions = clean.get("operation_definitions", {})
        semantic["operation_definitions"] = {name: definition_semantic_hash(name, definitions[name])
            for name in sorted({step["op"] for step in clean["steps"]} & set(definitions))}
    return digest(semantic, "sha1")


def bind_hardware(protocol, devices=None, configuration=None, raw=None):
    from .apparatus import source_apparatus, source_heating_block
    library = devices if devices is not None else {x["id"]: x for x in load_library("hardware.yaml")["devices"]}
    volume = sum(s.get("amount", {}).get("value", 0) for s in protocol["steps"]
                 if s["op"] == "Add" and s.get("amount", {}).get("unit") == "mL")
    vessel, source_issues = source_apparatus(protocol, raw)
    if vessel is None:
        vessel = copy.deepcopy(library["chemputer_reactor_template"])
        vessel["binding_basis"] = "unresolved_source_apparatus"
    controller = source_heating_block(protocol, raw)
    if controller is None:
        controller = copy.deepcopy(library["ika_rct_basic_25008259"])
        controller["binding_basis"] = "proposed_analysis_configuration"
        controller["note"] = "Proposed analysis controller; source does not identify this model as the original equipment."
    nodes = {"reactor": vessel, "heater": controller}
    for s in protocol["steps"]:
        for key in ("to_vessel", "from_vessel", "vessel"):
            if key in s and s[key] not in nodes:
                nodes[s[key]] = {"category": "vessel", "params": {}, "verified": False}
        if s["op"] == "Filter":
            nodes["filter"] = copy.deepcopy(library["chemputer_filter_template"])
            nodes.setdefault("filtrate", {"category": "vessel", "params": {}, "verified": False})
        if s["op"] == "Separate":
            nodes["separator"] = copy.deepcopy(library["chemputer_separator_template"])
        if s["op"] in ("Separate", "Purify"):
            nodes.setdefault("product", {"category": "vessel", "params": {}, "verified": False})
        if s["op"] == "Purify":
            nodes["column"] = {"category": "column", "params": {}, "verified": False}
        if s["op"] == "Irradiate":
            nodes["light"] = copy.deepcopy(library["chemputer_light_template"])
    protocol["hardware"] = {"config_id": "source_aware_provisional_v2", "nodes": nodes,
                            "edges": [["reactor", node] for node in nodes if node != "reactor"],
                            "bindings": {"heater": "heater"}, "estimated_liquid_lower_bound_mL": volume,
                            "verification_status": "human_review_pending", "source_issues": source_issues,
                            "binding_scope": "Source-reported vessels; unspecified automation remains a proposed analysis configuration. Edges are provisional.",
                            "inventory_scope": "Sum of stated Add volumes, not peak vessel occupancy or inferred solvent volume."}
    if configuration is not None:
        if not isinstance(configuration, dict):
            raise ValueError("Hardware configuration must be an object")
        mapping = configuration.get("nodes", {})
        edges, bindings = configuration.get("edges", []), configuration.get("bindings", {})
        if (not isinstance(mapping, dict) or not mapping or any(v not in library for v in mapping.values())
                or not isinstance(edges, list) or any(not isinstance(e, list) or len(e) != 2 or any(n not in mapping for n in e) for e in edges)
                or not isinstance(bindings, dict) or any(n not in mapping for n in bindings.values())):
            raise ValueError("Invalid reviewed hardware configuration: use library device IDs and declared graph nodes")
        protocol["hardware"] = {"config_id": configuration.get("id", "reviewed_binding_" + protocol["id"]),
                                "nodes": {k: copy.deepcopy(library[v]) for k, v in mapping.items()},
                                "edges": copy.deepcopy(edges), "bindings": copy.deepcopy(bindings),
                                "estimated_liquid_lower_bound_mL": volume, "verification_status": "topology_review_pending",
                                "source_apparatus": vessel, "source_issues": source_issues,
                                "binding_scope": "Explicit configuration override; original source apparatus retained for comparison."}
    return protocol
