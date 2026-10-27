"""Source-grounded operation contracts and a lossless, explicit XDL extension.

An admitted contract makes an action representable. It never installs executable
code, supplies an equipment implementation, or certifies experimental safety.
"""
from __future__ import annotations

import copy
import json
import math
import re

from lxml import etree

from .io import digest, load_library

PROFILE = "mosaic-xdl/1"
NS = "urn:mosaic:xdl:extensions:1"
MISSING_MARKERS = {
    "not_reported": "__NOT_REPORTED__",
    "qualitative": "__QUALITATIVE__",
    "ambiguous": "__AMBIGUOUS__",
}
PARAMETER_TYPES = {"string", "number", "integer", "boolean", "quantity", "reference"}
_IDENTIFIER = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,79}\Z")
_DEFINITION_FIELDS = {"name", "domain", "description", "parameters", "effects", "hardware_roles",
                      "evidence", "origins", "representation_status", "execution_supported",
                      "semantic_sha256", "version", "reason", "status"}
_PARAMETER_FIELDS = {"type", "required", "unit", "dimension", "description"}
_CONTRACT_FIELDS = ("description", "parameters", "effects", "hardware_roles")


def _core_operations():
    from .extract import OPERATIONS
    definitions = load_library("primitives.yaml")["operations"]
    return {name: definitions[name] for name in OPERATIONS}


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(label + " must be a nonempty string")
    return value


def _finite(value):
    try:
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
    except OverflowError:
        return False


def definition_semantic_hash(name, definition):
    """Hash semantics independently of citations, evidence and admission metadata."""
    contract = {key: copy.deepcopy(definition.get(key, [] if key == "hardware_roles" else None))
                for key in _CONTRACT_FIELDS}
    return digest({"name": name, "domain": definition.get("domain", "chemistry"), "contract": contract})


def normalize_definition(name, definition):
    """Validate a declarative atomic contract and admit its representation only.

    Definitions cannot override the existing core vocabulary. Source validation
    belongs to the instance, so the same contract can be reused across records.
    """
    if not isinstance(name, str) or not _IDENTIFIER.fullmatch(name):
        raise ValueError("Operation name must be an identifier")
    if name in _core_operations():
        raise ValueError("An extension cannot overwrite a core operation: " + name)
    if not isinstance(definition, dict) or set(definition) - _DEFINITION_FIELDS:
        raise ValueError("Operation definition contains unsupported fields")
    if definition.get("name", name) != name:
        raise ValueError("Operation definition name disagrees with its key")
    if definition.get("execution_supported", False) is not False:
        raise ValueError("Declarative operation admission cannot enable execution")
    result = copy.deepcopy(definition)
    _text(result.get("description"), "Operation description")
    domain = _text(result.get("domain", "chemistry"), "Operation domain")
    parameters = result.get("parameters")
    if not isinstance(parameters, dict):
        raise ValueError("Operation parameters must be an object")
    for key, parameter in parameters.items():
        if not isinstance(key, str) or not _IDENTIFIER.fullmatch(key):
            raise ValueError("Parameter names must be identifiers")
        if not isinstance(parameter, dict) or set(parameter) - _PARAMETER_FIELDS:
            raise ValueError("Parameter contract contains unsupported fields: " + key)
        if parameter.get("type") not in PARAMETER_TYPES or not isinstance(parameter.get("required"), bool):
            raise ValueError("Parameter needs a supported type and boolean required flag: " + key)
        for field in ("unit", "dimension", "description"):
            if field in parameter:
                _text(parameter[field], "Parameter " + field)
        if "unit" in parameter and parameter["type"] not in {"number", "integer", "quantity"}:
            raise ValueError("Only numeric parameters may declare a unit: " + key)
    for field in ("effects", "hardware_roles"):
        values = result.get(field, [] if field == "hardware_roles" else None)
        if not isinstance(values, list) or any(not isinstance(item, str) or not item.strip() for item in values):
            raise ValueError("Operation " + field + " must be a list of nonempty strings")
        if len(values) != len(set(values)):
            raise ValueError("Operation " + field + " must not contain duplicates")
        result[field] = values
    result.update(name=name, domain=domain, execution_supported=False, representation_status="admitted")
    semantic_hash = definition_semantic_hash(name, result)
    if "semantic_sha256" in definition and definition["semantic_sha256"] != semantic_hash:
        raise ValueError("Operation semantic hash does not match its contract")
    result["semantic_sha256"] = semantic_hash
    return result


