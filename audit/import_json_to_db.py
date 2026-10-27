"""One-way JSON/JSONL -> immutable SQLite snapshots; usable without Streamlit."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import sqlite3

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from audit import db
from audit.records import index_fields


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"JSON 含重复键：{key}")
        result[key] = value
    return result


def _constant(value):
    raise ValueError(f"JSON 不允许非有限数：{value}")


def parse_json(text):
    return json.loads(text, object_pairs_hook=_object, parse_constant=_constant)


def records_from_text(text, filename="upload.json"):
    """Yield objects from a single object, array, or line-delimited JSON file."""
    text = text.lstrip("\ufeff")
    if Path(filename).suffix.lower() == ".jsonl":
        for number, line in enumerate(text.splitlines(), 1):
            if line.strip():
                try:
                    record = parse_json(line)
                except ValueError as exc:
                    raise ValueError(f"{filename}:{number}: {exc}") from exc
                if not isinstance(record, dict):
                    raise ValueError(f"{filename}:{number}: 每行必须是一个记录对象")
                yield record
    else:
        try:
            data = parse_json(text)
        except ValueError as exc:
            raise ValueError(f"{filename}: {exc}") from exc
        values = data if isinstance(data, list) else [data]
        for number, record in enumerate(values, 1):
            if not isinstance(record, dict):
                raise ValueError(f"{filename}: 第 {number} 条必须是记录对象")
            yield record


def scan_files(paths):
    found = set()
    for item in paths:
        path = Path(item).expanduser().resolve()
        if path.is_file() and path.suffix.lower() in (".json", ".jsonl"):
            found.add(path)
        elif path.is_dir():
            found.update(p.resolve() for p in path.rglob("*")
                         if p.is_file() and p.suffix.lower() in (".json", ".jsonl"))
        else:
            raise ValueError(f"找不到 JSON/JSONL 文件或目录：{path}")
    if not found:
        raise ValueError("目录内没有 JSON/JSONL 文件。")
    return sorted(found)


def import_documents(database, documents, record_type="auto", *, reject_changed=False):
    """All documents commit together. Existing IDs are always skipped, even if changed."""
    if record_type not in ("auto", "positive", "negative", "other"):
        raise ValueError("不支持的记录类型")
    db.init_database(database)
    report = {"files": 0, "inserted": 0, "skipped": 0, "changed_duplicates": []}
    with db.connect(database) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        for source, text in documents:
            report["files"] += 1
            for record in records_from_text(text, source):
                record_id = record.get("id")
                if not isinstance(record_id, str) or not record_id.strip():
                    raise ValueError(f"{source}: 记录缺少非空字符串 id；整批导入已回滚。")
                raw = json.dumps(record, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
                canonical = json.dumps(record, ensure_ascii=False, allow_nan=False, sort_keys=True,
                                       separators=(",", ":"))
                digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
                old = conn.execute("SELECT raw_sha256 FROM records WHERE record_id=?", (record_id,)).fetchone()
                if old is not None:
                    report["skipped"] += 1
                    if old[0] != digest:
                        if reject_changed:
                            raise ValueError(f"不可变记录 ID 内容冲突：{record_id}；整批导入已回滚。")
                        report["changed_duplicates"].append({"record_id": record_id, "source": source})
                    continue
                fields = index_fields(record)
                if record_type != "auto":
                    fields["record_type"] = record_type
                conn.execute("INSERT INTO records (record_id,raw_json,raw_sha256,tier,record_type,parent_id,"
                             "has_gold_blockers,symbolic_violations,has_symbolic_violations,source_file,imported_at) "
                             "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                             (record_id, raw, digest, fields["tier"], fields["record_type"], fields["parent_id"],
                              fields["has_gold_blockers"], fields["symbolic_violations"],
                              fields["has_symbolic_violations"], str(source), db.utc_now()))
                conn.executemany("INSERT INTO record_risks(record_id,risk) VALUES (?,?)",
                                 [(record_id, risk) for risk in fields["risk_codes"]])
                report["inserted"] += 1
    return report


def import_paths(database, paths, record_type="auto", *, reject_changed=False):
    files = scan_files(paths)
    documents = ((str(path), path.read_text(encoding="utf-8-sig")) for path in files)
    return import_documents(database, documents, record_type, reject_changed=reject_changed)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", help="JSON、JSONL 文件或递归扫描的目录")
    parser.add_argument("--db", default=str(db.DEFAULT_DB))
    parser.add_argument("--kind", choices=("auto", "positive", "negative", "other"), default="auto")
    args = parser.parse_args()
    try:
        report = import_paths(args.db, args.paths, args.kind)
    except (ValueError, OSError, sqlite3.Error) as exc:
        parser.exit(1, f"导入失败：{exc}\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
