"""Deterministic offline assembly from immutable sources and extraction snapshots."""
from __future__ import annotations

import copy
import re
from collections import Counter, defaultdict, deque
from pathlib import Path

from .conditions import SuccessIndex
from .controls import generate_controls
from .crosscheck import crosscheck
from .extract import structured_plan
from .ingest import read_raw
from .io import ROOT, digest, load_library, read_json, write_json, write_jsonl
from .perturb import generate_observed
from .symbolic import evaluate
from .xdl import PROFILE, bind_hardware, canonical_hash, export_xdl, validate_xdl


def annotate_dependencies(protocol):
    reagent_roles = {r["id"]: r.get("role") for r in protocol["reagents"]}
    charged = []
    for step in protocol["steps"]:
        if step["op"] == "Add" and reagent_roles.get(step["reagent"]) in ("REACTANT", "SOLVENT"):
            charged.append(step["id"])
        if step["op"] == "HeatChill" and step.get("duration_s") and charged:
            step["requires"] = list(charged)
    return protocol


def _prepare(protocol, raw, reviews=None, devices=None):
    protocol = copy.deepcopy(protocol)
    if raw.get("yield_percent") is None or raw["yield_percent"] <= 30:
        raise ValueError("source has no unambiguous target yield above 30%")
    # Extraction snapshots preserve source text, but may predate label-policy fixes.
    protocol["yield_percent"] = raw["yield_percent"]
    protocol["yield_evidence"] = copy.deepcopy(raw["yield_evidence"])
    protocol.setdefault("context", {})["atmosphere"] = raw["atmosphere"]
    for step in protocol["steps"]:
        evidence = step.get("meta", {}).get("evidence", "")
        bound = re.search(r"maximum\s+temperature(?:\s+of)?\s*([-+]?\d+(?:\.\d+)?)\s*(?:(?:°|º|o)\s*)?C\b", evidence, re.I)
        if step["op"] == "Evaporate" and "temp_C" in step and bound and abs(float(bound[1]) - step["temp_C"]) < 1e-6:
            step.setdefault("meta", {})["temp_upper_bound_C"] = step.pop("temp_C")
            step["meta"]["normalization"] = "source upper bound retained as a constraint, not an invented setpoint"
    if raw.get("raw", {}).get("notes", {}).get("is_sensitive_to_oxygen") is True:
        protocol["context"]["inert_required"] = {"basis": "ORD.notes.is_sensitive_to_oxygen", "source_url": raw["source"]["url"]}
    if protocol["extraction"]["method"] == "llm_evidence_constrained":
        pending, observations, events = [], [], []
        for action in protocol["extraction"].get("unmapped_actions", []):
            evidence = action.get("evidence", "") if isinstance(action, dict) else str(action)
            # Analytical results do not become synthesis steps. Classify explicitly and keep the source text.
            physical = re.search(r"\b(add(?:ed|ition)?|wash(?:ed)?|extract(?:ed)?|dri(?:ed|ng)|quench(?:ed)?|filter(?:ed)?|heat(?:ed)?|stirr?ed|cool(?:ed)?|chromatograph\w*|remov(?:ed|al))\b", evidence, re.I)
            analytical = re.search(r"NMR|TLC|GC/MS|GC.?MS|\byield\b|\bisomer\b|\banalys\w*", evidence, re.I)
            if analytical and not physical:
                observations.append(action)
            elif re.search(r"\bcapped\b|\bsealed\b", evidence, re.I) and protocol["context"].get("pressure_control") == "SEALED":
                events.append({"kind": "vessel_sealed", "evidence": evidence})
            else:
                pending.append(action)
        protocol["extraction"]["analytical_observations"] = observations
        protocol["context"]["source_context_events"] = events
        protocol["extraction"]["unmapped_actions"] = pending
        if pending:
            raise ValueError("source actions not mapped; requires review")
    protocol["crosscheck"] = crosscheck(protocol, raw)
    if protocol["crosscheck"]["conflicts"]:
        raise ValueError("crosscheck: " + ";".join(protocol["crosscheck"]["conflicts"]))
    annotate_dependencies(protocol)
    bind_hardware(protocol, devices=devices, configuration=reviews.configuration(protocol["id"]) if reviews else None, raw=raw)
    check = evaluate(protocol)
    if check.risks:
        raise ValueError("symbolic violations: " + ",".join(check.risks))
    xml = export_xdl(protocol)
    validate_xdl(xml)
    protocol["xdl"] = xml
    protocol["canonical_sha1"] = canonical_hash(protocol)
    protocol["quality"] = {"tier": "silver", "source_grounded": True, "observed_yield_above_30": True,
                           "xdl_profile": PROFILE, "xdl_profile_schema_passed": True,
                           "official_platform_compiled": False, "symbolic_violations": [],
                           "unknown_constraints": check.unknowns, "manual_review": "pending",
                           "hardware_verification": "pending", "full_feasibility_certified": False}
    if reviews:
        reviews.apply(protocol)
        if protocol["quality"]["manual_review"] == "rejected":
            raise ValueError("manual_protocol_review_rejected")
    return protocol


