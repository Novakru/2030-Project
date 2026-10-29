"""Conventional XDL elements/attributes; provenance and catalogs stay in JSON."""
import copy
import json
import math
import re

from lxml import etree

from .io import load_library
from .normalization import analysis_protocol, is_normalized, validate_normalized

PROFILE = "xdl-2.0+extensions/1"
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
_ALIASES = {"temp_C": "temp", "temperature": "temp", "duration_s": "time", "duration": "time",
            "pressure_mbar": "pressure", "wavelength_nm": "wavelength"}
_UNITS = {"temp_C": "°C", "duration_s": "s", "pressure_mbar": "mbar", "rpm": "rpm", "wavelength_nm": "nm"}
_PARAM_TYPES = {"time": "time", "temp": "temp", "pressure": "pressure", "volume": "volume",
                "mass": "mass", "amount": "str", "stir_speed": "rotation_speed"}


def _value(value):
    return value.get("value") if isinstance(value, dict) and "value" in value else value


def _physical_step(step, canonical):
    """Lower semantic groups to actual operations, never export cluster labels."""
    op = step["op"]
    fields = {key: copy.deepcopy(value) for key, value in step.items()
              if key not in {"id", "op", "meta", "requires", "parameters", "missing_parameters", "operation_id", "normalization", "reported_parameters", "source_quantities"}}
    for key, value in step.get("parameters", {}).items():
        if key in fields and fields[key] != value:
            # The common vessel is a structural reference, not a duplicate source scalar.
            if key != "vessel":
                raise ValueError("XDL parameter collision: " + key)
        fields[key] = copy.deepcopy(value)
    fields.update(copy.deepcopy(step.get("missing_parameters", {})))
    concept = canonical.get("operation_id")
    if concept == "op.mix":
        method = _value(canonical.get("parameters", {}).get("method", fields.get("method")))
        op = {"stir": "Stir", "shake": "Shake", "vortex": "Vortex"}.get(method, "MixContents")
        if method in {"stir", "shake", "vortex"}:
            fields.pop("method", None)
    elif concept in {"op.heat", "op.cool", "op.temperature", "op.hold_temperature"} and step["op"] in {"HeatChill", "Heat", "Cool", "SetTemperature"}:
        op = "HeatChill" if "duration_s" in fields else "HeatChillToTemp"
    elif concept == "op.add" and op not in {"Add"}:
        op = "Add"
        for key, value in canonical.get("parameters", {}).items():
            fields.setdefault(key, value)
        if "material" in fields and "reagent" not in fields:
            fields["reagent"] = fields.pop("material")
    elif op == "Atmosphere":
        mode = _value(fields.pop("mode", None))
        op = {"evac_refill": "EvacuateAndRefill", "purge": "Purge"}.get(mode, "SetAtmosphere")
        if op == "SetAtmosphere" and mode is not None:
            fields["mode"] = mode
    elif op == "Purify" and _value(fields.get("method")) == "chromatography":
        op = "RunColumn"
        fields.pop("method")
        fields["from_vessel"] = fields.pop("vessel", "reactor")
        fields.setdefault("column", "column")
    elif op == "Separate":
        fields["from_vessel"] = fields.pop("vessel", "reactor")
        fields["product_phase"] = fields.pop("keep_phase", "__NOT_REPORTED__")
        fields.setdefault("separation_vessel", "separator")
        fields.setdefault("purpose", "extract")
    elif op == "Filter":
        if _value(fields.get("keep")) == "filtrate" and "to_vessel" in fields:
            fields["filtrate_vessel"] = fields.pop("to_vessel")
        if _value(fields.get("keep")) == "filtrate":
            fields.pop("keep")
    if op == "Wait":
        fields.pop("vessel", None)
    if op == "Add":
        amounts = [fields.pop("amount")] if "amount" in fields else []
        amounts.extend(step.get("source_quantities", []))
        for amount in amounts:
            unit = amount.get("unit") if isinstance(amount, dict) else None
            key = "volume" if unit == "mL" else "mass" if unit == "mg" else "amount"
            if key not in fields:
                fields[key] = amount
    attrs = {}
    for key, value in fields.items():
        target = _ALIASES.get(key, key)
        if key == "rpm":
            target = "stir_speed" if op in {"Stir", "HeatChill", "HeatChillToTemp", "Irradiate", "Evaporate"} else "rotation_speed"
        if key in _UNITS and isinstance(value, (int, float)):
            value = {"value": value, "unit": _UNITS[key]}
        if target in attrs and attrs[target] != value:
            raise ValueError("XDL property mapping is ambiguous: " + target)
        attrs[target] = value
    if op.startswith("Mapped"):
        op = canonical["op"]
    if not _IDENTIFIER.fullmatch(op) or op.startswith("Mapped"):
        raise ValueError("An XDL step needs a concrete declared operation")
    return op, attrs


