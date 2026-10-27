"""Pinned SOP fragments and native author XDL, with separate evidence contracts."""
from __future__ import annotations

import copy
from collections import Counter

import jsonpatch

from protocol_risk.io import ROOT, digest, read_json, read_jsonl
from protocol_risk.mutation_rules import make_negative
from protocol_risk.native import _graph, material_contracts, missing_input, remove_statement
from protocol_risk.sop import candidates
from protocol_risk.xdl import canonical_hash, export_xdl

from .mutations import assess_intervention, fault_instances
from protocol_risk.symbolic import evaluate


def source_paths():
    paths = [ROOT / "data/publications/chemputer_2022.jsonl", ROOT / "data/sop_sources.lock.json"]
    for origin in read_jsonl(paths[0]):
        paths.append(ROOT / origin["raw_xdl_path"])
        paths.extend(ROOT / r["path"] for r in origin["resources"] if r["path"].endswith(".json"))
    for source in read_json(paths[1])["sources"]:
        paths.extend(ROOT / source[key] for key in ("path", "text_path") if source.get(key))
    return sorted(set(paths))


def _sop_pairs(run_id):
    for original, risk, child in candidates():
        parent = copy.deepcopy(original)
        parent["id"] = "mosaic_sop_" + digest({"run": run_id, "parent": original})[:20]
        child["id"] = parent["id"]
        parent["xdl"] = export_xdl(parent)
        parent["canonical_sha1"] = canonical_hash(parent)
        child["xdl"] = export_xdl(child)
        intervention = assess_intervention(parent, child)
        sample = make_negative(parent, child, risk, parent.get("source_evidence", parent["construction"]), origin=parent["origin"])
        if not sample:
            raise ValueError("SOP intervention failed its domain checks")
        sample["id"] = "mosaic_" + sample["id"]
        sample["xdl"] = sample["protocol"]["xdl"]
        sample["mutation"].update(intervention=intervention, semantic_fault_count_verified=True,
            fault_instances=fault_instances(sample["protocol"], evaluate(sample["protocol"]).violations),
            mechanism_id={"B2": "B2.below_pure_solvent_melting_point", "B3": "B3.exposed_vapor_ignition_source",
                          "B5": "B5.water_into_concentrated_acid"}[risk])
        sample["benchmark_eligible"] = False
        sample["source_kind"] = parent["construction"]["kind"]
        sample["label"]["scope"] = "Source fragment or explicitly constructed scenario only; not an observed failed experiment."
        yield parent, sample


def _native_pairs(run_id):
    for origin in read_jsonl(ROOT / "data/publications/chemputer_2022.jsonl"):
        if origin["source_partition"] != "successful_reactions":
            continue
        graph, resource = _graph(origin)
        if graph is None:
            continue
        payload = (ROOT / origin["raw_xdl_path"]).read_bytes()
        source_hash = next(r["sha256"] for r in origin["resources"] if r["path"] == origin["raw_xdl_path"])
        if digest(payload) != source_hash:
            raise ValueError("Native author XDL source checksum mismatch")
        xml = payload.decode("utf-8")
        for contract in material_contracts(xml, graph):
            child = remove_statement(xml, contract["producer_xpath"])
            if missing_input(xml, contract) or not missing_input(child, contract):
                raise ValueError("Native material-flow contract did not replay")
            identifier = "mosaic_native_" + digest({"run": run_id, "source": origin["id"]})[:20]
            parent = {"id": identifier, "source": origin["source"], "source_partition": origin["source_partition"],
                "raw_id": origin["id"], "raw_sha256": source_hash, "format": "native_author_xdl",
                "xdl": xml, "hardware": graph, "graph_sha256": resource["sha256"],
                "quality": {"tier": "silver", "manual_review": "pending", "full_feasibility_certified": False,
                            "scope": "Author-reported successful partition; only the stated material-input contract is checked."}}
            changed = copy.deepcopy(parent)
            changed["xdl"] = child
            patch = jsonpatch.make_patch(parent, changed).patch
            sample = {"id": "mosaic_neg_D2_" + digest({"parent": identifier, "patch": patch})[:20],
                "parent_id": identifier, "source": origin["source"], "origin": "published_source",
                "format": "native_author_xdl", "protocol": changed, "xdl": child, "diff": patch,
                "contract": contract, "parent_xdl_sha256": source_hash,
                "graph_sha256": resource["sha256"], "benchmark_eligible": False,
                "mutation": {"risk": "D2", "semantic_fault_count": 1, "semantic_fault_count_verified": True,
                             "mechanism_id": "D2.omitted_" + material_contracts_operation(xml, contract),
                             "operation": "remove_statement", "intervention": {"count": 1, "kind": "remove_native_statement"}},
                "audit": {"parent_risks": [], "child_risks": ["D2"], "replay_exact": True},
                "label": {"risk_l1": "D", "risk_l2": "D2", "label_type": "hard", "feasible": False,
                          "p_infeasible": 1.0, "judge": "native_material_flow", "scope": "Sole material-input dependency only; other chemistry and hardware constraints remain unchecked."}}
            yield parent, sample
            break


def material_contracts_operation(xml, contract):
    from protocol_risk.native import parse
    return parse(xml).xpath(contract["producer_xpath"])[0].tag.lower()


def build_supplements(run_id, per_risk):
    parents, negatives, counts, seen = {}, [], Counter(), set()
    pairs = list(_sop_pairs(run_id)) + list(_native_pairs(run_id))
    mechanism_counts, parent_counts, ranked = Counter(), Counter(), []
    for parent, sample in pairs:
        mechanism = sample["mutation"]["mechanism_id"]
        ranked.append((mechanism_counts[mechanism], parent_counts[parent["id"]], mechanism, parent, sample))
        mechanism_counts[mechanism] += 1
        parent_counts[parent["id"]] += 1
    for _, _, _, parent, sample in sorted(ranked, key=lambda row: row[:3]):
        risk = sample["label"]["risk_l2"]
        if counts[risk] >= per_risk:
            continue
        key = digest({"xdl": sample["xdl"], "risk": risk})
        if key in seen:
            continue
        seen.add(key)
        parent["record_type"], sample["record_type"] = "positive", "negative"
        parent.setdefault("split_group", "source:" + str(parent["source"].get("id", parent.get("raw_id"))))
        value = int(digest(parent["split_group"])[:8], 16) % 100
        parent["split"] = "train" if value < 70 else "val" if value < 85 else "test"
        sample["split"], sample["split_group"] = parent["split"], parent["split_group"]
        sample["protocol"].update(record_type="positive", split=parent["split"], split_group=parent["split_group"])
        sample["diff"] = jsonpatch.make_patch(parent, sample["protocol"]).patch
        parents[parent["id"]] = parent
        negatives.append(sample)
        counts[risk] += 1
    return {"parents": list(parents.values()), "negatives": negatives,
            "counts": dict(counts), "policy": "SOP scenarios and native material contracts are separate evidence partitions, never ORD reaction counts."}
