"""Lossless XML for canonical concepts, evidence and explicit timing relations."""
from lxml import etree

from .extensions import NS, _read_value, _shape, _tag, _write_value

PROFILE = "mosaic-canonical/1"
METADATA = ("context", "initial_contents", "representation_scope", "source_text",
            "normalization", "temporal_relations", "temporal_groups")


def export_canonical_xdl(protocol):
    from .normalization import semantic_contract_hash, validate_normalized
    validate_normalized(protocol)
    root = etree.Element("Synthesis", nsmap={"mx": NS})
    root.set(_tag("profile"), PROFILE)
    metadata = etree.SubElement(root, "Metadata")
    _write_value(etree.SubElement(metadata, _tag("Data")),
                 {key: protocol[key] for key in METADATA if key in protocol})
    for tag, value in (("Hardware", protocol.get("hardware", {})), ("Reagents", protocol.get("reagents", []))):
        _write_value(etree.SubElement(etree.SubElement(root, tag), _tag("Data")), value)
    definitions = etree.SubElement(root, _tag("OperationDefinitions"))
    for name, contract in sorted(protocol.get("operation_definitions", {}).items()):
        node = etree.SubElement(definitions, _tag("Definition"), name=name,
                                semantic_sha256=semantic_contract_hash(contract))
        _write_value(node, contract)
    steps = etree.SubElement(root, "Procedure")
    for step in protocol["steps"]:
        _write_value(etree.SubElement(steps, _tag("Step"), id=step["id"], operation=step["op"]), step)
    return etree.tostring(root, encoding="unicode", pretty_print=True)


def read_canonical_xdl(xml):
    from .normalization import semantic_contract_hash, validate_normalized
    parser = etree.XMLParser(resolve_entities=False, no_network=True)
    try:
        root = etree.fromstring(xml.encode("utf-8") if isinstance(xml, str) else xml, parser)
    except (ValueError, TypeError, etree.XMLSyntaxError) as error:
        raise ValueError("Invalid canonical XML") from error
    if root.getroottree().docinfo.doctype:
        raise ValueError("DOCTYPE is not allowed")
    if root.tag != "Synthesis" or dict(root.attrib) != {_tag("profile"): PROFILE}:
        raise ValueError("Canonical XML requires its explicit profile")
    expected = ["Metadata", "Hardware", "Reagents", _tag("OperationDefinitions"), "Procedure"]
    if [c.tag for c in root] != expected or (root.text and root.text.strip()):
        raise ValueError("Unexpected canonical XML structure")
    if any(c.tail and c.tail.strip() for c in root):
        raise ValueError("Unexpected XML text")
    protocol = {"xdl_profile": PROFILE}
    for node, section in zip(root[:3], ("Metadata", "Hardware", "Reagents")):
        if node.attrib or len(node) != 1 or node[0].tag != _tag("Data"):
            raise ValueError("Invalid canonical " + section)
        _shape(node[0], "Data")
        value = _read_value(node[0])
        if section == "Metadata":
            if not isinstance(value, dict) or set(value) - set(METADATA):
                raise ValueError("Unexpected canonical metadata")
            protocol.update(value)
        else:
            protocol[section.lower()] = value
    definitions = {}
    if root[3].attrib or (root[3].text and root[3].text.strip()):
        raise ValueError("Invalid canonical definitions")
    for node in root[3]:
        _shape(node, "Definition", ("name", "semantic_sha256"))
        name = node.get("name")
        contract = _read_value(node)
        if name in definitions or semantic_contract_hash(contract) != node.get("semantic_sha256"):
            raise ValueError("Duplicate or modified canonical contract")
        definitions[name] = contract
    protocol["operation_definitions"] = definitions
    if root[4].attrib or (root[4].text and root[4].text.strip()):
        raise ValueError("Invalid canonical procedure")
    protocol["steps"] = []
    for node in root[4]:
        _shape(node, "Step", ("id", "operation"))
        step = _read_value(node)
        if not isinstance(step, dict) or step.get("id") != node.get("id") or step.get("op") != node.get("operation"):
            raise ValueError("Canonical step disagrees with XML attributes")
        protocol["steps"].append(step)
    validate_normalized(protocol)
    return protocol


def validate_canonical_xdl(xml):
    read_canonical_xdl(xml)
    return True
