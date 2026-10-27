"""python -m mosaic run/resume/verify/publish."""
import argparse
import json
from pathlib import Path

from protocol_risk.io import read_json

from .audit_bridge import publish
from .engine import BuildSpec, Runtime, build, resume
from .store import RunStore


def main(argv=None):
    parser = argparse.ArgumentParser(prog="mosaic")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="Build one source-pinned multi-agent dataset")
    run.add_argument("--output-dir", default="data/mosaic")
    run.add_argument("--domain", default="chemistry.batch/1")
    run.add_argument("--positives", type=int, default=140)
    run.add_argument("--per-risk", type=int, default=12)
    run.add_argument("--text-limit", type=int, default=10)
    run.add_argument("--llm-perturbations", type=int, default=4)
    run.add_argument("--max-calls", type=int, default=60)
    run.add_argument("--workers", type=int, default=4)
    run.add_argument("--model", action="append", default=[], metavar="ROLE=MODEL")
    run.add_argument("--offline", action="store_true")
    run.add_argument("--publish-db", type=Path)
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
    if args.command == "run":
        models = {}
        for value in args.model:
            role, separator, model = value.partition("=")
            if not separator or role not in ("extractor", "critic", "apparatus_mapper", "perturber") or not model:
                parser.error("--model requires extractor|critic|apparatus_mapper|perturber=MODEL")
            models[role] = model
        spec = BuildSpec(output_dir=args.output_dir, domain=args.domain, positives=args.positives,
                         per_risk=args.per_risk, text_limit=args.text_limit,
                         llm_perturbations=args.llm_perturbations, max_calls=args.max_calls, workers=args.workers, models=models)
        result = build(spec, runtime=Runtime(offline=args.offline, progress=lambda row: print(json.dumps(row), flush=True)))
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