def compile_document(protocol):
    """Return XML plus external extension declarations and positional bindings."""
    if not is_normalized(protocol):
        raise ValueError("XDL export requires a checked normalized protocol")
    validate_normalized(protocol)
    source = analysis_protocol(protocol)
    current = {step["id"]: step for step in protocol["steps"]}
    standards = load_library("xdl_steps.yaml")["steps"]
    root = etree.Element("Synthesis")
    metadata = {"description": "Source-grounded procedure; unresolved parameters require review."}
    url = protocol.get("source", {}).get("publication_url") or protocol.get("source", {}).get("url")
    if url:
        metadata["publication"] = url
    etree.SubElement(root, "Metadata", **metadata)
    hardware = etree.SubElement(root, "Hardware")
    reagents = etree.SubElement(root, "Reagents")
    parameters = etree.SubElement(root, "Parameters")
    procedure = etree.SubElement(root, "Procedure")
    extensions = {"schema": "mosaic.xdl-extensions/1", "steps": {}, "equipment": {}}
    bindings = []
    reagent_ids, reagent_names = set(), {}
    for reagent in protocol.get("reagents", []):
        role = {"SOLVENT": "solvent", "REACTANT": "substrate", "CATALYST": "catalyst"}.get(reagent.get("role"), "reagent")
        name = reagent.get("name") or reagent["id"]
        reagent_names[reagent["id"]] = name
        if name not in reagent_ids:
            etree.SubElement(reagents, "Reagent", name=name, role=role)
            reagent_ids.add(name)
    components = set()
    nodes = protocol.get("hardware", {}).get("nodes", {})

    def component(identifier):
        if identifier in components:
            return
        if identifier not in nodes:
            raise ValueError("Undefined hardware reference; exporter cannot repair it: " + identifier)
        node = nodes[identifier]
        subtype = node.get("apparatus_kind")
        kind = re.sub(r"(?<!^)(?=[A-Z])", "_", subtype).lower() if isinstance(subtype, str) else "unresolved_apparatus"
        if not _IDENTIFIER.fullmatch(kind):
            kind = "unresolved_apparatus"
        etree.SubElement(hardware, "Component", id=identifier, type=kind)
        components.add(identifier)
        extensions["equipment"][kind] = {"description": "Concrete apparatus type; configuration and source evidence are external."}

    for identifier, node in sorted(nodes.items()):
        if node.get("binding_basis") in {"source_reported", "operation_requirement"}:
            component(identifier)

    def literal(value, key, step_id):
        if isinstance(value, dict) and "marker" in value:
            identifier = "p_" + step_id + "_" + key + value["marker"]
            identifier = re.sub(r"\W", "_", identifier)
            etree.SubElement(parameters, "Parameter", id=identifier, type=_PARAM_TYPES.get(key, "str"))
            return identifier
        if isinstance(value, str) and value in {"__NOT_REPORTED__", "__QUALITATIVE__", "__AMBIGUOUS__"}:
            return literal({"marker": value}, key, step_id)
        if isinstance(value, dict) and "value" in value:
            scalar = literal(value["value"], key, step_id)
            return scalar + " " + value["unit"] if value.get("unit") else scalar
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (int, float)):
            if not math.isfinite(value):
                raise ValueError("XDL numeric value must be finite")
            return format(value, ".12g")
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        return str(value)

    for index, step in enumerate(source["steps"]):
        tag, values = _physical_step(step, current[step["id"]])
        standard = standards.get(tag)
        # An extension adds only operation properties, not another XML grammar.
        properties = set(standard["properties"]) if standard else set()
        additional = set(values) - properties
        if not standard or additional:
            extension = extensions["steps"].setdefault(tag, {"properties": [], "required": [], "extends": tag if standard else None})
            extension["properties"] = sorted(set(extension["properties"]) | set(values))
        attrs = {}
        for key, value in sorted(values.items()):
            if not _IDENTIFIER.fullmatch(key) or key in {"normalization", "operation_id", "category_id", "subtype_id", "cluster", "contract"}:
                raise ValueError("Nonexperimental XDL property: " + key)
            if value is None:
                continue
            actual = _value(value)
            if key in {"vessel", "from_vessel", "to_vessel", "filtrate_vessel", "separation_vessel", "column"} and isinstance(actual, str) and not actual.startswith("__"):
                reference = actual if actual in nodes else protocol.get("hardware", {}).get("reference_aliases", {}).get(actual, actual)
                component(reference)
                value = reference
            if key == "reagent" and isinstance(actual, str):
                if actual not in reagent_names and actual not in reagent_ids:
                    raise ValueError("Undefined reagent reference: " + actual)
                value = reagent_names.get(actual, actual)
            attrs[key] = literal(value, key, step["id"])
        if standard:
            for key in standard["required"]:
                if key not in attrs:
                    attrs[key] = literal({"marker": "__NOT_REPORTED__"}, key, step["id"])
        etree.SubElement(procedure, tag, **dict(sorted(attrs.items())))
        group = protocol["normalization"].get("groups", {}).get("composition:" + step["id"], {})
        bindings.append({"position": index, "step_id": step["id"], "tag": tag,
                         "member_ids": group.get("member_ids", [step["id"]])})
    if not len(parameters):
        root.remove(parameters)
    xml = etree.tostring(root, encoding="unicode", pretty_print=True)
    read_document(xml, extensions=extensions)
    return {"xml": xml, "extensions": extensions, "bindings": bindings}


