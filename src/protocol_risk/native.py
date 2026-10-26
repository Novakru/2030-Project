"""Single missing material-transfer statements in published, native author XDL."""
from __future__ import annotations

from collections import Counter

import jsonpatch
from lxml import etree

from .io import ROOT, digest, read_json, read_jsonl, write_json, write_jsonl


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


def build_native_negatives(per_risk=12):
    origins = {r["id"]: r for r in read_jsonl(ROOT / "data/publications/chemputer_2022.jsonl")}
    output, seen = [], set()
    for parent in read_jsonl(ROOT / "data/publications/candidates.jsonl"):
        if parent["source_partition"] != "successful_reactions" or parent["id"] not in origins:
            continue
        graph, resource = _graph(origins[parent["id"]])
        if graph is None:
            continue
        xml = (ROOT / parent["xdl_path"]).read_bytes().decode("utf-8")
        if digest(xml.encode("utf-8")) != parent["xdl_sha256"]:
            raise ValueError("Prepared author XDL checksum mismatch")
        for contract in material_contracts(xml, graph):
            child = remove_statement(xml, contract["producer_xpath"])
            if not missing_input(child, contract) or missing_input(xml, contract):
                continue
            fingerprint = digest(etree.tostring(parse(child), method="c14n", with_comments=False))
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            identifier = "neg_D2_native_" + digest({"parent": parent["id"], "contract": contract})[:16]
            target = ROOT / "data/xdl/native_negative/D2" / (identifier + ".xdl")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(child.encode("utf-8"))
            patch = jsonpatch.make_patch({"xdl": xml}, {"xdl": child}).patch
            output.append({"id": identifier, "parent_id": parent["id"], "source": parent["source"],
                           "origin": "published_source", "format": "native_author_xdl", "source_partition": parent["source_partition"],
                           "parent_xdl_path": parent["xdl_path"], "parent_xdl_sha256": parent["xdl_sha256"],
                           "graph_path": resource["path"], "graph_sha256": resource["sha256"],
                           "xdl_path": target.relative_to(ROOT).as_posix(), "xdl": child, "diff": patch,
                           "contract": contract, "mutation": {"semantic_fault_count": 1, "operation": "remove_statement"},
                           "benchmark_eligible": False,
                           "label": {"risk_l1": "D", "risk_l2": "D2", "label_type": "hard", "feasible": False,
                                     "p_infeasible": 1.0, "judge": "native_material_flow",
                                     "scope": "Sole material-input dependency only; other native chemistry/hardware constraints are not certified."}})
            break  # Distinct original programs, rather than many edits to one program.
        if len(output) >= per_risk:
            break
    write_jsonl(ROOT / "data/native_negatives.jsonl", output)
    folder = (ROOT / "data/xdl/native_negative/D2").resolve()
    expected = {row["id"] + ".xdl" for row in output}
    for path in folder.glob("neg_D2_native_*.xdl"):
        if path.name not in expected and path.is_file() and path.resolve().is_relative_to(folder):
            path.unlink()
    summary = {"source_derived_negatives": len(output), "risk_counts": dict(Counter(r["label"]["risk_l2"] for r in output)),
               "source_partitions": dict(Counter(r["source_partition"] for r in output)), "benchmark_eligible": 0,
               "scope": "Published native XDL and source-graph material-input contracts; separate from ORD IR checks."}
    write_json(ROOT / "reports/native_negatives.json", summary)
    return summary


def audit_native_negatives():
    failures = []
    rows = list(read_jsonl(ROOT / "data/native_negatives.jsonl"))
    parents = {r["id"]: r for r in read_jsonl(ROOT / "data/publications/candidates.jsonl")}
    origins = {r["id"]: r for r in read_jsonl(ROOT / "data/publications/chemputer_2022.jsonl")}
    seen, seen_parents = set(), set()
    for row in rows:
        if row["id"] in seen or row["parent_id"] in seen_parents:
            failures.append("duplicate_native_example:" + row["id"])
        seen.add(row["id"])
        seen_parents.add(row["parent_id"])
        parent = parents.get(row["parent_id"])
        if not parent or parent["source_partition"] != "successful_reactions":
            failures.append("invalid_parent:" + row["id"])
            continue
        xml = (ROOT / parent["xdl_path"]).read_bytes().decode("utf-8")
        graph_path = ROOT / row["graph_path"]
        _, resource = _graph(origins[row["parent_id"]])
        if (resource is None or resource["path"] != row["graph_path"] or resource["sha256"] != row["graph_sha256"]
                or row["source"] != parent["source"] or row["parent_xdl_sha256"] != parent["xdl_sha256"]
                or digest(xml.encode("utf-8")) != row["parent_xdl_sha256"] or digest(graph_path.read_bytes()) != row["graph_sha256"]):
            failures.append("source_checksum:" + row["id"])
        elif row["contract"] not in material_contracts(xml, read_json(graph_path)):
            failures.append("unsupported_contract:" + row["id"])
        if (jsonpatch.apply_patch({"xdl": xml}, row["diff"]) != {"xdl": row["xdl"]}
                or remove_statement(xml, row["contract"]["producer_xpath"]) != row["xdl"]
                or (ROOT / row["xdl_path"]).read_bytes().decode("utf-8") != row["xdl"]):
            failures.append("single_statement_replay:" + row["id"])
        if (missing_input(xml, row["contract"]) or not missing_input(row["xdl"], row["contract"]) or row["benchmark_eligible"]
                or row["label"]["risk_l2"] != "D2" or row["mutation"]["semantic_fault_count"] != 1):
            failures.append("wrong_target_or_admission:" + row["id"])
    result = {"passed": not failures, "records_checked": len(rows), "failures": failures}
    write_json(ROOT / "reports/native_negatives_audit.json", result)
    return result
