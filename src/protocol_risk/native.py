"""Single missing material-transfer statements in published, native author XDL."""
from __future__ import annotations


from lxml import etree

from .io import ROOT, digest, read_json


def parse(xml):
    tree = etree.fromstring(xml.encode("utf-8"), etree.XMLParser(resolve_entities=False, no_network=True)).getroottree()
    if tree.docinfo.doctype:
        raise ValueError("DOCTYPE is not allowed")
    return tree


def writes_to(step, vessel):
    return (step.get("to_vessel") == vessel or step.get("filtrate_vessel") == vessel
            or step.tag in ("Add", "AddSolid", "Dissolve") and step.get("vessel") == vessel)


def material_contracts(xml, graph):
    tree = parse(xml)
    if tree.xpath("//Procedure//Async"):
        return []  # A linear scan cannot certify asynchronous execution order.
    nodes = {n["id"]: n for n in graph.get("nodes", [])}
    steps = tree.xpath("//Procedure//*[not(*)]")
    contracts = []
    for index, producer in enumerate(steps):
        if producer.tag not in ("Transfer", "FilterThrough") or producer.getparent().tag not in ("Procedure", "Workup"):
            continue
        vessel = producer.get("to_vessel")
        if nodes.get(vessel, {}).get("current_volume") != 0:
            continue
        writers = [s for s in steps if writes_to(s, vessel)]
        consumers = [s for s in steps[index + 1:] if s.tag == "Evaporate" and s.get("vessel") == vessel]
        if len(writers) == 1 and consumers:
            contracts.append({"vessel": vessel, "producer_xpath": tree.getpath(producer),
                              "consumer_xpath": tree.getpath(consumers[0]), "initial_volume": 0,
                              "basis": "Source graph declares an empty vessel; this is its sole material-input statement before evaporation."})
    return contracts


def missing_input(xml, contract):
    tree = parse(xml)
    consumers = tree.xpath(contract["consumer_xpath"])
    return bool(consumers and not any(writes_to(s, contract["vessel"]) for s in tree.xpath("//Procedure//*[not(*)]")))


def remove_statement(xml, xpath):
    tree = parse(xml)
    selected = tree.xpath(xpath)
    if len(selected) != 1:
        raise ValueError("Expected one uniquely identified source statement")
    selected[0].getparent().remove(selected[0])
    return etree.tostring(tree, encoding="unicode")


def _graph(origin):
    choices = []
    for resource in origin["resources"]:
        if resource["path"].endswith(".json"):
            value = read_json(ROOT / resource["path"])
            if isinstance(value, dict) and isinstance(value.get("nodes"), list):
                if digest((ROOT / resource["path"]).read_bytes()) != resource["sha256"]:
                    raise ValueError("Source hardware graph checksum mismatch")
                choices.append((value, resource))
    return choices[0] if len(choices) == 1 else (None, None)