def _source_text(source):
    if source is None or isinstance(source, str):
        return source
    if isinstance(source, dict):
        text = source.get("procedure", source.get("source_text"))
        if isinstance(text, str):
            return text
    raise ValueError("Source must contain literal procedure text")


def _evidence(value, source, label):
    quote = _text(value, label)
    if source is not None and quote not in source:
        raise ValueError(label + " is not an exact source substring")
    return quote


def _validate_missing(value, source=None):
    if not isinstance(value, dict) or set(value) - {"status", "marker", "evidence", "raw"}:
        raise ValueError("Missing parameter must be a closed marker object")
    status = value.get("status")
    if status not in MISSING_MARKERS or value.get("marker") != MISSING_MARKERS[status]:
        raise ValueError("Missing parameter status and marker disagree")
    quote = _evidence(value.get("evidence"), source, "Missing parameter evidence")
    raw = value.get("raw")
    if raw is not None and (not isinstance(raw, str) or not raw or raw not in quote):
        raise ValueError("A missing parameter's raw wording must occur in its evidence")
    if status in {"qualitative", "ambiguous"} and raw is None:
        raise ValueError("Qualitative and ambiguous values need their original wording")


def _numeric_grounded(value, unit, evidence):
    from .crosscheck import NUMBER, _matches, quantities_in_text

    # Conversions are limited to dimensions already parsed independently by the
    # text checker. Relative centrifugal force and rpm are never interchanged.
    measures = {
        "mL": ("mL", 1), "uL": ("mL", .001), "\u00b5L": ("mL", .001), "\u03bcL": ("mL", .001),
        "nL": ("mL", 1e-6), "L": ("mL", 1000),
        "mg": ("mg", 1), "g": ("mg", 1000), "ug": ("mg", .001), "kg": ("mg", 1e6),
        "mmol": ("mmol", 1), "mol": ("mmol", 1000), "umol": ("mmol", .001), "nmol": ("mmol", 1e-6),
        "s": ("duration_s", 1), "min": ("duration_s", 60), "h": ("duration_s", 3600),
        "d": ("duration_s", 86400), "\u00b0C": ("temp_C", 1), "C": ("temp_C", 1),
        "rpm": ("rpm", 1), "mbar": ("pressure_mbar", 1), "nm": ("wavelength_nm", 1),
    }
    if unit in measures:
        dimension, factor = measures[unit]
        return _matches(value * factor, quantities_in_text(evidence, dimension))
    normalized = evidence.replace("\u2212", "-")
    if unit:
        pattern = rf"(?<![\w.])({NUMBER})\s*{re.escape(unit)}(?!\w)"
    else:
        pattern = rf"(?<![\w.])({NUMBER})(?![\w.])"
    return _matches(value, [float(match.group(1)) for match in re.finditer(pattern, normalized)])


def _reported_numeric(specification, evidence):
    """Do not call a parameter absent when its own cited clause gives its unit."""
    from .crosscheck import NUMBER, quantities_in_text
    dimensions = {"volume": "mL", "mass": "mg", "amount": "mmol", "substance": "mmol",
                  "time": "duration_s", "duration": "duration_s", "temperature": "temp_C",
                  "pressure": "pressure_mbar", "wavelength": "wavelength_nm"}
    units = {"mL": "mL", "uL": "mL", "\u00b5L": "mL", "\u03bcL": "mL", "L": "mL", "nL": "mL",
             "mg": "mg", "g": "mg", "ug": "mg", "kg": "mg", "mmol": "mmol", "mol": "mmol",
             "umol": "mmol", "nmol": "mmol", "s": "duration_s", "min": "duration_s", "h": "duration_s",
             "d": "duration_s", "C": "temp_C", "\u00b0C": "temp_C", "rpm": "rpm", "mbar": "pressure_mbar", "nm": "wavelength_nm"}
    unit = specification.get("unit")
    dimension = units.get(unit, dimensions.get(specification.get("dimension")))
    if dimension:
        return bool(quantities_in_text(evidence, dimension))
    return bool(unit and re.search(rf"({NUMBER})\s*{re.escape(unit)}(?!\w)", evidence))


