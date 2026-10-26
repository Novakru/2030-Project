"""Recorded human decisions tied to exact source, procedure and equipment facts."""
from __future__ import annotations

import copy
from datetime import date
from urllib.parse import urlsplit

from .io import ROOT, digest, load_library, read_json, read_jsonl, write_json

CHECKS = {
    "hardware": ("identity", "parameters", "material_scope", "ports", "operating_scope"),
    "protocol": ("chemical_identity", "quantities", "conditions", "procedure_coverage", "hardware_graph", "operating_constraints"),
}
FOLDERS = {"hardware": "hardware", "protocol": "protocols"}


def hardware_facts(device):
    return {k: v for k, v in device.items() if k not in ("verified", "verification")}


def protocol_facts(protocol):
    keys = ("id", "raw_id", "raw_sha256", "source", "reaction_smiles", "yield_percent", "yield_evidence",
            "reagents", "steps", "context", "hardware", "constraints", "extraction")
    facts = copy.deepcopy({k: protocol[k] for k in keys if k in protocol})
    hardware = facts.get("hardware", {})
    hardware.pop("verification_status", None)
    hardware["nodes"] = {name: hardware_facts(node) for name, node in hardware.get("nodes", {}).items()}
    return facts


def subject_hash(kind, subject):
    return digest(hardware_facts(subject) if kind == "hardware" else protocol_facts(subject))


def evidence_valid(evidence, root=ROOT):
    if not isinstance(evidence, list) or not evidence:
        return False
    for item in evidence:
        if not isinstance(item, dict) or any(not isinstance(item.get(k), str) or not item[k].strip()
                                            for k in ("source", "locator", "finding")):
            return False
        source = urlsplit(item["source"])
        if source.scheme in ("http", "https"):
            if not source.netloc or source.username or source.password:
                return False
        else:
            path = (root / item["source"]).resolve()
            if (not path.is_relative_to(root.resolve()) or not path.is_file() or path.name == ".env"
                    or item.get("sha256") != digest(path.read_bytes())):
                return False
    return True


def decision_status(record, kind, subject, root=ROOT):
    if record is None:
        return "missing"
    if not isinstance(record, dict) or record.get("kind") != kind or record.get("id") != subject["id"]:
        return "invalid"
    if record.get("subject_sha256") != subject_hash(kind, subject):
        return "stale"
    if record.get("verdict") == "pending":
        return "pending"
    try:
        date.fromisoformat(record.get("reviewed_at", ""))
    except (ValueError, TypeError):
        return "invalid"
    if (record.get("review_type") != "human" or not isinstance(record.get("reviewer"), str) or not record["reviewer"].strip()
            or not evidence_valid(record.get("evidence"), root)):
        return "invalid"
    if record.get("verdict") == "rejected":
        return "rejected"
    if record.get("verdict") != "approved" or not isinstance(record.get("checks"), dict):
        return "invalid"
    if not all(record["checks"].get(k) is True for k in CHECKS[kind]):
        return "incomplete"
    if kind == "hardware":
        known_facts = any(v is not None for v in subject.get("params", {}).values()) or bool(subject.get("wetted_materials"))
        if not known_facts or subject.get("verification", {}).get("status") == "template_only":
            return "template_only"
    elif record.get("unknowns_sha256") != digest(subject.get("quality", {}).get("unknown_constraints", [])):
        return "stale_constraints"
    return "approved"


