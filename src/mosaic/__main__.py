"""Command-line entry for text-to-XDL conversion and review."""
import argparse
import json
from pathlib import Path

from .engine import ConversionSpec, ROLES, Runtime, convert, resume
from .sources import load_text_sources


def main(argv=None):
    parser = argparse.ArgumentParser(prog="mosaic", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    extract = commands.add_parser("extract", help="Convert literal .txt/.md/JSON/JSONL experimental procedures")
    extract.add_argument("paths", nargs="+", type=Path)
    extract.add_argument("--output-dir", default="outputs")
    extract.add_argument("--registry", type=Path, help="library_registry.json from a previous conversion")
    extract.add_argument("--no-curation", action="store_true")
    extract.add_argument("--max-calls", type=int, help="Default: 3 per source + 2 for the whole batch")
    extract.add_argument("--max-seconds", type=int, default=900)
    extract.add_argument("--workers", type=int, default=3)
    extract.add_argument("--model", action="append", default=[], metavar="ROLE=MODEL")
    extract.add_argument("--publish-db", type=Path)
    again = commands.add_parser("resume", help="Resume an unchanged conversion, optionally without HTTP")
    again.add_argument("run_dir", type=Path)
    again.add_argument("--offline", action="store_true")
    check = commands.add_parser("verify", help="Verify frozen sources, evidence and XDL roundtrips")
    check.add_argument("run_dir", type=Path)
    evaluate = commands.add_parser("evaluate", help="Score actual XDL conservation and optional expert fact references")
    evaluate.add_argument("run_dir", type=Path)
    evaluate.add_argument("--reference", type=Path, action="append", default=[])
    evaluate.add_argument("--output", type=Path)
    review = commands.add_parser("publish", help="Import conversion results into the optional review database")
    review.add_argument("run_dir", type=Path)
    review.add_argument("--db", type=Path, required=True)
    commands.add_parser("api-check", help="Check configured API with a nonce and invalid-key control")
    args = parser.parse_args(argv)
    if args.command == "extract":
        models = {}
        for value in args.model:
            role, separator, model = value.partition("=")
            if not separator or role not in ROLES or not model:
                parser.error("--model requires ROLE=MODEL; roles: " + ", ".join(ROLES))
            models[role] = model
        result = convert(ConversionSpec(output_dir=args.output_dir, registry_path=str(args.registry) if args.registry else None,
            curate=not args.no_curation, max_calls=args.max_calls, max_seconds=args.max_seconds, workers=args.workers, models=models),
            runtime=Runtime(records=load_text_sources(args.paths)))
        if args.publish_db:
            from .audit_bridge import publish
            result["publication"] = publish(result["run_dir"], args.publish_db)
    elif args.command == "resume":
        result = resume(args.run_dir, offline=args.offline)
    elif args.command == "verify":
        from .verification import verify_conversion
        result = verify_conversion(args.run_dir)
    elif args.command == "publish":
        from .audit_bridge import publish
        result = publish(args.run_dir, args.db)
    elif args.command == "evaluate":
        from datetime import datetime, timezone
        from .evaluation import evaluate_run
        from .store import atomic_json
        result = evaluate_run(args.run_dir, args.reference)
        output = args.output or Path("outputs/reports") / (args.run_dir.name + "_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + ".json")
        atomic_json(output, result)
        result["report"] = str(output.resolve())
    else:
        from .protocol.api import probe
        result = probe()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result.get("passed") is False else 2 if result.get("failures", 0) else 0


if __name__ == "__main__":
    raise SystemExit(main())