def validate_extension_step(step, definition, source=None):
    """Validate one new-operation instance; known facts need literal evidence.

    Passing no source checks representation only. This is intentional for
    exported negative examples whose interventions differ from source facts.
    """
    if not isinstance(step, dict):
        raise ValueError("An extension step must be an object")
    name = step.get("op")
    normalized = normalize_definition(name, definition)
    source = _source_text(source)
    meta = step.get("meta", {})
    if not isinstance(meta, dict):
        raise ValueError("Step metadata must be an object")
    evidence = step.get("evidence", meta.get("evidence"))
    step_quote = _evidence(evidence, source, "Step evidence")
    values = step.get("parameters")
    if not isinstance(values, dict) or set(values) - set(normalized["parameters"]):
        raise ValueError("Extension parameters must match their operation contract")
    for key, specification in normalized["parameters"].items():
        if key not in values:
            if specification["required"]:
                raise ValueError("Required parameter needs a known value or missing marker: " + key)
            continue
        item = values[key]
        if not isinstance(item, dict):
            raise ValueError("Parameter must be an evidence-bearing object: " + key)
        if "status" in item or "marker" in item:
            _validate_missing(item, source)
            if item["evidence"] not in step_quote:
                raise ValueError("Parameter evidence must be contained in its step evidence")
            if (source is not None and item["status"] == "not_reported"
                    and specification["type"] in {"number", "integer", "quantity"}
                    and _reported_numeric(specification, item["evidence"])):
                raise ValueError("A source-reported numeric parameter cannot be marked not_reported: " + key)
            continue
        if set(item) - {"value", "evidence", "unit"} or "value" not in item:
            raise ValueError("Known parameter contains unsupported fields: " + key)
        quote = _evidence(item.get("evidence"), source, "Parameter evidence")
        if quote not in step_quote:
            raise ValueError("Parameter evidence must be contained in its step evidence")
        value, kind = item["value"], specification["type"]
        valid_type = ((kind in {"number", "quantity"} and _finite(value))
                      or (kind == "integer" and isinstance(value, int) and _finite(value))
                      or (kind == "boolean" and isinstance(value, bool))
                      or (kind in {"string", "reference"} and isinstance(value, str) and bool(value)))
        if not valid_type:
            raise ValueError("Parameter has an invalid " + kind + " value: " + key)
        unit = item.get("unit", specification.get("unit"))
        if "unit" in item:
            _text(unit, "Parameter unit")
            if kind not in {"number", "integer", "quantity"}:
                raise ValueError("Nonnumeric parameter cannot carry a unit: " + key)
        if kind == "quantity" and not unit:
            raise ValueError("Quantity parameter requires a unit: " + key)
        if "unit" in specification and unit != specification["unit"]:
            raise ValueError("Parameter unit disagrees with its declared contract: " + key)
        if source is not None:
            if kind in {"string", "reference"} and value not in quote:
                raise ValueError("Parameter value must occur literally in its evidence: " + key)
            if kind in {"number", "integer", "quantity"} and not _numeric_grounded(value, unit, quote):
                raise ValueError("Numeric parameter is not supported by its source number and unit: " + key)
            if kind == "boolean" and not re.search(r"\b(?:true|yes)\b" if value else r"\b(?:false|no)\b", quote, re.I):
                raise ValueError("Boolean parameter needs an explicit source boolean; preserve natural-language conditions as strings: " + key)
    if "missing_parameters" in step:
        raise ValueError("New-operation missing values belong in parameters")


def _tag(name):
    return "{" + NS + "}" + name


def _write_value(parent, value):
    """A closed typed tree preserves JSON exactly without arbitrary XML nodes."""
    if isinstance(value, dict):
        element = etree.SubElement(parent, _tag("Object"))
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("JSON object keys must be strings")
            _write_value(etree.SubElement(element, _tag("Field"), name=key), item)
    elif isinstance(value, list):
        element = etree.SubElement(parent, _tag("Array"))
        for item in value:
            _write_value(etree.SubElement(element, _tag("Item")), item)
    elif value is None:
        etree.SubElement(parent, _tag("Null"))
    elif isinstance(value, bool):
        etree.SubElement(parent, _tag("Boolean")).text = "true" if value else "false"
    elif _finite(value):
        etree.SubElement(parent, _tag("Number")).text = json.dumps(value, allow_nan=False)
    elif isinstance(value, str):
        etree.SubElement(parent, _tag("String")).text = value
    else:
        raise ValueError("Only finite JSON values can be serialized")


