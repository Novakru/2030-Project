"""Audit a versioned dataset and expose evidence for diversity and IR reduction."""
from __future__ import annotations

import copy
import re
from collections import Counter, defaultdict
from pathlib import Path

import jsonpatch

from .apparatus import source_fact_hash
from .diversity import summarize
from .io import ROOT, digest, load_library, read_json, read_jsonl, write_json
from .symbolic import evaluate
from .xdl import export_xdl, validate_xdl


def atomic_inventory(positives, snapshots):
    library = load_library("primitives.yaml")
    definitions = library["operations"]
    used = Counter(s["op"] for p in positives for s in p["steps"])
    extracted = Counter(s["op"] for p in snapshots for s in p.get("steps", []))
    context_only = Counter(s["op"] for p in positives for s in p["steps"]
                           if s["op"] == "Atmosphere" and s.get("mode") in ("environment", "balloon"))
    unmapped = [{"id": p["id"], "actions": p.get("extraction", {}).get("unmapped_actions", [])}
               for p in snapshots if p.get("extraction", {}).get("unmapped_actions")]
    fields = {op: set(spec["required"] + spec["optional"]) for op, spec in definitions.items()}
    operations = {}
    for op, spec in definitions.items():
        elsewhere = set().union(*(v for k, v in fields.items() if k != op))
        operations[op] = {"selected_steps": used[op], "context_only_steps": context_only[op],
            "snapshot_steps": extracted[op], "required": spec["required"], "optional": spec["optional"],
            "fields_unique_in_current_registry": sorted(fields[op] - elsewhere), "risk_checks": spec["risks"],
            "state_distinction": spec["reason"], "export_mapping": spec["xdl_steps"],
            "reduction_status": "retain_pending_lossless_proof" if used[op] else "defer_removal_broader_source_coverage_needed"}
    all_fields = set().union(*fields.values())
    aliases = {"solvent": "reagent", "wash_reagent": "reagent", "quench_reagent": "reagent",
               "drying_agent": "reagent", "temperatures": "temp_C"}
    macros = {}
    for name, spec in load_library("macros.yaml")["macros"].items():
        missing = [key for key in spec.get("requires", []) if aliases.get(key, key) not in all_fields]
        macros[name] = {"expansion": spec["expansion"], "requires": spec.get("requires", []),
                       "parameters_without_primitive_field": missing, "status": "draft_not_proven_lossless",
                       "gate": "Preserve source parameters, state effects, endpoints and apparatus context; replay risk checks before admission."}
    return {"library_version": library["version"], "candidate_operations": len(definitions),
            "selected_operations_used": sum(bool(used[op]) for op in definitions),
            "selected_steps": sum(used.values()), "extraction_snapshots": len(snapshots),
            "operations": operations, "macro_candidates": macros,
            "unmapped_snapshot_records": len(unmapped), "unmapped_snapshot_actions": sum(len(r["actions"]) for r in unmapped),
            "unmapped_examples": unmapped[:5], "source_action_coverage": None,
            "source_action_coverage_status": "unproven: no independently annotated complete source-action denominator",
            "minimality_proven": False,
            "policy": "No new primitives or automatic removals. Shared fields alone do not prove equivalent state effects; selected IR coverage does not establish 98% source-action coverage."}


def _binding_summary(positives):
    nodes = [p["hardware"]["nodes"].get("reactor", {}) for p in positives]
    micro = [p for p in positives if re.search(r"micro[- ]?reactor", " ".join(s.get("meta", {}).get("evidence", "") for s in p["steps"]), re.I)]
    return {"vessel_types": dict(Counter(n.get("apparatus_kind", "unspecified") for n in nodes)),
            "binding_basis": dict(Counter(n.get("binding_basis", "legacy_default") for n in nodes)),
            "microreactor_mentions": len(micro),
            "microreactor_type_retained": sum(p["hardware"]["nodes"]["reactor"].get("apparatus_kind") == "microreactor" for p in micro),
            "explicit_5mL_microreactors": [p["id"] for p in micro if p["hardware"]["nodes"]["reactor"].get("params", {}).get("capacity_mL") == 5],
            "source_conflicts": sum(bool(p["hardware"].get("source_issues")) for p in positives)}


def _norm(text):
    return " ".join(text.split()).casefold()


