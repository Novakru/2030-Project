"""Review conversion snapshots without changing the source JSON or replay files."""
import json
from pathlib import Path

import pytest

from audit import db
from audit.export_db_to_json import export_database
from audit.import_json_to_db import import_documents, import_paths
from mosaic.audit_bridge import publish
from tests.legacy.test_conversion import convert_text


def record(identifier="conversion_1"):
    return {"id": identifier, "record_type": "positive", "source_text": "Stir overnight.",
            "quality": {"tier": "silver"}, "steps": [{"op": "Mix", "parameters": {"method": "stir"}}]}


def imported(tmp_path):
    path = tmp_path / "records.json"
    path.write_text(json.dumps([record()]), encoding="utf-8")
    database = tmp_path / "review.sqlite3"
    import_paths(database, [path])
    return path, database


def test_review_is_persistent_idempotent_and_export_is_the_only_json_update(tmp_path):
    source, database = imported(tmp_path)
    before = source.read_bytes()
    row = db.get_record(database, "conversion_1")
    db.review_record(database, row["record_id"], "accept", "Expert", "忠实表达", row["revision"])
    assert import_paths(database, [source])["skipped"] == 1
    assert db.get_record(database, row["record_id"])["reviewer"] == "Expert"
    first = export_database(database, tmp_path / "exports")
    second = export_database(database, tmp_path / "exports", mode="split")
    assert first != second
    output = json.loads((first / "records.json").read_text(encoding="utf-8"))[0]
    assert output["quality"]["tier"] == "gold"
    assert output["quality"]["manual_review"]["decision"] == "accept"
    assert output["steps"] == record()["steps"] and source.read_bytes() == before


def test_concurrent_or_repeated_review_is_rejected_and_undo_is_logged(tmp_path):
    _, database = imported(tmp_path)
    db.review_record(database, "conversion_1", "reject", "A", "需核对", 0)
    with pytest.raises(db.ReviewConflict):
        db.review_record(database, "conversion_1", "accept", "B", "", 0)
    rejected = db.get_record(database, "conversion_1")
    assert rejected["effective_tier"] == "silver"
    db.review_record(database, "conversion_1", "undo", "B", "", rejected["revision"])
    assert db.get_record(database, "conversion_1")["status"] == "pending"
    assert [event["action"] for event in db.review_history(database, "conversion_1")] == ["undo", "reject"]


def test_bad_import_rolls_back_and_changed_identity_cannot_overwrite_review(tmp_path):
    _, database = imported(tmp_path)
    with pytest.raises(ValueError):
        import_documents(database, [("batch.json", json.dumps([record("another"), {}]))])
    assert db.statistics(database)["total"] == 1
    changed = {**record(), "source_text": "Different source"}
    with pytest.raises(ValueError, match="内容冲突"):
        import_documents(database, [("changed.json", json.dumps(changed))], reject_changed=True)
    assert json.loads(db.get_record(database, "conversion_1")["raw_json"])["source_text"] == "Stir overnight."


def test_opening_an_existing_database_never_creates_a_file_on_a_typo(tmp_path):
    missing = tmp_path / "typo.sqlite3"
    with pytest.raises(Exception):
        db.validate_database(missing)
    assert not missing.exists()


def test_conversion_publication_is_explicit_and_does_not_create_review_decisions(tmp_path):
    result = convert_text(tmp_path)
    database = tmp_path / "reviews.sqlite3"
    published = publish(result["run_dir"], database)
    assert published["inserted"] == 1 and published["manual_decisions_created"] == 0
    assert db.statistics(database)["pending"] == 1
    assert publish(Path(result["run_dir"]), database)["skipped"] == 1