def split_group(protocol):
    smiles = protocol.get("reaction_smiles") or ""
    try:
        from rdkit import Chem, RDLogger
        from rdkit.Chem.Scaffolds import MurckoScaffold
        RDLogger.DisableLog("rdApp.error")
        product = smiles.split(">")[-1]
        mol = Chem.MolFromSmiles(product)
        if mol:
            scaffold = MurckoScaffold.MurckoScaffoldSmiles(mol=mol)
            if scaffold:
                return "product_scaffold:" + scaffold
            return "acyclic_product:" + Chem.MolToSmiles(mol)
    except ImportError:
        pass
    return "reaction_class:" + str(protocol.get("reaction_class"))


def assign_splits(positives, negatives):
    assignments = {}
    for parent in positives:
        group = split_group(parent)
        value = int(digest(group)[:8], 16) % 100
        split = "train" if value < 70 else "val" if value < 85 else "test"
        parent["split"], parent["split_group"] = split, group
        assignments[parent["id"]] = (split, group)
    for negative in negatives:
        negative["split"], negative["split_group"] = assignments[negative["parent_id"]]


def build(limit=140, per_risk=12, output_dir=None):
    from .reviews import ReviewBook
    reviews = ReviewBook()
    devices = reviews.devices()
    data_dir = Path(output_dir).resolve() if output_dir is not None else ROOT / "data"
    if output_dir is not None and (not data_dir.is_relative_to((ROOT / "data").resolve()) or data_dir == (ROOT / "data").resolve()):
        raise ValueError("Versioned output must be a subdirectory of the workspace data directory")
    report_dir = data_dir / "reports" if output_dir is not None else ROOT / "reports"
    extracts = {p.stem: read_json(p) for p in sorted((ROOT / "data/intermediate/extractions").glob("*.json"))}
    text, structured, rejected, raw_lookup = [], defaultdict(deque), [], {}
    for raw in read_raw():
        if raw["id"] in extracts:
            try:
                prepared = _prepare(extracts[raw["id"]], raw, reviews, devices)
                text.append(prepared)
                raw_lookup[prepared["id"]] = raw
            except (ValueError, KeyError, TypeError) as error:
                rejected.append({"id": raw["id"], "method": "text", "reason": str(error)[:1000]})
        # Do not flatten special flow, electrochemical, microwave or optical operations.
        conditions = raw.get("conditions", {})
        if (not raw["temperature"] or not raw["duration"] or raw.get("yield_percent") is None
                or raw["yield_percent"] <= 30 or not raw.get("reaction_smiles")
                or any(conditions.get(k) for k in ("flow", "electrochemistry", "illumination"))
                or conditions.get("conditions_are_dynamic")
                or conditions.get("temperature", {}).get("control", {}).get("type") == "MICROWAVE"):
            continue
        if any(c["addition_order"] is None or c["amount"] is None or c["amount"]["unit"] not in ("mL", "mg", "mmol") for c in raw["components"]):
            continue
        if len(structured[raw["source"]["dataset_name"]]) >= limit * 2:
            continue
        try:
            protocol = structured_plan(raw)
            # Inert environment is context; do not invent a purge cycle.
            gas = raw["atmosphere"].get("type")
            if gas in ("NITROGEN", "ARGON"):
                protocol["steps"].insert(0, {"id": "gas_context", "op": "Atmosphere", "vessel": "reactor",
                                             "gas": gas.lower(), "mode": "environment",
                                             "meta": {"source_path": raw["atmosphere"].get("derived_from", "/conditions/pressure/atmosphere")}})
            prepared = _prepare(protocol, raw, reviews, devices)
            structured[raw["source"]["dataset_name"]].append((prepared, raw))
        except (ValueError, KeyError, TypeError):
            continue
    positives, hashes, reaction_counts = [], set(), Counter()

    def add(protocol, raw):
        key = protocol["canonical_sha1"]
        reaction = protocol["reaction_smiles"]
        if key in hashes or reaction_counts[reaction] >= 3 or protocol["id"] in {p["id"] for p in positives}:
            return
        positives.append(protocol)
        raw_lookup[protocol["id"]] = raw
        hashes.add(key)
        reaction_counts[reaction] += 1

    for protocol in sorted(text, key=lambda p: p["id"]):
        add(protocol, raw_lookup[protocol["id"]])
        if len(positives) >= limit:
            break
    while len(positives) < limit and any(structured.values()):
        for name in sorted(structured):
            if not structured[name]:
                continue
            protocol, raw = structured[name].popleft()
            add(protocol, raw)
            if len(positives) >= limit:
                break
    assign_splits(positives, [])
    index = SuccessIndex()
    success_count = index.build(read_raw())
    negatives, negative_stats = generate_observed(positives, read_raw(), per_risk, success_index=index)
    index.close()
    assign_splits(positives, negatives)
    for protocol in positives:
        (data_dir / "xdl/positive").mkdir(parents=True, exist_ok=True)
        (data_dir / "xdl/positive" / (protocol["id"] + ".xdl")).write_text(protocol["xdl"], encoding="utf-8")
        write_json(data_dir / "raw/protocols" / (protocol["raw_id"] + ".json"), raw_lookup[protocol["id"]])
    for negative in negatives:
        xml = export_xdl(negative["protocol"])
        validate_xdl(xml)
        negative["xdl"] = xml
        folder = data_dir / "xdl/negative" / negative["label"]["risk_l2"]
        folder.mkdir(parents=True, exist_ok=True)
        (folder / (negative["id"] + ".xdl")).write_text(xml, encoding="utf-8")
    controls, control_negatives = generate_controls(per_risk)
    for negative in control_negatives:
        negative["xdl"] = export_xdl(negative["protocol"])
        validate_xdl(negative["xdl"])
        folder = data_dir / "controls/xdl" / negative["label"]["risk_l2"]
        folder.mkdir(parents=True, exist_ok=True)
        (folder / (negative["id"] + ".xdl")).write_text(negative["xdl"], encoding="utf-8")
    write_jsonl(data_dir / "positives.jsonl", positives)
    write_jsonl(data_dir / "negatives.jsonl", negatives)
    write_jsonl(data_dir / "controls/parents.jsonl", controls)
    write_jsonl(data_dir / "controls/negatives.jsonl", control_negatives)
    write_jsonl(data_dir / "intermediate/rejected.jsonl", rejected)
    write_jsonl(data_dir / "raw/selected.jsonl", [raw_lookup[p["id"]] for p in positives])
    write_jsonl(data_dir / "unmapped.jsonl", [{"id": p["id"], "action": action} for p in extracts.values()
                for action in p["extraction"].get("unmapped_actions", [])])
    stats = {"raw_reactions": read_json(ROOT / "reports/ingest.json")["total"], "raw_selected": len(positives),
             "positive_xdl": len(positives), "strict_gold": sum(p["quality"]["tier"] == "gold" for p in positives),
             "silver": sum(p["quality"]["tier"] == "silver" for p in positives),
             "positive_methods": dict(Counter(p["extraction"]["method"] for p in positives)),
             "independent_amounts_verified": sum(p["crosscheck"]["checks"]["amount_comparison_is_independent"] for p in positives),
             "unique_reaction_smiles": len({p["reaction_smiles"] for p in positives}),
             "unique_canonical_protocols": len({p["canonical_sha1"] for p in positives}),
             "selected_source_datasets": len({p["source"]["dataset_id"] for p in positives}),
             "observed_parent_negatives": len(negatives), "observed_risk_counts": negative_stats["counts"],
             "negative_rejection_counts": negative_stats["rejected"], "success_filter_observations": success_count,
             "negative_selection": negative_stats.get("selection", {}),
             "control_parents": len(controls), "control_negatives": len(control_negatives),
             "control_risk_counts": dict(Counter(n["label"]["risk_l2"] for n in control_negatives)),
             "hardware_entries": len(load_library("hardware.yaml")["devices"]),
             "hardware_human_verified": sum(d.get("verified") is True for d in devices.values()),
             "review_input_issues": reviews.issues,
             "primitive_operations": len(load_library("primitives.yaml")["operations"]),
             "risk_categories": len(load_library("risks.yaml")["risks"]),
             "split_counts": dict(Counter(p["split"] for p in positives)),
             "important": "Controls do not count as ORD gold negatives; silver exports do not certify hardware feasibility."}
    write_json(report_dir / "stats.json", stats)
    _prune_outputs(positives, negatives, control_negatives, data_dir)
    return stats


