"""Small command-line entry point; build/audit run without an API or network."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .io import ROOT, digest, read_json, write_json


def main(argv=None):
    parser = argparse.ArgumentParser(prog="protocol-risk")
    subs = parser.add_subparsers(dest="command", required=True)
    subs.add_parser("api-check", help="Probe configured key and a deliberately invalid control key")
    subs.add_parser("fetch", help="Download immutable files and verify checksums from sources.lock.json")
    subs.add_parser("ingest", help="Read pinned ORD files into normalized raw records")
    extract = subs.add_parser("extract", help="Batch evidence-constrained extraction; API required")
    extract.add_argument("--limit", type=int, default=170)
    extract.add_argument("--workers", type=int, default=4)
    single = subs.add_parser("extract-one", help="Extract a UTF-8 text file or structured input JSON")
    single.add_argument("input", type=Path)
    single.add_argument("--output", type=Path, required=True)
    build = subs.add_parser("build", help="Rebuild XDL, examples and statistics offline")
    build.add_argument("--limit", type=int, default=140)
    build.add_argument("--per-risk", type=int, default=12)
    build.add_argument("--output-dir", type=Path, help="Versioned dataset directory under data/; leaves the current dataset and audit DB untouched")
    subs.add_parser("audit", help="Audit all exported records and patch replay offline")
    subs.add_parser("train", help="Train/calibrate a research baseline on real HTE yields; no judge admission implied")
    subs.add_parser("report", help="Render human-readable delivery and acceptance reports")
    quality = subs.add_parser("quality-report", help="Audit a separate dataset version and report diversity, source apparatus and atomic reduction evidence")
    quality.add_argument("--dataset-dir", type=Path, default=ROOT / "data/quality_v2")
    subs.add_parser("props-sync", help="Cache raw PubChem responses without guessing or replacing curated properties")
    subs.add_parser("collect-chemputer", help="Collect original author XDL/graph/compiled artifacts by verified ZIP ranges")
    subs.add_parser("audit-publications", help="Audit collected author XDLs and member checksums offline")
    subs.add_parser("prepare-publications", help="Prepare source-preserving publication references with auditable mechanical repairs")
    subs.add_parser("scan-amounts", help="Independently compare source-text quantities across all extraction snapshots")
    subs.add_parser("hte-contrasts", help="Find exact single-factor recorded HTE success/failure contrasts offline")
    subs.add_parser("audit-contrasts", help="Recheck HTE contrasts against upstream records and every recorded replicate")
    subs.add_parser("verify-rebuild", help="Rebuild all existing deterministic artifacts with HTTP blocked and compare every file")
    subs.add_parser("prepare-review", help="Prepare source-bound human review requests without approving or overwriting decisions")
    subs.add_parser("build-native-negatives", help="Construct missing-material-input errors in author-reported successful native XDL")
    subs.add_parser("audit-native-negatives", help="Recheck source-graph dependencies and exact native XDL statement deletion")
    subs.add_parser("build-sop", help="Build pinned SOP fragments and explicitly instantiated B2/B3/B5 scenarios offline")
    subs.add_parser("audit-sop", help="Check SOP source pins, parameter origins, rule target and patch replay")
    subs.add_parser("validate-native-platform", help="Parse/compile published native XDL with the pinned paper-bundled SDK, device I/O disabled")
    subs.add_parser("audit-native-platform", help="Check native platform inputs, adapter replay and compiled file checksums")
    args = parser.parse_args(argv)
    if args.command == "api-check":
        from .api import probe
        result = probe()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["passed"] else 1
    if args.command == "fetch":
        from .ingest import fetch_locked
        fetch_locked()
        result = {"status": "source_checksums_verified"}
    elif args.command == "ingest":
        from .ingest import ingest
        result = ingest()
    elif args.command == "extract":
        from .extract import extract_many
        result = {"extracted": len(extract_many(args.limit, args.workers))}
    elif args.command == "extract-one":
        from .api import Client
        from .extract import build_ir, text_plan
        if args.input.suffix.lower() == ".json":
            record = read_json(args.input)
        else:
            text = args.input.read_text(encoding="utf-8")
            identifier = "user_" + digest(text)[:16]
            record = {"id": identifier, "procedure": text, "components": [], "reaction_smiles": None,
                      "reaction_class": None, "raw_sha256": digest({"text": text}), "yield_percent": None,
                      "source": {"db": "USER_TEXT", "url": None, "file": str(args.input.resolve())},
                      "conditions": {}, "atmosphere": {}, "setup": {}}
        plan, provenance = text_plan(record, Client())
        result = build_ir(record, plan, provenance)
        result["quality"] = {"tier": "unreviewed", "feasibility": None}
        write_json(args.output, result)
        result = {"output": str(args.output), "steps": len(result["steps"]), "quality": "unreviewed"}
    elif args.command == "build":
        from .pipeline import build
        result = build(args.limit, args.per_risk, output_dir=args.output_dir)
    elif args.command == "audit":
        from .audit import audit
        result = audit()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["passed"] else 1
    elif args.command == "train":
        from .jev import train
        result = train()
    elif args.command == "report":
        from .report import report
        result = report()
    elif args.command == "quality-report":
        from .quality import quality_report
        result = quality_report(args.dataset_dir)
    elif args.command == "props-sync":
        from .props import sync_pubchem
        result = sync_pubchem()
    elif args.command == "collect-chemputer":
        from .publications import collect_chemputer
        result = collect_chemputer()
    elif args.command == "audit-publications":
        from .publications import audit_publications
        result = audit_publications()
    elif args.command == "prepare-publications":
        from .publications import prepare_publication_candidates
        result = prepare_publication_candidates()
    elif args.command == "scan-amounts":
        from .amounts import scan_amounts
        result = scan_amounts()
    elif args.command == "hte-contrasts":
        from .contrasts import build_contrasts
        result = build_contrasts()
    elif args.command == "audit-contrasts":
        from .contrasts import audit_contrasts
        result = audit_contrasts()
    elif args.command == "verify-rebuild":
        from .reproduce import verify_rebuild
        result = verify_rebuild()
    elif args.command == "prepare-review":
        from .reviews import prepare_review_packet
        result = prepare_review_packet()
    elif args.command == "build-native-negatives":
        from .native import build_native_negatives
        result = build_native_negatives()
    elif args.command == "audit-native-negatives":
        from .native import audit_native_negatives
        result = audit_native_negatives()
    elif args.command == "build-sop":
        from .sop import build_sop
        result = build_sop()
    elif args.command == "audit-sop":
        from .sop import audit_sop
        result = audit_sop()
    elif args.command == "validate-native-platform":
        from .platform_validation import validate_native_platform
        result = validate_native_platform()
    elif args.command == "audit-native-platform":
        from .platform_validation import audit_native_platform
        result = audit_native_platform()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not isinstance(result, dict) or result.get("passed", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