def audit_version(positives, negatives, data_dir):
    issues = []
    parents = {p["id"]: p for p in positives}
    if len(parents) != len(positives):
        issues.append({"reason": "duplicate_positive_ids"})
    fingerprints = set()
    for p in positives:
        try:
            if evaluate(p).risks or export_xdl(p) != p["xdl"]:
                raise ValueError("positive_rule_or_export_mismatch")
            validate_xdl(p["xdl"])
            raw = read_json(data_dir / "raw/protocols" / (p["raw_id"] + ".json"))
            if digest(raw["raw"]) != p["raw_sha256"]:
                raise ValueError("raw_snapshot_hash_mismatch")
            for node in p["hardware"]["nodes"].values():
                if node.get("binding_basis") != "source_reported":
                    continue
                if node.get("verified") or node.get("source_fact_sha256") != source_fact_hash(node):
                    raise ValueError("source_fact_hash_or_verification_mismatch")
                for citation in node.get("source_evidence", []):
                    if citation["raw_sha256"] != raw["raw_sha256"] or citation["source_url"] != raw["source"]["url"]:
                        raise ValueError("source_fact_provenance_mismatch")
                    if citation["locator"] == "/setup/vessel":
                        if citation["value"] != raw["setup"]["vessel"]:
                            raise ValueError("source_setup_mismatch")
                    elif isinstance(citation["value"], str) and _norm(citation["value"]) not in _norm(raw.get("procedure") or ""):
                        raise ValueError("source_quote_not_found_in_raw")
        except (ValueError, KeyError, TypeError, OSError) as error:
            issues.append({"id": p["id"], "reason": str(error)[:500]})
    for n in negatives:
        try:
            parent = parents[n["parent_id"]]
            child = jsonpatch.apply_patch(copy.deepcopy(parent), n["diff"])
            expected = [] if n["label"]["label_type"] == "soft" else [n["label"]["risk_l2"]]
            if child != n["protocol"] or evaluate(child).risks != expected or n["xdl"] != export_xdl(child):
                raise ValueError("negative_replay_or_rule_or_export_mismatch")
            validate_xdl(n["xdl"])
            from .perturb import negative_fingerprint
            key = negative_fingerprint(n)
            if key in fingerprints:
                raise ValueError("duplicate_negative_protocol")
            fingerprints.add(key)
            if n["split"] != parent["split"] or n["mutation"]["semantic_fault_count"] != 1:
                raise ValueError("split_or_declared_fault_count_mismatch")
        except (ValueError, KeyError, TypeError) as error:
            issues.append({"id": n["id"], "reason": str(error)[:500]})
    return {"passed": not issues, "positives_checked": len(positives), "negatives_checked": len(negatives),
            "checks": ["raw object hashes", "source apparatus quotes/fields", "positive rules and XML", "exact child patch replay", "negative single risk class", "duplicate negatives", "split isolation"],
            "scope": "Internal integrity; not independent extraction review, chemical feasibility certification or proof of semantic fault independence.", "issues": issues}


