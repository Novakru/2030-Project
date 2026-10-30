"""Validate a conversion against its own frozen sources and XDL contracts."""
from pathlib import Path

from .evaluation import check_conservation
from .fact_binding import bind_facts
from .facts import validate_facts
from .registry import Registry
from .protocol.io import digest, read_json, read_jsonl
from .store import RunStore


def verify_conversion(run_dir):
    root = Path(run_dir).resolve()
    manifest = read_json(root / "manifest.json")
    RunStore(root, manifest["request"]).verify()
    result = manifest["result"]
    sources = {raw["id"]: raw for raw in read_jsonl(root / "sources.jsonl")}
    records = list(read_jsonl(root / result["review_bundle"]["records"]))
    failures = list(read_jsonl(root / "failures.jsonl"))
    candidates = list(read_jsonl(root / result["review_bundle"]["candidates"]))
    registry = Registry(read_json(root / "library_registry.json"))
    issues, seen = [], set()
    for record in records:
        try:
            if record["id"] in seen:
                raise ValueError("Duplicate converted record")
            seen.add(record["id"])
            source = sources[record["raw_id"]]
            if record["source_text"] != source["procedure"] or record["raw_sha256"] != source["raw_sha256"]:
                raise ValueError("Converted source differs from snapshot")
            if source.get("raw") is not None and digest(source["raw"]) != source["raw_sha256"]:
                raise ValueError("Source snapshot hash differs")
            facts = validate_facts(record["facts"], source["procedure"])
            bindings = bind_facts(facts, registry.snapshot)
            if bindings != record["bindings"] or record["compiled"]["xml"] != record["xdl"]:
                raise ValueError("Facts binding or XDL artifact differs")
            check = check_conservation(facts, bindings, record["compiled"])
            if not check["passed"] or check != record["compilation_check"]:
                raise ValueError("Actual XDL loses facts, references or apparatus identity")
            if (root / "xdl" / (record["id"] + ".xdl")).read_text(encoding="utf-8") != record["xdl"]:
                raise ValueError("XDL file differs from record")
            sidecar = read_json(root / "xdl" / (record["id"] + ".json"))
            expected_sidecar = {"record_id": record["id"], "text_sha256": record["text_sha256"],
                                **{k: v for k, v in record["compiled"].items() if k != "xml"}}
            if sidecar != expected_sidecar:
                raise ValueError("XDL configuration/extension sidecar differs from record")
        except (ValueError, KeyError, TypeError) as error:
            issues.append({"record_id": record.get("id"), "error": str(error)})
    attempted = [r["raw_id"] for r in records] + [f["raw_id"] for f in failures]
    if len(attempted) != len(set(attempted)) or set(attempted) != set(sources):
        issues.append({"error": "Each source must have exactly one conversion or failure"})
    if {c["raw_id"] for c in candidates} != {f["raw_id"] for f in failures}:
        issues.append({"error": "Failed sources must retain review candidates"})
    if result["converted"] != len(records) or result["failures"] != len(failures) or result["total"] != len(sources):
        issues.append({"error": "Manifest counts differ from records"})
    return {"passed": not issues, "converted": len(records), "sources": len(sources), "issues": issues}
