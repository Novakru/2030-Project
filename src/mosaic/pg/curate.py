"""Batch-level library maintenance (operations and equipment).

1. ``collect``  scans results: op="other" labels and equipment names, with counts and example sentences.
2. ``propose``  one LLM call per batch maps labels to existing ops (alias) or proposes a new op contract.
3. ``apply``    deterministic gate: aliases must target an existing op; new ops must have a valid role
               contract and a name that does not collide. Accepted entries go to ops.local.yaml, which
               the extractor loads on the next run (``--ops-extra``). Graphs are never rewritten here.
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import yaml

from .ir import load_ops
from .prompts import CURATOR_SYSTEM

ROLE_VALUES = {"required", "optional", "none"}


def collect(results):
    ops, equipment = defaultdict(list), Counter()
    for r in results.values():
        g = r.get("graph")
        if not g:
            continue
        sents = {s["id"]: s["text"] for s in r.get("prepared", {}).get("sentences", [])}
        for s in g["steps"]:
            if s["op"] == "other":
                label = (s["op_label"] or "unknown").lower().strip()
                ops[label].append({"source": r["source_id"], "surface": s["surface"],
                                   "sentence": " ".join(sents.get(x, "") for x in s["sentences"])[:300]})
        for e in g["equipment"]:
            equipment[re.sub(r"\s+", " ", e["name"].lower())] += 1
    return {"ops": {k: {"count": len(v), "examples": v[:3]} for k, v in sorted(ops.items(), key=lambda x: -len(x[1]))},
            "equipment": dict(equipment.most_common())}


def propose(queue, llm, ops_extra=None):
    if not queue["ops"]:
        return {"decisions": []}
    library = {k: v["desc"] for k, v in load_ops(ops_extra)["ops"].items()}
    user = "LIBRARY:\n" + json.dumps(library, ensure_ascii=False) + "\n\nUNMAPPED:\n" + json.dumps(queue["ops"], ensure_ascii=False)
    reply, _ = llm.json("curator", CURATOR_SYSTEM, user + "\n\nJSON:")
    return reply


def apply(decisions, ops_local_path):
    path = Path(ops_local_path)
    local = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
    local = local or {}
    local.setdefault("ops", {})
    lib = load_ops(str(path) if path.exists() else None)
    accepted, rejected = [], []
    for d in decisions.get("decisions", []):
        label = str(d.get("label", "")).strip()
        if d.get("decision") == "alias":
            op = d.get("op")
            if op in lib["ops"] and op != "other":
                local["ops"].setdefault(op, dict(lib["ops"][op]))
                aliases = set(local["ops"][op].get("aliases") or []) | {label}
                local["ops"][op]["aliases"] = sorted(aliases)
                accepted.append({"label": label, "alias_of": op})
            else:
                rejected.append({"label": label, "reason": f"alias target {op!r} not in library"})
        elif d.get("decision") == "new":
            spec, name = d.get("spec") or {}, re.sub(r"\W+", "_", str(d.get("op", "")).lower()).strip("_")
            ok = (name and name not in lib["ops"] and spec.get("target") in ROLE_VALUES and spec.get("inputs") in ROLE_VALUES
                  and isinstance(spec.get("outputs", []), list) and spec.get("desc"))
            if ok:
                local["ops"][name] = {"desc": spec["desc"], "target": spec["target"], "inputs": spec["inputs"],
                                      "outputs": spec.get("outputs") or ["main"], "params": spec.get("params") or [],
                                      "xdl": None, "aliases": [label], "status": "silver_needs_review"}
                accepted.append({"label": label, "new_op": name})
            else:
                rejected.append({"label": label, "reason": "invalid or colliding new-op contract"})
    path.write_text(yaml.safe_dump(local, allow_unicode=True, sort_keys=False), encoding="utf-8")
    load_ops.cache_clear()
    return {"accepted": accepted, "rejected": rejected, "path": str(path)}
