"""SQLite persistence. Imports preserve snapshots; reviews use optimistic locking."""
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Dict, Optional

APP_ID = 0x52564131  # RVA1
SCHEMA_VERSION = 2
STATUSES = ("pending", "accepted", "rejected")
EFFECTIVE_TIER = "CASE WHEN status = 'accepted' THEN 'gold' ELSE tier END"
_DATA_DIR = Path(__file__).resolve().parent / "data"
DEFAULT_DB = _DATA_DIR / "reviews.sqlite3"

SCHEMA = """
CREATE TABLE records (
    record_id TEXT PRIMARY KEY, raw_json TEXT NOT NULL, raw_sha256 TEXT NOT NULL,
    tier TEXT NOT NULL, record_type TEXT NOT NULL,
    has_gold_blockers INTEGER NOT NULL CHECK(has_gold_blockers IN (0,1)),
    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','accepted','rejected')),
    reviewer TEXT, reviewed_at TEXT, comment TEXT NOT NULL DEFAULT '',
    source_file TEXT NOT NULL, imported_at TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 0,
    CHECK ((status='pending' AND reviewer IS NULL AND reviewed_at IS NULL) OR
           (status!='pending' AND reviewer IS NOT NULL AND reviewed_at IS NOT NULL))
);
CREATE TABLE review_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id TEXT NOT NULL REFERENCES records(record_id),
    action TEXT NOT NULL CHECK(action IN ('accept','reject','undo')),
    reviewer TEXT NOT NULL, created_at TEXT NOT NULL, comment TEXT NOT NULL,
    previous_status TEXT NOT NULL, previous_reviewer TEXT, previous_reviewed_at TEXT,
    previous_comment TEXT NOT NULL, revision INTEGER NOT NULL
);
CREATE INDEX records_filter ON records(status,record_type,tier);
"""