def read_document(xml, *, extensions=None):
    """Validate conventional XML, identifiers, declared tags and references."""
    parser = etree.XMLParser(resolve_entities=False, no_network=True, remove_comments=True)
    try:
        root = etree.fromstring(xml.encode("utf-8") if isinstance(xml, str) else xml, parser)
    except (ValueError, TypeError, etree.XMLSyntaxError) as error:
        raise ValueError("Invalid XDL XML") from error
    if root.getroottree().docinfo.doctype:
        raise ValueError("DOCTYPE is not allowed")
    if root.tag == "XDL" and len(root) == 1:
        root = root[0]
    if root.tag != "Synthesis" or root.attrib or root.nsmap:
        raise ValueError("XDL requires ordinary Synthesis sections without private namespaces")
    tags = [node.tag for node in root]
    expected = [tag for tag in ("Metadata", "Hardware", "Reagents", "Parameters", "Procedure") if tag in tags]
    if tags != expected or any(tags.count(tag) != 1 for tag in tags) or not {"Hardware", "Reagents", "Procedure"} <= set(tags):
        raise ValueError("Invalid XDL section layout")
    extensions = extensions or {}
    steps = load_library("xdl_steps.yaml")["steps"]
    equipment = {re.sub(r"(?<!^)(?=[A-Z])", "_", entry["name"]).lower() for entry in load_library("equipment.yaml")["subtypes"].values()}
    equipment |= {"reactor", "unresolved_apparatus", *extensions.get("equipment", {})}
    identifiers, components, reagents, parameters = set(), set(), set(), set()
    data = {"hardware": [], "reagents": [], "parameters": [], "steps": [], "metadata": {}}
    for section in root:
        if section.tag == "Metadata":
            if len(section) or set(section.attrib) - {"description", "publication"}:
                raise ValueError("Unexpected XDL metadata")
            data["metadata"] = dict(section.attrib)
            continue
        for node in section:
            if len(node) or node.nsmap:
                raise ValueError("Unexpected nested/private XDL node")
            attrs = dict(node.attrib)
            if section.tag == "Procedure":
                standard, extension = steps.get(node.tag), extensions.get("steps", {}).get(node.tag)
                if standard is None and extension is None:
                    raise ValueError("Undeclared XDL operation: " + str(node.tag))
                allowed = set((standard or {}).get("properties", [])) | set((extension or {}).get("properties", []))
                required = set((standard or {}).get("required", [])) | set((extension or {}).get("required", []))
                if set(attrs) - allowed or not required <= set(attrs):
                    raise ValueError("Invalid properties for XDL operation " + node.tag)
                for key, value in attrs.items():
                    pool = reagents if key == "reagent" else components if key in {"vessel", "from_vessel", "to_vessel", "filtrate_vessel", "separation_vessel", "column"} else None
                    if pool is not None and value not in pool and value not in parameters:
                        raise ValueError("Undefined XDL reference: " + value)
                data["steps"].append({"op": node.tag, **attrs})
                continue
            tag, required, allowed, field, target = {
                "Hardware": ("Component", {"id", "type"}, {"id", "type"}, "id", components),
                "Reagents": ("Reagent", {"name"}, {"name", "role"}, "name", reagents),
                "Parameters": ("Parameter", {"id", "type"}, {"id", "type", "value"}, "id", parameters),
            }[section.tag]
            if node.tag != tag or not required <= set(attrs) or set(attrs) - allowed:
                raise ValueError("Invalid XDL declaration")
            identifier = attrs[field]
            if not identifier or identifier in identifiers:
                raise ValueError("Duplicate or empty XDL identifier")
            identifiers.add(identifier)
            target.add(identifier)
            if section.tag == "Hardware" and attrs["type"] not in equipment:
                raise ValueError("Undeclared XDL equipment type")
            data[{"Hardware": "hardware", "Reagents": "reagents", "Parameters": "parameters"}[section.tag]].append(attrs)
    return data
