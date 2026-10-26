"""Dataset-level acceptance checks; full acceptance and internal integrity are separate."""
from __future__ import annotations

import copy
import csv
import random
from collections import Counter

import jsonpatch

from .ingest import iter_ord
from .crosscheck import crosscheck
from .io import ROOT, digest, load_library, read_json, read_jsonl, write_json
from .perturb import negative_fingerprint
from .symbolic import evaluate
from .xdl import canonical_hash, export_xdl, validate_xdl
from .yields import target_yield


def judge_admitted(report):
    required = ("C1", "C2", "C3", "C4", "C6")
    for risk in required:
        item = report.get("per_risk", {}).get(risk, {})
        metrics = item.get("test_metrics", {})
        if item.get("admitted") is not True:
            return False
        auc, ece, precision = (metrics.get(k) for k in ("auroc", "ece", "precision_at_p_ge_0_9"))
        if any(not isinstance(value, (int, float)) or isinstance(value, bool) for value in (auc, ece, precision)):
            return False
        if not (auc >= 0.80 and ece <= 0.05 and precision >= 0.85):
            return False
    return True


def hard_review_metrics(rows, eligible_ids):
    reviewed = {}
    for row in rows:
        correct = row.get("correct", "").strip().lower()
        if row.get("id") in eligible_ids and row.get("reviewer", "").strip() and correct in ("true", "false", "1", "0"):
            reviewed[row["id"]] = correct in ("true", "1")
    errors = sum(not good for good in reviewed.values())
    return {"count": len(reviewed), "errors": errors, "error_rate": errors / len(reviewed) if reviewed else None}


