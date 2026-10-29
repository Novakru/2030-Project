"""Verify byte-identical conversion output replay while all requests HTTP calls are blocked."""
import argparse
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

from mosaic.engine import resume


def snapshot(root):
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    paths = {event["artifact"] for event in manifest["events"]
             if event["stage"].startswith(("output/", "xdl/", "library/"))}
    return {relative: hashlib.sha256((root / relative).read_bytes()).hexdigest()
            for relative in sorted(paths)}


def verify_replay(run_dir):
    root = Path(run_dir).resolve()
    before = snapshot(root)
    if not before:
        raise ValueError("Run has no frozen conversion outputs to replay")
    with patch("requests.sessions.Session.request", side_effect=AssertionError("HTTP blocked during replay")):
        result = resume(root, offline=True)
    after = snapshot(root)
    changed = sorted(key for key in before.keys() | after.keys() if before.get(key) != after.get(key))
    return {"passed": not changed and result["new_model_calls"] == 0,
            "run_id": result["run_id"], "files_compared": len(before),
            "byte_identical": not changed, "changed_files": changed, "http_blocked": True,
            "new_model_calls": result["new_model_calls"],
            "cumulative_run_model_calls": result["model_calls"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = verify_replay(args.run_dir)
    content = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(content.encode("utf-8"))
    print(content, end="")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