class ReviewConflict(ValueError):
    """The displayed revision is stale or a decision has already been made."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


@contextmanager
def connect(path, readonly: bool = False):
    path = Path(path).expanduser().resolve()
    # mode=rw prevents an accidental empty DB when an existing path is mistyped.
    conn = sqlite3.connect(path.as_uri() + ("?mode=ro" if readonly else "?mode=rw"),
                           uri=True, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=15000")
    try:
        yield conn
    finally:
        conn.close()


def validate_database(path):
    with connect(path, readonly=True) as conn:
        if (conn.execute("PRAGMA application_id").fetchone()[0] != APP_ID or
                conn.execute("PRAGMA user_version").fetchone()[0] != SCHEMA_VERSION):
            raise ValueError("不是本审核工具的数据库，或数据库版本不兼容。请选择本工具创建的审核数据库。")
        conn.execute("SELECT record_id, raw_json, revision FROM records LIMIT 1")


def init_database(path=DEFAULT_DB):
    path = Path(path).expanduser().resolve()
    if path.exists():
        validate_database(path)
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation avoids adopting or modifying an unrelated SQLite file.
    with path.open("xb"):
        pass
    conn = sqlite3.connect(str(path), timeout=15)
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.executescript("BEGIN IMMEDIATE;\n" + SCHEMA +
                           f"\nPRAGMA application_id={APP_ID}; PRAGMA user_version={SCHEMA_VERSION}; COMMIT;")
        conn.execute("PRAGMA journal_mode=WAL")
    finally:
        conn.close()
    return path


def _where(filters: Optional[Dict] = None):
    filters = filters or {}
    clauses, params = [], []
    for key, column in (("status", "status"), ("record_type", "record_type"),
                        ("tier", EFFECTIVE_TIER), ("has_gold_blockers", "has_gold_blockers")):
        value = filters.get(key)
        if value is not None and value != "":
            if key == "status" and value == "reviewed":
                clauses.append("status != 'pending'")
            else:
                clauses.append(f"({column}) = ?")
                params.append(value)
    if filters.get("search"):
        value = str(filters["search"]).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        clauses.append("record_id LIKE ? ESCAPE '\\'")
        params.append("%" + value + "%")
    if "record_ids" in filters:
        ids = list(filters["record_ids"])
        clauses.append("record_id IN (" + ",".join("?" for _ in ids) + ")" if ids else "0")
        params.extend(ids)
    return (" WHERE " + " AND ".join(clauses) if clauses else ""), params


def query_records(path, filters=None, sort="record_id", descending=False, include_raw=False):
    order = {"record_id": "record_id", "tier": EFFECTIVE_TIER, "status": "status",
             "reviewed_at": "reviewed_at", "record_type": "record_type",
             "has_gold_blockers": "has_gold_blockers"}
    if sort not in order:
        raise ValueError("不支持的排序字段")
    columns = ("records.*" if include_raw else
               "record_id,tier,record_type,has_gold_blockers,status,reviewer,reviewed_at,"
               "comment,source_file,imported_at,revision")
    where, params = _where(filters)
    sql = (f"SELECT {columns}, {EFFECTIVE_TIER} AS effective_tier FROM records{where} "
           f"ORDER BY {order[sort]} {'DESC' if descending else 'ASC'}, record_id")
    with connect(path, readonly=True) as conn:
        return [dict(row) for row in conn.execute(sql, params)]


def get_record(path, record_id):
    with connect(path, readonly=True) as conn:
        row = conn.execute(f"SELECT *, {EFFECTIVE_TIER} AS effective_tier FROM records WHERE record_id=?",
                           (record_id,)).fetchone()
        return dict(row) if row else None


def statistics(path):
    with connect(path, readonly=True) as conn:
        result = {s: 0 for s in STATUSES}
        result.update(dict(conn.execute("SELECT status,count(*) FROM records GROUP BY status")))
        result["total"] = sum(result[s] for s in STATUSES)
        return result


def filter_options(path):
    with connect(path, readonly=True) as conn:
        return {
            "tiers": [r[0] for r in conn.execute(f"SELECT DISTINCT {EFFECTIVE_TIER} FROM records ORDER BY 1")],
        }


def review_record(path, record_id, decision, reviewer, comment="", expected_revision=None):
    if decision not in ("accept", "reject", "undo"):
        raise ValueError("不支持的审核决定")
    reviewer = reviewer.strip()
    if not reviewer:
        raise ValueError("请先填写审核人姓名。")
    if expected_revision is None:
        raise ValueError("缺少记录版本，请刷新后再审核。")
    with connect(path) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        old = conn.execute("SELECT * FROM records WHERE record_id=?", (record_id,)).fetchone()
        if old is None:
            raise ValueError("记录不存在。")
        if old["revision"] != expected_revision or ((decision == "undo") == (old["status"] == "pending")):
            raise ReviewConflict("记录已被审核或更新，请刷新页面查看最新决定。")
        now = utc_now()
        revision = old["revision"] + 1
        if decision == "undo":
            values = ("pending", None, None, "", revision, record_id, expected_revision)
        else:
            values = ("accepted" if decision == "accept" else "rejected", reviewer, now,
                      comment, revision, record_id, expected_revision)
        conn.execute("UPDATE records SET status=?,reviewer=?,reviewed_at=?,comment=?,revision=? "
                     "WHERE record_id=? AND revision=?", values)
        conn.execute("INSERT INTO review_events "
                     "(record_id,action,reviewer,created_at,comment,previous_status,previous_reviewer,"
                     "previous_reviewed_at,previous_comment,revision) VALUES (?,?,?,?,?,?,?,?,?,?)",
                     (record_id, decision, reviewer, now, comment, old["status"], old["reviewer"],
                      old["reviewed_at"], old["comment"], revision))


def review_history(path, record_id):
    with connect(path, readonly=True) as conn:
        return [dict(row) for row in conn.execute(
            "SELECT * FROM review_events WHERE record_id=? ORDER BY event_id DESC", (record_id,))]
