"""python -m mosaic run/resume/verify/publish."""
import argparse
import json
from pathlib import Path

from protocol_risk.io import read_json

from .audit_bridge import publish
from .engine import BuildSpec, Runtime, build, resume
from .store import RunStore
from .sources import load_text_sources


def main(argv=None):
    parser = argparse.ArgumentParser(prog="mosaic")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="Build a dataset exclusively from literal source procedures")
    extract = commands.add_parser("extract", help="Convert .txt/.md/JSON literal procedures into XDL review records")
    extract.add_argument("paths", nargs="+", type=Path)
    run.add_argument("--input", action="append", type=Path, help="Text files/directories; defaults to ORD procedure text")
    run.add_argument("--positives", type=int, default=100)
    run.add_argument("--per-risk", type=int, default=10)
    run.add_argument("--source-limit", type=int, default=0, help="Maximum distinct text attempts; 0 = four times target")
    run.add_argument("--llm-perturbations", type=int, default=4)
    run.add_argument("--include-reference-supplements", action="store_true", help="Explicitly add separately labelled SOP/native-XDL references")
    for command in (run, extract):
        command.add_argument("--output-dir", default="data/mosaic")
        command.add_argument("--domain", default="chemistry.extended/1")
        command.add_argument("--registry", type=Path, help="Frozen library_registry.json from a previous run")
        command.add_argument("--no-curation", action="store_true", help="Keep deterministic observations without calling the library curator")
        command.add_argument("--max-calls", type=int, default=500)
        command.add_argument("--workers", type=int, default=4)
        command.add_argument("--model", action="append", default=[], metavar="ROLE=MODEL")
        command.add_argument("--offline", action="store_true")
        command.add_argument("--publish-db", type=Path)
    again = commands.add_parser("resume", help="Resume the same pinned run; --offline only reuses saved model responses")
    again.add_argument("run_dir", type=Path)
    again.add_argument("--offline", action="store_true")
    check = commands.add_parser("verify", help="Verify artifacts, source pins and single-intervention replay")
    check.add_argument("run_dir", type=Path)
    check.add_argument("--artifacts-only", action="store_true")
    to_db = commands.add_parser("publish", help="Explicitly import one frozen batch into SQLite")
    to_db.add_argument("run_dir", type=Path)
    to_db.add_argument("--db", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command in ("run", "extract"):
        models = {}
        for value in args.model:
            role, separator, model = value.partition("=")
            if not separator or role not in ("extractor", "critic", "apparatus_mapper", "perturber", "library_curator", "operation_expander") or not model:
                parser.error("--model requires extractor|critic|apparatus_mapper|perturber|library_curator|operation_expander=MODEL")
            models[role] = model
        inputs = args.paths if args.command == "extract" else args.input
        records = load_text_sources(inputs) if inputs else None
        positives = len(records) if args.command == "extract" else args.positives
        spec = BuildSpec(output_dir=args.output_dir, domain=args.domain, positives=positives,
                         per_risk=args.per_risk if args.command == "run" else 0,
                         source_limit=args.source_limit if args.command == "run" else len(records),
                         llm_perturbations=args.llm_perturbations if args.command == "run" else 0,
                         registry_path=str(args.registry) if args.registry else None, curate=not args.no_curation,
                         include_reference_supplements=args.command == "run" and args.include_reference_supplements,
                         max_calls=args.max_calls, workers=args.workers, models=models)
        result = build(spec, runtime=Runtime(records=records, offline=args.offline, progress=lambda row: print(json.dumps(row), flush=True)))
        if args.publish_db:
            result["audit_publication"] = publish(result["run_dir"], args.publish_db)
    elif args.command == "resume":
        result = resume(args.run_dir, offline=args.offline)
    elif args.command == "verify":
        if args.artifacts_only:
            manifest = read_json(args.run_dir / "manifest.json")
            result = {"passed": RunStore(args.run_dir, manifest["request"]).verify(), "run_dir": str(args.run_dir)}
        else:
            from .verification import verify_dataset
            result = verify_dataset(args.run_dir)
    else:
        result = publish(args.run_dir, args.db)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("passed", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
