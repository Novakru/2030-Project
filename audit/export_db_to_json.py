"""One-way SQLite -> timestamped JSON/CSV, never synchronizing source files."""
import argparse
from copy import deepcopy
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import tempfile

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from audit import db
from audit.records import quality_owner

DEFAULT_EXPORT = Path(__file__).resolve().parent / "exports"


def timestamp():
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")


def merge_review(row):
    record = deepcopy(json.loads(row["raw_json"]))
    if row["status"] == "pending":
        return record
    owner = quality_owner(record)
    original = owner.get("quality")
    if original is not None and not isinstance(original, dict):
        raise ValueError(f"{row['record_id']}: quality 不是对象，无法增量合并；请修正源数据后另建数据库。")
    if original is None:
        owner["quality"] = {}
    q = owner["quality"]
    if row["status"] == "accepted":
        q["tier"] = "gold"
    # Rejection preserves the imported tier (silver/perturbed/unrated), including absent tier.
    q["manual_review"] = {
        "reviewer": row["reviewer"], "reviewed_at": row["reviewed_at"],
        "decision": "accept" if row["status"] == "accepted" else "reject",
        "comment": row["comment"],
    }
    return record


def json_bytes(rows):
    return (json.dumps([merge_review(row) for row in rows], ensure_ascii=False,
                       allow_nan=False, indent=2) + "\n").encode("utf-8")


def csv_bytes(rows):
    stream = io.StringIO(newline="")
    columns = ["record_id", "record_type", "parent_id", "risks", "tier", "effective_tier",
               "has_gold_blockers", "symbolic_violations", "status", "reviewer", "reviewed_at",
               "comment", "revision", "source_file", "imported_at"]
    writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        # Prevent spreadsheet formulas in untrusted identifiers, reviewer names and comments.
        safe = {k: ("'" + v if isinstance(v, str) and v.lstrip().startswith(("=", "+", "-", "@")) else v)
                for k, v in row.items()}
        writer.writerow(safe)
    return stream.getvalue().encode("utf-8-sig")


def atomic_write(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=str(path.parent), prefix=".review-", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def safe_filename(record_id):
    stem = re.sub(r"[^a-zA-Z0-9_-]", "_", record_id)[:64].strip("_") or "record"
    digest = hashlib.sha256(record_id.encode("utf-8")).hexdigest()[:16]
    return f"record_{stem}_{digest}.json"


def export_rows(rows, output=DEFAULT_EXPORT, mode="single", report_csv=True):
    if mode not in ("single", "split"):
        raise ValueError("mode 必须是 single 或 split")
    output = Path(output).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    # Each export owns an exclusive timestamped run folder. A manifest marks completion.
    run = output / ("review_" + timestamp())
    run.mkdir(exist_ok=False)
    rows = list(rows)
    # Validate every merge before writing the first output JSON.
    records = [merge_review(row) for row in rows]
    if mode == "single":
        atomic_write(run / "records.json", (json.dumps(records, ensure_ascii=False, allow_nan=False,
                                                        indent=2) + "\n").encode("utf-8"))
    else:
        used = set()
        for row, record in zip(rows, records):
            name = safe_filename(row["record_id"])
            if name in used:
                raise ValueError("输出文件名重复，请检查记录 ID")
            used.add(name)
            atomic_write(run / name, (json.dumps(record, ensure_ascii=False, allow_nan=False,
                                                 indent=2) + "\n").encode("utf-8"))
    if report_csv:
        atomic_write(run / "reviews.csv", csv_bytes(rows))
    manifest = {"exported_at": db.utc_now(), "records": len(rows), "mode": mode,
                "statuses": {s: sum(row["status"] == s for row in rows) for s in db.STATUSES},
                "record_ids": [row["record_id"] for row in rows], "complete": True}
    atomic_write(run / "manifest.json", (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    return run


def export_database(database, output=DEFAULT_EXPORT, mode="single", filters=None, report_csv=True):
    db.validate_database(database)
    rows = db.query_records(database, filters, include_raw=True)
    return export_rows(rows, output, mode, report_csv)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(db.DEFAULT_DB))
    parser.add_argument("--output", default=str(DEFAULT_EXPORT), help="父目录；自动创建带 UTC 时间戳的子目录")
    parser.add_argument("--mode", choices=("single", "split"), default="single")
    parser.add_argument("--status", choices=("all", "pending", "accepted", "rejected", "reviewed"), default="all")
    parser.add_argument("--kind", choices=("positive", "negative", "other"))
    parser.add_argument("--tier")
    parser.add_argument("--risk")
    parser.add_argument("--search")
    parser.add_argument("--blockers", choices=("yes", "no"))
    parser.add_argument("--symbolic", choices=("yes", "no"))
    parser.add_argument("--no-csv", action="store_true")
    args = parser.parse_args()
    filters = {"status": None if args.status == "all" else args.status,
               "record_type": args.kind, "tier": args.tier, "risk": args.risk, "search": args.search,
               "has_gold_blockers": None if args.blockers is None else int(args.blockers == "yes"),
               "has_symbolic_violations": None if args.symbolic is None else int(args.symbolic == "yes")}
    try:
        run = export_database(args.db, args.output, args.mode, filters, not args.no_csv)
    except (ValueError, OSError, sqlite3.Error) as exc:
        parser.exit(1, f"导出失败：{exc}\n")
    print(str(run))


if __name__ == "__main__":
    main()