def _shape(element, name, attributes=()):
    if element.tag != _tag(name) or set(element.attrib) != set(attributes):
        raise ValueError("Unexpected extension element or attributes: " + str(element.tag))
    if element.tail and element.tail.strip():
        raise ValueError("Unexpected text after extension element")


def _read_value(parent):
    if len(parent) != 1 or (parent.text and parent.text.strip()):
        raise ValueError("A typed field must contain exactly one value")
    element = parent[0]
    if element.attrib or (element.tail and element.tail.strip()):
        raise ValueError("Typed values cannot have attributes or trailing text")
    name = etree.QName(element).localname
    if element.tag != _tag(name):
        raise ValueError("Typed values require the extension namespace")
    if name in {"Object", "Array"}:
        if element.text and element.text.strip():
            raise ValueError("Containers cannot have text content")
        result = {} if name == "Object" else []
        for child in element:
            _shape(child, "Field" if name == "Object" else "Item", ("name",) if name == "Object" else ())
            value = _read_value(child)
            if name == "Object":
                key = child.get("name")
                if key in result:
                    raise ValueError("Duplicate JSON field: " + key)
                result[key] = value
            else:
                result.append(value)
        return result
    if len(element):
        raise ValueError("Scalar typed values cannot contain child nodes")
    text = element.text or ""
    if name == "String":
        return text
    if name == "Null" and not text:
        return None
    if name == "Boolean" and text in {"true", "false"}:
        return text == "true"
    if name == "Number":
        try:
            value = json.loads(text)
        except (ValueError, TypeError) as error:
            raise ValueError("Invalid JSON number") from error
        if _finite(value):
            return value
    raise ValueError("Invalid typed value: " + name)


def _validate_steps(steps, definitions):
    if not isinstance(steps, list) or not steps:
        raise ValueError("Extended XDL needs a nonempty steps array")
    used_ids = set()
    for step in steps:
        if not isinstance(step, dict):
            raise ValueError("Step must be an object")
        identifier = _text(step.get("id"), "Step id")
        if identifier in used_ids:
            raise ValueError("Duplicate step id: " + identifier)
        used_ids.add(identifier)
        operation = step.get("op")
        if operation in definitions:
            validate_extension_step(step, definitions[operation])
        elif operation not in _core_operations():
            raise ValueError("Operation has no embedded contract: " + str(operation))
        missing = step.get("missing_parameters", {})
        if not isinstance(missing, dict):
            raise ValueError("Missing parameters must be an object")
        for field, marker in missing.items():
            if not isinstance(field, str) or not _IDENTIFIER.fullmatch(field):
                raise ValueError("Missing parameter name must be an identifier")
            if operation in _core_operations():
                from .extract import STEP_FIELDS
                contract = _core_operations()[operation]
                permitted = set(contract["required"]) | set(contract.get("optional", [])) | STEP_FIELDS.get(operation, set())
                if field not in permitted:
                    raise ValueError("Missing parameter is not declared by its core operation: " + field)
            _validate_missing(marker)
            if field in step:
                raise ValueError("A parameter cannot be both known and missing: " + field)


