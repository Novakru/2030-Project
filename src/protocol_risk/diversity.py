"""Deterministic, inspectable selection; numeric perturbations are not new mechanisms."""
from __future__ import annotations

import re
from collections import Counter

from .io import digest


def features(sample, parent=None):
    protocol = sample.get("protocol", {})
    parent = parent or protocol
    evidence = sample.get("label", {}).get("evidence", [])
    evidence = evidence if isinstance(evidence, list) else [evidence]
    rules = sorted({e.get("rule_id") or e.get("precondition", "") for e in evidence if isinstance(e, dict)} - {""})
    paths = []
    changed_operations = set()
    reagent_roles = {r["id"]: r.get("role") for r in parent.get("reagents", [])}
    for patch in sample.get("diff", []):
        path = patch.get("path", "")
        if not path.startswith(("/steps/", "/reagents/", "/hardware/", "/context/", "/initial_contents/")):
            continue
        paths.append((patch["op"], re.sub(r"/\d+(?=/|$)", "/*", path)))
        match = re.match(r"/steps/(\d+)(?:/|$)", path)
        if match and int(match[1]) < len(parent.get("steps", [])):
            step = parent["steps"][int(match[1])]
            changed_operations.add((step["op"], reagent_roles.get(step.get("reagent")) or ""))
    sequence = []
    for step in parent.get("steps", []):
        if not sequence or sequence[-1] != step["op"]:
            sequence.append(step["op"])
    vessel = parent.get("hardware", {}).get("nodes", {}).get("reactor", {})
    source = sample.get("source", {})
    return {"parent": sample.get("parent_id"), "source_dataset": source.get("dataset_id") or source.get("url"),
            "reaction": sample.get("reaction_smiles") or None, "reaction_class": parent.get("reaction_class"),
            "device_family": vessel.get("apparatus_kind") or vessel.get("category"),
            "flow_template": digest(sequence)[:16] if sequence else None,
            "mechanism": digest({"rules": rules, "edits": sorted(set(paths)), "targets": sorted(changed_operations)})[:16] if rules or paths else None}


def summarize(samples, parents=None):
    parents = parents or {}
    rows = [features(s, parents.get(s.get("parent_id"))) for s in samples]
    dimensions = ("parent", "source_dataset", "reaction", "reaction_class", "device_family", "flow_template", "mechanism")
    result = {"count": len(rows)}
    for key in dimensions:
        counts = Counter(r[key] for r in rows if r[key])
        result[key] = {"unique": len(counts), "missing": sum(not r[key] for r in rows),
                       "largest_group": max(counts.values(), default=0)}
    result["limitations"] = [key + "_has_one_observed_group" for key in ("source_dataset", "device_family", "flow_template", "mechanism")
                              if result[key]["unique"] <= 1 and rows]
    return result


def select_diverse(candidates, limit, parents=None):
    """One fresh parent first, then fault/source/apparatus/flow novelty and balance."""
    parents = parents or {}
    remaining = sorted(candidates, key=lambda s: s["id"])
    profiles = {s["id"]: features(s, parents.get(s.get("parent_id"))) for s in remaining}
    counts = {k: Counter() for k in ("parent", "mechanism", "source_dataset", "device_family", "flow_template", "reaction_class", "reaction")}
    selected = []
    while remaining and len(selected) < max(0, limit):
        def score(sample):
            f = profiles[sample["id"]]
            fresh = tuple(int(bool(f[k]) and not counts[k][f[k]]) for k in counts)
            balance = tuple(-counts[k][f[k]] if f[k] else -len(candidates) for k in ("source_dataset", "parent", "mechanism", "device_family", "flow_template"))
            return fresh + balance
        best = max(remaining, key=score)
        remaining.remove(best)
        selected.append(best)
        for key in counts:
            value = profiles[best["id"]][key]
            if value:
                counts[key][value] += 1
    return selected