def _prune_outputs(positives, negatives, controls, data_dir=None):
    """Remove stale generated files only; preserve unrelated files and human review artifacts."""
    expected = {
        "xdl/positive": {p["id"] + ".xdl" for p in positives},
        "raw/protocols": {p["raw_id"] + ".json" for p in positives},
    }
    data_dir = ROOT / "data" if data_dir is None else Path(data_dir).resolve()
    if not data_dir.resolve().is_relative_to((ROOT / "data").resolve()):
        raise ValueError("Output cleanup target escapes data directory")
    for prefix, samples in (("xdl/negative", negatives), ("controls/xdl", controls)):
        for risk in load_library("risks.yaml")["risks"]:
            expected[prefix + "/" + risk] = {n["id"] + ".xdl" for n in samples if n["label"]["risk_l2"] == risk}
    for name, filenames in expected.items():
        folder = (data_dir / name).resolve()
        if not folder.is_relative_to((ROOT / "data").resolve()):
            raise ValueError("Output cleanup target escapes data directory")
        if not folder.exists():
            continue
        pattern = "ord-*.json" if name.endswith("protocols") else "*.xdl"
        for path in folder.glob(pattern):
            if path.name not in filenames and path.is_file() and path.resolve().is_relative_to(folder):
                path.unlink()