def export_extended_xdl(protocol):
    """Export the self-describing MOSAIC profile, preserving each step field."""
    definitions = protocol.get("operation_definitions", {})
    if not isinstance(definitions, dict):
        raise ValueError("Operation definitions must be an object")
    for name, definition in definitions.items():
        normalize_definition(name, definition)
    steps = protocol.get("steps")
    _validate_steps(steps, definitions)
    root = etree.Element("Synthesis", nsmap={"mx": NS})
    root.set(_tag("profile"), PROFILE)
    metadata = etree.SubElement(root, "Metadata", description="Source-grounded extended XDL representation; hardware execution is not certified.")
    facts = {key: copy.deepcopy(protocol[key]) for key in
             ("context", "initial_contents", "representation_scope", "source_text") if key in protocol}
    _write_value(etree.SubElement(metadata, _tag("Data")), facts)
    for tag, value in (("Hardware", protocol.get("hardware", {})), ("Reagents", protocol.get("reagents", []))):
        section = etree.SubElement(root, tag)
        _write_value(etree.SubElement(section, _tag("Data")), value)
    library = etree.SubElement(root, _tag("OperationDefinitions"))
    for name, definition in sorted(definitions.items()):
        entry = etree.SubElement(library, _tag("Definition"), name=name,
                                 semantic_sha256=definition_semantic_hash(name, definition))
        _write_value(entry, definition)
    procedure = etree.SubElement(root, "Procedure")
    for step in steps:
        entry = etree.SubElement(procedure, _tag("Step"), operation=step["op"], id=step["id"])
        _write_value(entry, step)
    return etree.tostring(root, encoding="unicode", pretty_print=True)


def read_extended_xdl(xml):
    """Read and validate the closed extension grammar, returning lossless records."""
    parser = etree.XMLParser(resolve_entities=False, no_network=True, remove_comments=False)
    try:
        root = etree.fromstring(xml.encode("utf-8") if isinstance(xml, str) else xml, parser)
    except (ValueError, TypeError, etree.XMLSyntaxError) as error:
        raise ValueError("Invalid extended XDL XML") from error
    if root.getroottree().docinfo.doctype:
        raise ValueError("DOCTYPE is not allowed")
    if root.tag != "Synthesis" or dict(root.attrib) != {_tag("profile"): PROFILE}:
        raise ValueError("Extended XDL needs the explicit MOSAIC profile on Synthesis")
    expected = ["Metadata", "Hardware", "Reagents", _tag("OperationDefinitions"), "Procedure"]
    if [child.tag for child in root] != expected or (root.text and root.text.strip()):
        raise ValueError("Unexpected extended XDL document structure")
    if any(child.tail and child.tail.strip() for child in root):
        raise ValueError("Unexpected text between extended XDL sections")
    metadata, hardware, reagents, library, procedure = root
    if set(metadata.attrib) != {"description"} or len(metadata) != 1 or (metadata.text and metadata.text.strip()):
        raise ValueError("Unexpected extended XDL metadata")
    _shape(metadata[0], "Data")
    facts = _read_value(metadata[0])
    if not isinstance(facts, dict) or set(facts) - {"context", "initial_contents", "representation_scope", "source_text"}:
        raise ValueError("Unexpected extended XDL metadata fields")
    for key, value in facts.items():
        if not isinstance(value, dict if key in {"context", "initial_contents"} else str):
            raise ValueError("Invalid extended XDL metadata value: " + key)
    for section, kind in ((hardware, dict), (reagents, list)):
        if section.attrib or len(section) != 1 or (section.text and section.text.strip()):
            raise ValueError("Unexpected hardware or reagent section")
        _shape(section[0], "Data")
        if not isinstance(_read_value(section[0]), kind):
            raise ValueError("Hardware and reagent sections have the wrong data type")
    _shape(library, "OperationDefinitions")
    if library.text and library.text.strip():
        raise ValueError("Unexpected text in operation definitions")
    definitions = {}
    for entry in library:
        _shape(entry, "Definition", ("name", "semantic_sha256"))
        name = entry.get("name")
        if name in definitions:
            raise ValueError("Duplicate operation definition: " + name)
        definition = _read_value(entry)
        normalize_definition(name, definition)
        if entry.get("semantic_sha256") != definition_semantic_hash(name, definition):
            raise ValueError("Embedded operation contract hash mismatch")
        definitions[name] = definition
    if procedure.attrib or (procedure.text and procedure.text.strip()):
        raise ValueError("Unexpected procedure attributes or text")
    steps = []
    for entry in procedure:
        _shape(entry, "Step", ("operation", "id"))
        step = _read_value(entry)
        if not isinstance(step, dict) or entry.get("operation") != step.get("op") or entry.get("id") != step.get("id"):
            raise ValueError("Step attributes disagree with its embedded record")
        steps.append(step)
    _validate_steps(steps, definitions)
    return {"steps": steps, "operation_definitions": definitions}


def validate_extended_xdl(xml):
    read_extended_xdl(xml)
    return True
