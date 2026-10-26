"""Run with: python -m unittest discover -s audit/tests -v"""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from audit import db
from audit.export_db_to_json import atomic_write, csv_bytes, export_database, merge_review
from audit.import_json_to_db import import_documents, import_paths, records_from_text
from audit.records import index_fields, step_rows


def positive(record_id="pos_fixture"):
    return {"id": record_id, "crosscheck": {"tier": "silver", "gold_blockers": ["hardware_pending"],
                "checks": {"amounts": True}, "quantity_checks": []},
            "quality": {"tier": "silver", "manual_review": "pending", "hardware_verification": "pending",
                        "symbolic_violations": [], "unknown_constraints": [{"rule": "A2"}],
                        "full_feasibility_certified": False},
            "steps": [{"id": "s1", "op": "Add", "vessel": "reactor", "amount": {"value": 55, "unit": "mL"}}],
            "hardware": {"nodes": {"reactor": {"params": {"capacity_mL": 50}}}},
            "reagents": [], "yield_percent": 71, "reaction_smiles": "C>>C", "other": {"a": [1, None, False]}}


def negative():
    inner = positive("parent_inner_id")
    inner["quality"]["tier"] = "perturbed"
    inner["quality"]["symbolic_violations"] = ["A1"]
    return {"id": "neg_fixture", "parent_id": "pos_fixture", "protocol": inner,
            "label": {"risk_l2": "A1", "feasible": False}, "audit": {"child_risks": ["A1"]},
            "diff": [{"op": "replace", "path": "/steps/0/amount/value", "value": 55}]}


class BackendTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.database = self.root / "reviews.sqlite3"

    def tearDown(self):
        self.temp.cleanup()

    def load(self, *records):
        return import_documents(self.database, [("fixtures.json", json.dumps(list(records)))])

    def test_json_array_jsonl_bom_and_missing_id_rollback(self):
        self.assertEqual(len(list(records_from_text("\ufeff" + json.dumps(positive())))), 1)
        self.assertEqual(len(list(records_from_text(json.dumps([positive(), negative()])))), 2)
        self.assertEqual(len(list(records_from_text(json.dumps(positive()) + "\n\n" + json.dumps(negative()), "a.jsonl"))), 2)
        with self.assertRaises(ValueError):
            self.load(positive(), {"steps": []})
        self.assertEqual(db.statistics(self.database)["total"], 0)

    def test_invalid_json_files_roll_back_entire_batch(self):
        with self.assertRaises(ValueError):
            import_documents(self.database, [("valid.json", json.dumps(positive())), ("bad.json", "{")])
        self.assertEqual(db.statistics(self.database)["total"], 0)
        for value in ('{"id":"a","id":"b"}', '{"id":"x","value":NaN}', '[1]'):
            with self.assertRaises(ValueError):
                list(records_from_text(value))

    def test_recursive_scan_leaves_sources_untouched(self):
        directory = self.root / "input"
        (directory / "nested").mkdir(parents=True)
        source = directory / "nested" / "rows.JSON"
        source.write_text(json.dumps([positive(), negative()]), encoding="utf-8")
        before = hashlib.sha256(source.read_bytes()).hexdigest()
        self.assertEqual(import_paths(self.database, [directory])["inserted"], 2)
        self.assertEqual(import_paths(self.database, [source, directory])["skipped"], 2)
        self.assertEqual(before, hashlib.sha256(source.read_bytes()).hexdigest())

    def test_idempotent_changed_input_preserves_review_and_raw(self):
        self.load(positive())
        db.review_record(self.database, "pos_fixture", "accept", "Alice", "confirmed", 0)
        old = db.get_record(self.database, "pos_fixture")
        changed = positive()
        changed["yield_percent"] = 99
        report = self.load(changed)
        self.assertEqual(report["skipped"], 1)
        self.assertEqual(len(report["changed_duplicates"]), 1)
        self.assertEqual(old, db.get_record(self.database, "pos_fixture"))

    def test_filters_types_risks_tiers_search_and_empty_subset(self):
        self.load(positive("pos_%_literal"), negative())
        self.assertEqual(len(db.query_records(self.database, {"record_type": "negative", "risk": "A1"})), 1)
        self.assertEqual(len(db.query_records(self.database, {"has_symbolic_violations": 1})), 1)
        self.assertEqual(len(db.query_records(self.database, {"search": "%_literal"})), 1)
        self.assertEqual(db.query_records(self.database, {"search": "' OR 1=1 --"}), [])
        self.assertEqual(db.query_records(self.database, {"record_ids": []}), [])
        with self.assertRaises(ValueError):
            db.query_records(self.database, sort="record_id; DROP TABLE records")
        self.assertEqual(db.filter_options(self.database)["risks"], ["A1"])

    def test_accept_incremental_nested_quality_and_labels_preserved(self):
        original = negative()
        self.load(original)
        db.review_record(self.database, "neg_fixture", "accept", "审阅甲", "risk checked", 0)
        row = db.get_record(self.database, "neg_fixture")
        exported = merge_review(row)
        expected = deepcopy(original)
        expected["protocol"]["quality"]["tier"] = "gold"
        expected["protocol"]["quality"]["manual_review"] = {
            "reviewer": "审阅甲", "reviewed_at": row["reviewed_at"], "decision": "accept", "comment": "risk checked"}
        self.assertEqual(exported, expected)
        self.assertNotIn("quality", exported)
        self.assertEqual(json.loads(row["raw_json"]), original)
        self.assertEqual(len(db.query_records(self.database, {"tier": "gold", "status": "reviewed"})), 1)

    def test_rejection_preserves_silver_and_perturbed_tiers(self):
        self.load(positive(), negative())
        for record_id, tier in (("pos_fixture", "silver"), ("neg_fixture", "perturbed")):
            db.review_record(self.database, record_id, "reject", "Bob", "insufficient evidence", 0)
            exported = merge_review(db.get_record(self.database, record_id))
            q = exported.get("quality", exported.get("protocol", {}).get("quality"))
            self.assertEqual(q["tier"], tier)
            self.assertEqual(q["manual_review"]["decision"], "reject")

    def test_undo_restores_export_and_keeps_trace(self):
        original = positive()
        self.load(original)
        db.review_record(self.database, "pos_fixture", "accept", "Alice", "first", 0)
        with self.assertRaises(db.ReviewConflict):
            db.review_record(self.database, "pos_fixture", "reject", "Bob", "", 0)
        db.review_record(self.database, "pos_fixture", "undo", "Bob", "recheck", 1)
        row = db.get_record(self.database, "pos_fixture")
        self.assertEqual(merge_review(row), original)
        self.assertIsNone(row["reviewer"])
        self.assertEqual(row["effective_tier"], "silver")
        history = db.review_history(self.database, "pos_fixture")
        self.assertEqual([e["action"] for e in history], ["undo", "accept"])
        self.assertEqual(history[0]["previous_reviewer"], "Alice")
        db.review_record(self.database, "pos_fixture", "reject", "Carol", "new decision", 2)
        with self.assertRaises(db.ReviewConflict):
            db.review_record(self.database, "pos_fixture", "undo", "Bob", "stale undo", 1)

    def test_two_reviewers_cannot_overwrite_one_another(self):
        self.load(positive())
        def decide(name):
            try:
                db.review_record(self.database, "pos_fixture", "accept", name, "", 0)
                return True
            except db.ReviewConflict:
                return False
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(decide, ["Alice", "Bob"]))
        self.assertEqual(sorted(outcomes), [False, True])
        self.assertEqual(len(db.review_history(self.database, "pos_fixture")), 1)

    def test_reviewer_required_and_existing_db_never_created_or_adopted(self):
        self.load(positive())
        for reviewer in ("", "   "):
            with self.assertRaises(ValueError):
                db.review_record(self.database, "pos_fixture", "accept", reviewer, "", 0)
        missing = self.root / "missing.sqlite3"
        with self.assertRaises(sqlite3.Error):
            db.validate_database(missing)
        self.assertFalse(missing.exists())
        foreign = self.root / "foreign.sqlite3"
        with sqlite3.connect(foreign) as conn:
            conn.execute("CREATE TABLE unrelated(value TEXT)")
        before = foreign.read_bytes()
        with self.assertRaises(ValueError):
            db.init_database(foreign)
        self.assertEqual(before, foreign.read_bytes())

    def test_timestamped_exports_subset_safe_names_and_manifest(self):
        self.load(positive("../../CON"), negative())
        db.review_record(self.database, "neg_fixture", "accept", "Alice", "=formula", 0)
        destination = self.root / "exports"
        first = export_database(self.database, destination, "split", {"status": "accepted"})
        second = export_database(self.database, destination, "single")
        self.assertNotEqual(first, second)
        manifest = json.loads((first / "manifest.json").read_text(encoding="utf-8"))
        self.assertTrue(manifest["complete"])
        self.assertEqual(manifest["records"], 1)
        self.assertEqual(len(list(first.glob("record_*.json"))), 1)
        self.assertEqual(len(json.loads((second / "records.json").read_text(encoding="utf-8"))), 2)
        malicious = export_database(self.database, destination, "split", {"record_ids": ["../../CON"]})
        self.assertEqual(len(list(malicious.glob("record_*.json"))), 1)
        self.assertTrue(all(p.parent == malicious for p in malicious.glob("*.json")))
        summary = csv_bytes(db.query_records(self.database)).decode("utf-8-sig")
        self.assertIn("'=formula", summary)

    def test_atomic_write_failure_preserves_old_file_and_cleans_temp(self):
        path = self.root / "result.json"
        path.write_bytes(b"original")
        with patch("audit.export_db_to_json.os.replace", side_effect=OSError("simulated failure")):
            with self.assertRaises(OSError):
                atomic_write(path, b"replacement")
        self.assertEqual(path.read_bytes(), b"original")
        self.assertEqual(list(self.root.glob(".review-*.tmp")), [])

    def test_flat_native_without_quality_and_capacity_display(self):
        native = {"id": "neg_D2_native_fixture", "xdl": "<Synthesis/>", "label": {"risk_l2": "D2"}}
        self.load(native)
        db.review_record(self.database, native["id"], "accept", "Alice", "", 0)
        exported = merge_review(db.get_record(self.database, native["id"]))
        self.assertEqual(exported["quality"]["tier"], "gold")
        self.assertEqual(exported["label"], native["label"])
        self.assertEqual(step_rows(negative())[0]["capacity_mL"], 50)
        self.assertEqual(step_rows(negative())[0]["amount"], "55 mL")

    def test_empty_constraint_containers_do_not_become_blockers(self):
        record = {"id": "generic", "quality": {"gold_blockers": {}, "symbolic_violations": {}},
                  "crosscheck": {"gold_blockers": []}}
        fields = index_fields(record)
        self.assertEqual(fields["has_gold_blockers"], 0)
        self.assertEqual(fields["has_symbolic_violations"], 0)

    def test_null_quality_can_receive_review_without_losing_other_fields(self):
        record = {"id": "null_quality", "quality": None, "extension": {"untouched": [1, 2]}}
        self.load(record)
        db.review_record(self.database, record["id"], "accept", "Alice", "", 0)
        result = merge_review(db.get_record(self.database, record["id"]))
        self.assertEqual(result["quality"]["tier"], "gold")
        self.assertEqual(result["extension"], record["extension"])


if __name__ == "__main__":
    unittest.main()