def audit():
    from .reviews import ReviewBook
    review_book = ReviewBook()
    reviewed_devices = review_book.devices()
    failures, checks = [], Counter()
    manifest = read_json(ROOT / "data/sources.lock.json")
    for item in manifest["files"]:
        path = ROOT / item["path"]
        if not path.exists() or digest(path.read_bytes()) != item["sha256"]:
            failures.append("source_checksum:" + path.name)
        checks["source_files_checked"] += 1
    positives = list(read_jsonl(ROOT / "data/positives.jsonl"))
    parents = {p["id"]: p for p in positives}
    reaction_counts = Counter(p["reaction_smiles"] for p in positives)
    if any(count > 3 for count in reaction_counts.values()):
        failures.append("more_than_three_variants_per_reaction")
    hashes, raw_ids = set(), set()
    source_raw_hashes = {}
    needed = {p["raw_id"] for p in positives}
    # Independently deserialize upstream records rather than trusting the intermediate copy.
    for source in manifest["files"]:
        for raw, _ in iter_ord(ROOT / source["path"], ids=needed):
            if raw.get("reaction_id") in needed:
                source_raw_hashes[raw["reaction_id"]] = digest(raw)
    split_groups = {}
    for p in positives:
        checks["positives_checked"] += 1
        if p["id"] in raw_ids or p["canonical_sha1"] in hashes:
            failures.append("positive_duplicate:" + p["id"])
        raw_ids.add(p["id"])
        hashes.add(p["canonical_sha1"])
        if canonical_hash(p) != p["canonical_sha1"]:
            failures.append("canonical_hash:" + p["id"])
        if source_raw_hashes.get(p["raw_id"]) != p["raw_sha256"]:
            failures.append("upstream_raw_hash:" + p["id"])
        raw_path = ROOT / "data/raw/protocols" / (p["raw_id"] + ".json")
        if not raw_path.exists():
            failures.append("missing_selected_raw:" + p["id"])
        else:
            selected = read_json(raw_path)
            if digest(selected["raw"]) != p["raw_sha256"]:
                failures.append("selected_raw_hash:" + p["id"])
            if selected["yield_percent"] is None or selected["yield_percent"] <= 30:
                failures.append("unproven_source_success:" + p["id"])
            observed, evidence = target_yield(selected["raw"])
            if (observed != selected["yield_percent"] or observed != p["yield_percent"]
                    or evidence != selected.get("yield_evidence") or evidence != p.get("yield_evidence")):
                failures.append("target_yield_evidence:" + p["id"])
            if crosscheck(p, selected) != p["crosscheck"]:
                failures.append("stale_or_incorrect_crosscheck:" + p["id"])
        try:
            validate_xdl(p["xdl"])
            if export_xdl(p) != p["xdl"]:
                failures.append("stale_positive_xdl:" + p["id"])
            xml_path = ROOT / "data/xdl/positive" / (p["id"] + ".xdl")
            if xml_path.read_text(encoding="utf-8") != p["xdl"]:
                failures.append("positive_xdl_file_mismatch:" + p["id"])
        except Exception as error:
            failures.append("xdl_positive:" + p["id"] + ":" + type(error).__name__)
        judgment = evaluate(p)
        if judgment.risks:
            failures.append("positive_violation:" + p["id"])
        if judgment.unknowns != p["quality"]["unknown_constraints"]:
            failures.append("stale_unknown_constraints:" + p["id"])
        expected_quality = review_book.apply(copy.deepcopy(p))["quality"]
        for key in ("tier", "manual_review", "hardware_verification", "gold_blockers", "review_record_sha256"):
            if expected_quality.get(key) != p["quality"].get(key):
                failures.append("review_verdict:" + p["id"] + ":" + key)
        if p["quality"].get("manual_review") == "rejected":
            failures.append("rejected_review_still_exported:" + p["id"])
        for node in p["hardware"]["nodes"].values():
            if node.get("id") in reviewed_devices and node != reviewed_devices[node["id"]]:
                failures.append("hardware_fact_or_review_mismatch:" + p["id"])
        group, split = p["split_group"], p["split"]
        if group in split_groups and split_groups[group] != split:
            failures.append("scaffold_leakage:" + group)
        split_groups[group] = split
    negatives = list(read_jsonl(ROOT / "data/negatives.jsonl"))
    control_parents = {p["id"]: p for p in read_jsonl(ROOT / "data/controls/parents.jsonl")}
    controls = list(read_jsonl(ROOT / "data/controls/negatives.jsonl"))
    negative_hashes = set()
    for n in negatives + controls:
        mapping = control_parents if n["origin"] == "authored_control" else parents
        parent = mapping.get(n["parent_id"])
        if parent is None:
            failures.append("missing_parent:" + n["id"])
            continue
        checks["negatives_checked"] += 1
        try:
            if jsonpatch.apply_patch(copy.deepcopy(parent), n["diff"]) != n["protocol"]:
                failures.append("patch_replay:" + n["id"])
            if evaluate(parent).risks:
                failures.append("invalid_parent:" + n["id"])
            judgment = evaluate(n["protocol"])
            risks = judgment.risks
            expected = [] if n["label"]["label_type"] == "soft" else [n["label"]["risk_l2"]]
            if risks != expected:
                failures.append("multi_or_wrong_fault:" + n["id"])
            if n["label"]["label_type"] == "hard" and n["label"]["evidence"] != judgment.violations:
                failures.append("stale_rule_evidence:" + n["id"])
            validate_xdl(n["xdl"])
            if export_xdl(n["protocol"]) != n["xdl"]:
                failures.append("stale_negative_xdl:" + n["id"])
        except Exception as error:
            failures.append("negative_integrity:" + n["id"] + ":" + type(error).__name__)
        # Different hardware faults must remain distinct even if XDL procedure text is identical.
        complete_hash = negative_fingerprint(n)
        if complete_hash in negative_hashes:
            failures.append("negative_duplicate:" + n["id"])
        negative_hashes.add(complete_hash)
        if n["label"]["label_type"] == "soft" and (n["label"]["feasible"] is not None or n["label"]["p_infeasible"] is not None):
            failures.append("uncalibrated_probability_or_failure_claim:" + n["id"])
        if n["origin"] != "authored_control" and n["split"] != parent["split"]:
            failures.append("parent_split_leakage:" + n["id"])
    coverage = Counter(n["label"]["risk_l2"] for n in negatives)
    native_path = ROOT / "data/native_negatives.jsonl"
    if native_path.exists():
        from .native import audit_native_negatives
        native_result = audit_native_negatives()
        checks["native_negatives_checked"] = native_result["records_checked"]
        failures.extend("native:" + failure for failure in native_result["failures"])
        coverage.update(n["label"]["risk_l2"] for n in read_jsonl(native_path))
    source_coverage = Counter(coverage)
    scenario_coverage = Counter()
    sop_path = ROOT / "data/sop/negatives.jsonl"
    if sop_path.exists():
        from .sop import audit_sop
        sop_result = audit_sop()
        checks["sop_negatives_checked"] = sop_result["records_checked"]
        failures.extend("sop:" + failure for failure in sop_result["failures"])
        for row in read_jsonl(sop_path):
            (scenario_coverage if row["origin"] == "instantiated_sop" else source_coverage).update([row["label"]["risk_l2"]])
        coverage = source_coverage + scenario_coverage
    control_coverage = Counter(n["label"]["risk_l2"] for n in controls)
    if (ROOT / "data/publications/platform_validation.jsonl").exists():
        from .platform_validation import audit_native_platform
        platform_result = audit_native_platform()
        checks["native_platform_programs_checked"] = platform_result["programs_checked"]
        checks["native_platform_compiled_checked"] = platform_result["compiled_checked"]
        failures.extend("native_platform:" + failure for failure in platform_result["failures"])
    all_risks = list(load_library("risks.yaml")["risks"])
    hardware = list(reviewed_devices.values())
    # Prepare a real human review queue; do not claim it was reviewed by the agent.
    queue_path = ROOT / "reports/manual_review.csv"
    valid_review_ids = {n["id"] for n in negatives + controls}
    rewrite_queue = not queue_path.exists()
    if queue_path.exists():
        with queue_path.open(encoding="utf-8-sig", newline="") as stream:
            existing_reviews = list(csv.DictReader(stream))
        if not any(r.get("reviewer") or r.get("correct") or r.get("notes") for r in existing_reviews):
            rewrite_queue = any(r["id"] not in valid_review_ids for r in existing_reviews)
    if rewrite_queue:
        choices = random.Random(20261025).sample(negatives + controls, min(100, len(negatives + controls)))
        with queue_path.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=["id", "origin", "risk", "parent_id", "reviewer", "correct", "notes"])
            writer.writeheader()
            for sample in choices:
                writer.writerow({"id": sample["id"], "origin": sample["origin"], "risk": sample["label"]["risk_l2"], "parent_id": sample["parent_id"]})
    reviewed = 0
    review_rows = []
    with queue_path.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            review_rows.append(row)
            reviewed += bool(row.get("id") in valid_review_ids and row.get("reviewer") and row.get("correct") in ("true", "false", "1", "0"))
    eligible_hard_ids = {n["id"] for n in negatives if n.get("benchmark_eligible") and n["label"]["label_type"] == "hard"}
    hard_reviews = hard_review_metrics(review_rows, eligible_hard_ids)
    eligible_counts = Counter(n["label"]["risk_l2"] for n in negatives if n.get("benchmark_eligible"))
    metrics_path = ROOT / "reports/jev_metrics.json"
    admitted = judge_admitted(read_json(metrics_path)) if metrics_path.exists() else False
    strict = {"raw_100_plus": len(positives) >= 100, "xdl_exports_100_plus": len(positives) >= 100,
              "strict_gold_100_plus": sum(p["quality"]["tier"] == "gold" for p in positives) >= 100,
              "every_observed_risk_10_plus": all(source_coverage[r] >= 10 for r in all_risks),
              "every_constructed_risk_10_plus": all(coverage[r] >= 10 for r in all_risks),
              "every_benchmark_eligible_risk_10_plus": all(eligible_counts[r] >= 10 for r in all_risks),
              "every_control_risk_10_plus": all(control_coverage[r] >= 10 for r in all_risks),
              "hardware_20_human_verified": sum(d.get("verified") is True for d in hardware) >= 20,
              "manual_negative_review_100": reviewed >= 100,
              "manual_hard_gold_error_rate_below_2_percent": hard_reviews["count"] >= 100 and hard_reviews["error_rate"] < 0.02,
              "per_C_subclass_judge_admitted": admitted}
    result = {"passed": not failures, "full_specification_accepted": not failures and all(strict.values()),
              "checks": dict(checks), "failures": failures, "acceptance": strict,
              "observed_risk_gaps": {r: max(0, 10 - source_coverage[r]) for r in all_risks if source_coverage[r] < 10},
              "constructed_risk_gaps": {r: max(0, 10 - coverage[r]) for r in all_risks if coverage[r] < 10},
              "source_only_risk_gaps": {r: max(0, 10 - source_coverage[r]) for r in all_risks if source_coverage[r] < 10},
              "instantiated_sop_risk_counts": dict(scenario_coverage),
              "manual_reviews_completed": reviewed,
              "eligible_hard_manual_reviews": hard_reviews,
              "claim_limit": "Integrity checks are not a certificate of chemical or physical feasibility."}
    atomic_ops = set(load_library("primitives.yaml")["operations"])
    invalid_ops = {s["op"] for p in positives for s in p["steps"] if s["op"] not in atomic_ops}
    if invalid_ops:
        result["failures"].append("unmapped_primitives:" + ",".join(sorted(invalid_ops)))
        result["passed"] = False
    write_json(ROOT / "reports/audit.json", result)
    return result