def quality_report(dataset_dir):
    data_dir = Path(dataset_dir).resolve()
    if not data_dir.is_relative_to((ROOT / "data").resolve()) or data_dir == (ROOT / "data").resolve():
        raise ValueError("Quality report requires a separate version directory under data/")
    positives = list(read_jsonl(data_dir / "positives.jsonl"))
    negatives = list(read_jsonl(data_dir / "negatives.jsonl"))
    baseline = list(read_jsonl(ROOT / "data/positives.jsonl"))
    baseline_neg = list(read_jsonl(ROOT / "data/negatives.jsonl"))
    parents = {p["id"]: p for p in positives}
    old_parents = {p["id"]: p for p in baseline}
    by_risk, old_risks = defaultdict(list), defaultdict(list)
    for n in negatives:
        by_risk[n["label"]["risk_l2"]].append(n)
    for n in baseline_neg:
        old_risks[n["label"]["risk_l2"]].append(n)
    snapshots = [read_json(p) for p in sorted((ROOT / "data/intermediate/extractions").glob("*.json"))]
    atoms = atomic_inventory(positives, snapshots)
    integrity = audit_version(positives, negatives, data_dir)
    changed = [identifier for identifier in sorted(set(parents) & set(old_parents))
               if parents[identifier]["hardware"] != old_parents[identifier]["hardware"]]
    stats = read_json(data_dir / "reports/stats.json")
    supplements = [ROOT / "data/native_negatives.jsonl", ROOT / "data/sop/negatives.jsonl"]
    extra = [n for p in supplements if p.exists() for n in read_jsonl(p)]
    counts = Counter(n["label"]["risk_l2"] for n in negatives + extra)
    report = {"version": 2, "dataset_dir": data_dir.relative_to(ROOT).as_posix(), "passed": integrity["passed"],
              "integrity": integrity, "positive_records": len(positives), "negative_records": len(negatives),
              "hardware": {"baseline": _binding_summary(baseline), "current": _binding_summary(positives), "changed_shared_ids": changed},
              "diversity": {risk: {"baseline": summarize(old_risks[risk], old_parents), "current": summarize(by_risk[risk], parents),
                             "pool": stats.get("negative_selection", {}).get(risk, {}).get("candidate_pool", {})}
                            for risk in load_library("risks.yaml")["risks"]},
              "comparison_scope": "Baseline and v2 differ in apparatus and selected records; counts describe the actual versions, not an isolated experiment on the selector.",
              "supplement_partitions": [{"path": p.relative_to(ROOT).as_posix(), "sha256": digest(p.read_bytes())} for p in supplements if p.exists()],
              "combined_constructed_counts": {risk: counts[risk] for risk in load_library("risks.yaml")["risks"]},
              "combined_constructed_gaps": {risk: max(0, 10 - counts[risk]) for risk in load_library("risks.yaml")["risks"] if counts[risk] < 10},
              "atomic_minimum": {"candidate_operations": atoms["candidate_operations"], "selected_operations_used": atoms["selected_operations_used"], "minimality_proven": False},
              "strict_gold": sum(p["quality"]["tier"] == "gold" for p in positives), "manual_reviews_created": 0,
              "source_rejections": dict(Counter(r["reason"] for r in read_jsonl(data_dir / "intermediate/rejected.jsonl"))),
              "limitations": ["Most risk mechanisms remain single-pattern; source diversity alone does not solve this.",
                              "A3/B4/C5 remain source-limited; B2/B3 scenario supplements are not independent experiments.",
                              "No universal atomic minimum or 98% source-action coverage proven; no review DB updated."]}
    target = data_dir / "reports"
    write_json(target / "data_quality.json", report)
    write_json(target / "atomic_minimum.json", atoms)
    lines = ["# 原子操作最小集：迭代证据", "", "目前保留 12 个候选操作，不声称已证明最小集。", "",
             "| 操作 | 入选步骤 | 其中仅上下文 | 提取快照步骤 | 独立语义 / 合并前需保留 |", "|---|---:|---:|---:|---|"]
    for op, row in atoms["operations"].items():
        lines.append(f"| {op} | {row['selected_steps']} | {row['context_only_steps']} | {row['snapshot_steps']} | {row['state_distinction']} |")
    lines.extend(["", "操作出现少不能证明可删。宏分解仍是候选：须保留参数、状态变化、终点条件及风险检查结果，才可合并。",
                  "AdjustPH 的 target_pH 尚无对应原子字段；不能把它直接认定为一次 Add 的无损别名。",
                  f"{len(snapshots)} 份提取快照中仍保留 {atoms['unmapped_snapshot_actions']} 个未映射条目，其中含待分类事项。没有独立标注的完整原文动作分母，不能据已映射 IR 宣称原文覆盖率达到 98%。", ""])
    (target / "atomic_minimum.md").write_text("\n".join(lines), encoding="utf-8")
    rows = ["# 数据质量 v2", "", f"{len(positives)} 条 silver 正例，{len(negatives)} 条 ORD 派生风险候选；未生成人工决定。", "",
            "| 风险 | 来源数据集：旧 → 新 | 父流程：旧 → 新 | 机制代理分组：旧 → 新 |", "|---|---:|---:|---:|"]
    for risk, pair in report["diversity"].items():
        a, b = pair["baseline"], pair["current"]
        rows.append(f"| {risk} | {a['source_dataset']['unique']} → {b['source_dataset']['unique']} | {a['parent']['unique']} → {b['parent']['unique']} | {a['mechanism']['unique']} → {b['mechanism']['unique']} |")
    rows.extend(["", "机制分组依据规则、修改字段、原有操作及试剂角色，是去重代理，不等于已验证的独立物理故障机制。多数类别仍只有一种模式，尚需来源驱动补齐。",
                 "原文 microreactor 保留类型与 5 mL 容量；未指定控制器的 IKA 绑定明确标为建议分析配置；孔板体积范围不清时保留原值并放弃容量判定。",
                 "当前 SQLite 保存原始导入版本。查看本版应新建数据库、仅导入本目录 positives.jsonl / negatives.jsonl；原数据库不自动同步。",
                 "原子操作收敛证据见 [atomic_minimum.md](atomic_minimum.md)。完整计数、引用、缺口与校验结果见 [data_quality.json](data_quality.json)。", ""])
    (target / "data_quality.md").write_text("\n".join(rows), encoding="utf-8")
    return {"passed": report["passed"], "dataset_dir": report["dataset_dir"], "positives": len(positives), "negatives": len(negatives),
            "audit_issues": len(integrity["issues"]), "remaining_constructed_gaps": report["combined_constructed_gaps"],
            "report": (target / "data_quality.md").relative_to(ROOT).as_posix()}
