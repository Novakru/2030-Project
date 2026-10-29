"""Summarize a frozen batch without treating conversion or coverage gaps as successes."""
import argparse
import json
from collections import Counter
from pathlib import Path

from protocol_risk.io import load_library, read_json, read_jsonl


def summarize(run_dir):
    root = Path(run_dir)
    manifest = read_json(root / "manifest.json")
    result = manifest["result"]
    folder = root / Path(result["review_bundle"]["positives"]).parent
    parents = list(read_jsonl(root / result["review_bundle"]["positives"]))
    negatives = list(read_jsonl(root / result["review_bundle"]["negatives"]))
    failures = list(read_jsonl(folder / "quarantined.jsonl"))
    registry = read_json(root / result["library_registry"])
    evolution = read_json(root / result["library_evolution"])
    atomic = read_json(folder / "atomic_operations.json")
    mappings = registry.get("operation_mappings", {})
    gaps = [gap for parent in parents for gap in parent.get("quality", {}).get("missing_parameters", [])]
    extension_usage = Counter(step["op"] for parent in parents for step in parent["steps"]
                              if step["op"] in parent.get("operation_definitions", {}))
    risk_counts = Counter(record["label"]["risk_l2"] for record in negatives)
    risks = {}
    for risk in load_library("risks.yaml")["risks"]:
        selected = [record for record in negatives if record["label"]["risk_l2"] == risk]
        risks[risk] = {"records": risk_counts[risk],
                       "mechanisms": dict(Counter(record["mutation"]["mechanism_id"] for record in selected)),
                       "parents": len({record["parent_id"] for record in selected}),
                       "label_types": dict(Counter(record["label"]["label_type"] for record in selected))}
    return {"run_id": result["run_id"], "status": manifest["status"],
            "input_contract": result["input_contract"], "raw_source_records": result["raw_source_records"],
            "text_conversions": result["text_primary_positives"], "negative_candidates": len(negatives),
            "incomplete_conversions": len(failures), "audit_records": len(parents) + len(negatives) + len(failures),
            "tool_failed_conversions": len(failures),
            "representation_complete": sum(parent.get("quality", {}).get("representation_complete", False) for parent in parents),
            "parameters_complete": sum(parent.get("quality", {}).get("parameters_complete", False) for parent in parents),
            "missing_source_parameter_records": sum(bool(parent.get("quality", {}).get("missing_parameters")) for parent in parents),
            "missing_parameter_statuses": dict(Counter(gap["status"] for gap in gaps)),
            "extended_profile_records": sum(parent.get("xdl_profile") == "mosaic-xdl/1" for parent in parents),
            "canonical_profile_records": sum(parent.get("xdl_profile") == "mosaic-canonical/1" for parent in parents),
            "canonical_operation_usage": dict(sorted(Counter(step.get("operation_id") for p in parents for step in p["steps"]
                                                               if step.get("operation_id")).items())),
            "temporal_relations": sum(len(parent.get("temporal_relations", [])) for parent in parents),
            "unresolved_operation_records": sum(bool(p.get("normalization", {}).get("unresolved")) for p in parents),
            "migration": result.get("migration"),
            "extension_usage": dict(sorted(extension_usage.items())),
            "positive_source_datasets": len({p["source"].get("dataset_id") for p in parents}),
            "strict_gold": sum(p.get("quality", {}).get("tier") == "gold" for p in parents),
            "quota_acceptance_passed": not result["positive_shortfall"] and not result["risk_shortfalls"],
            "positive_shortfall": result["positive_shortfall"], "risk_shortfalls": result["risk_shortfalls"],
            "risks": risks, "mechanism_groups": sum(len(value["mechanisms"]) for value in risks.values()),
            "failure_reasons": dict(Counter(row["error"].split(":")[0] for row in failures)),
            "positive_apparatus_kinds": dict(Counter(node.get("apparatus_kind", node.get("category", "unknown"))
                for p in parents for node in p["hardware"]["nodes"].values())),
            "library": {"families": len(registry["families"]), "catalog_profiles": len(registry["devices"]),
                        "canonical_operations": len(registry.get("canonical_operations", registry["operations"])),
                        "canonical_equipment_categories": len(registry.get("equipment_catalog", {}).get("categories", {})),
                        "canonical_equipment_subtypes": len(registry.get("equipment_catalog", {}).get("subtypes", {})),
                        "legacy_mapped_names": len(mappings.get("migrations", {})),
                        "legacy_mapped_contracts": len(mappings.get("contracts", {})),
                        "source_contract_versions_not_public_concepts": len(registry.get("source_operation_contracts", {})),
                        "operations_used": atomic["selected_operations_used"],
                        "operation_candidates": len(registry["operation_candidates"]),
                        "family_candidates": len(registry["family_candidates"]),
                        "admitted_representations": len(registry["representations"]),
                        "admitted_extension_contract_versions": len(registry.get("extension_operations", {})),
                        "admitted_extension_names": sorted({definition["name"] for definition in registry.get("extension_operations", {}).values()}),
                        "observations": evolution["observations"], "curator": evolution["curator"],
                        "curation_actions": {} if result.get("migration") else evolution["counts"],
                        "historical_curation_actions": evolution["counts"] if result.get("migration") else {},
                        "rejected_proposals": len(evolution["rejected"]),
                        "pending_observations": len(evolution["pending_observation_ids"]),
                        "before_revision": evolution["before_revision"], "after_revision": evolution["after_revision"],
                        "minimality_proven": atomic["minimality_proven"]},
            "model_receipts": {"live_calls_this_run": result["model_calls"],
                               "cached_role_responses": sum(e["engine"] == "cache_replay" and e["stage"].startswith("agent/")
                                                            for e in manifest["events"]),
                               "note": "Cached responses include earlier live work; replay does not mean no historical API usage."},
            "limitations": ["Silver means static checks passed, not experimental completeness or feasibility certification.",
                            "Action coverage is heuristic; unknowns and unrepresented parameters remain explicit.",
                            "No ORD structured-field backfill and no authored controls count toward text conversion quotas.",
                            "Same equipment family does not prove substitutability; unknown ratings remain unknown.",
                            "Biology/materials contracts can be represented; specialized execution adapters are not implemented.",
                            "Automatic curation is bounded; the remainder stays pending; no new executable operation was admitted."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--output", type=Path, default=Path("reports/mosaic_quality.json"))
    args = parser.parse_args()
    report = summarize(args.run_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes((json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    print(f"{report['text_conversions']} conversions, {report['negative_candidates']} negatives, "
          f"{report['incomplete_conversions']} incomplete; quota acceptance: {report['quota_acceptance_passed']}")


if __name__ == "__main__":
    main()
