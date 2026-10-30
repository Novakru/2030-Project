"""Independent reader for conventional XDL and declared operation extensions."""
import re
from lxml import etree
from .io import load_library


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
                    pool = reagents if key in {"reagent", "solvent", "eluting_solvent", "rinsing_solvent"} else components if key in {"vessel", "from_vessel", "to_vessel", "filtrate_vessel", "separation_vessel", "column"} else None
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