class ReviewBook:
    def __init__(self, root=None, devices=None):
        root = ROOT if root is None else root
        self.root, self.records, self.issues, self.invalid = root, {}, [], set()
        self.base_devices = copy.deepcopy(devices if devices is not None else load_library("hardware.yaml")["devices"])
        self._devices = None
        for kind in CHECKS:
            for path in sorted((root / "data/reviews" / FOLDERS[kind]).glob("*.json")):
                try:
                    record = read_json(path)
                    if not isinstance(record, dict) or record.get("id") != path.stem or record.get("kind") != kind:
                        raise ValueError("Review ID/kind differs from its filename/folder")
                    self.records[(kind, path.stem)] = record
                except (ValueError, OSError) as error:
                    self.invalid.add((kind, path.stem))
                    self.issues.append({"path": path.relative_to(root).as_posix(), "error": type(error).__name__})

    def status(self, kind, subject):
        if (kind, subject["id"]) in self.invalid:
            return "invalid"
        return decision_status(self.records.get((kind, subject["id"])), kind, subject, self.root)

    def devices(self):
        if self._devices is not None:
            return self._devices
        devices = copy.deepcopy(self.base_devices)
        for device in devices:
            status = self.status("hardware", device)
            device["verified"] = status == "approved"
            if device["verified"]:
                device["verification"] = {"status": "human_verified", "human_verified": True,
                                           "review_record_sha256": digest(self.records[("hardware", device["id"])])}
        self._devices = {d["id"]: d for d in devices}
        return self._devices

    def configuration(self, protocol_id):
        path = self.root / "data/reviews/bindings" / (protocol_id + ".json")
        return read_json(path) if path.exists() else None

    def apply(self, protocol):
        quality = protocol["quality"]
        quality.pop("review_record_sha256", None)
        quality.pop("manual_review_scope", None)
        status = self.status("protocol", protocol)
        devices = self.devices()
        verified = bool(protocol["hardware"]["nodes"]) and all(
            d.get("verified") is True and d == devices.get(d.get("id")) for d in protocol["hardware"]["nodes"].values())
        blockers = []
        if status != "approved":
            blockers.append("protocol_review_pending")
        if not verified:
            blockers.append("hardware_human_verification_pending")
        if protocol.get("source", {}).get("db") != "ORD":
            blockers.append("unadmitted_source")
        if protocol["crosscheck"]["conflicts"] or quality["symbolic_violations"]:
            blockers.append("automatic_validation_conflict")
        quality.update(tier="silver" if blockers else "gold", review_status=status,
                       manual_review="approved" if status == "approved" else "rejected" if status == "rejected" else "pending",
                       hardware_verification="verified" if verified else "pending", gold_blockers=blockers)
        if status == "approved":
            quality["review_record_sha256"] = digest(self.records[("protocol", protocol["id"])])
            quality["manual_review_scope"] = "Source identity, amounts, conditions, complete procedure, hardware graph and listed unknown constraints; no execution certificate."
        return protocol


def prepare_review_packet():
    book = ReviewBook()
    subjects = [("hardware", d) for d in load_library("hardware.yaml")["devices"]]
    subjects.extend(("protocol", p) for p in read_jsonl(ROOT / "data/positives.jsonl"))
    lines = ["# 人工核对工作包", "", "此命令只生成待审核记录，保留已有人工内容。核对后填写 data/reviews/ 对应文件，再执行 build 和 audit。",
             "先审核硬件并重建，再审核流程；流程审核需确认当前列出的全部未知约束。参数、步骤或未知约束变化会使旧审核失效。", "",
             "| 类型 | ID | 当前状态 | 核对材料 |", "|---|---|---|---|"]
    counts = {}
    for kind, subject in subjects:
        identifier = subject["id"]
        request = {"kind": kind, "id": identifier, "subject_sha256": subject_hash(kind, subject),
                   "review_type": "human", "reviewer": "", "reviewed_at": "", "verdict": "pending",
                   "checks": {check: False for check in CHECKS[kind]}, "evidence": []}
        if kind == "protocol":
            request["unknowns_sha256"] = digest(subject["quality"]["unknown_constraints"])
        decision = ROOT / "data/reviews" / FOLDERS[kind] / (identifier + ".json")
        if not decision.exists():
            write_json(decision, request)
        status = book.status(kind, subject) if (kind, identifier) in book.records or (kind, identifier) in book.invalid else "pending"
        counts[status] = counts.get(status, 0) + 1
        packet = {"request": request, "current_status": status,
                  "snapshot": hardware_facts(subject) if kind == "hardware" else protocol_facts(subject)}
        if kind == "protocol":
            packet.update(automatic_crosscheck=subject["crosscheck"], unknown_constraints=subject["quality"]["unknown_constraints"],
                          raw_path=f"data/raw/protocols/{subject['raw_id']}.json", xdl_path=f"data/xdl/positive/{identifier}.xdl")
        write_json(ROOT / "reports/review_packet" / kind / (identifier + ".json"), packet)
        lines.append(f"| {kind} | {identifier} | {status} | [{identifier}.json]({kind}/{identifier}.json) |")
    (ROOT / "reports/review_packet/index.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    result = {"subjects": len(subjects), "statuses": counts, "load_issues": book.issues,
              "human_reviews_created": 0, "index": "reports/review_packet/index.md"}
    write_json(ROOT / "reports/review_packet.json", result)
    return result
