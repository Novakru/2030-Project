"""Explicit one-way publication of a frozen batch into the existing audit app."""
from pathlib import Path
import sys

from protocol_risk.io import ROOT, read_json

from .store import RunStore


def publish(run_dir, database):
    # The audit app intentionally remains a standalone package outside src/.
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from audit import db
    from audit.import_json_to_db import import_paths

    run_dir = Path(run_dir).resolve()
    manifest = read_json(run_dir / "manifest.json")
    RunStore(run_dir, manifest["request"]).verify()
    bundle = manifest.get("result", {}).get("review_bundle")
    if not bundle:
        raise ValueError("Run has no completed review bundle")
    files = []
    for key in ("positives", "negatives"):
        path = (run_dir / bundle[key]).resolve()
        if not path.is_relative_to(run_dir):
            raise ValueError("Review bundle escapes the run")
        files.append(path)
    report = import_paths(Path(database).resolve(), files, reject_changed=True)
    report.update(database=str(Path(database).resolve()), run_id=manifest["result"]["run_id"],
                  statistics=db.statistics(database), manual_decisions_created=0)
    return report
