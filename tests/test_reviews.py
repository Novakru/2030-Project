"""Review workflow fixtures are synthetic; they never approve shipped source records."""
import copy

import pytest

from protocol_risk.io import digest, read_json, write_json, write_jsonl
from protocol_risk.reviews import CHECKS, ReviewBook, decision_status, evidence_valid, subject_hash
from protocol_risk.xdl import bind_hardware


def device():
    return {"id": "fixture_vessel", "category": "vessel", "params": {"capacity_mL": 10},
            "source_url": "https://example.test/datasheet", "wetted_materials": ["glass"],
            "ports": [], "verified": False, "verification": {"status": "source_reviewed"}}


def approval(kind, subject):
    row = {"kind": kind, "id": subject["id"], "subject_sha256": subject_hash(kind, subject),
           "review_type": "human", "reviewer": "TEST FIXTURE ONLY", "reviewed_at": "2026-10-26", "verdict": "approved",
           "checks": {k: True for k in CHECKS[kind]},
           "evidence": [{"source": "https://example.test/source", "locator": "fixture section", "finding": "Test fixture, not a real review"}]}
    if kind == "protocol":
        row["unknowns_sha256"] = digest(subject["quality"]["unknown_constraints"])
    return row


def protocol(book):
    return {"id": "fixture_protocol", "source": {"db": "ORD"}, "raw_sha256": "fixture_only",
            "reagents": [], "steps": [], "hardware": {"nodes": {"reactor": copy.deepcopy(book.devices()["fixture_vessel"])}},
            "crosscheck": {"conflicts": []}, "quality": {"tier": "silver", "unknown_constraints": [],
            "symbolic_violations": [], "full_feasibility_certified": False}}


def test_equipment_review_expires_when_a_parameter_or_scope_changes():
    subject = device()
    row = approval("hardware", subject)
    assert decision_status(row, "hardware", subject) == "approved"
    subject["params"]["capacity_mL"] = 20
    assert decision_status(row, "hardware", subject) == "stale"


@pytest.mark.parametrize("field,value", [("reviewer", None), ("reviewer", ""), ("reviewed_at", "unknown"),
                                         ("review_type", "llm"), ("evidence", [])])
def test_missing_identity_date_or_evidence_cannot_be_approved(field, value):
    subject = device()
    row = approval("hardware", subject)
    row[field] = value
    assert decision_status(row, "hardware", subject) == "invalid"


def test_boolean_looking_strings_and_numeric_flags_are_not_review_checks():
    subject = device()
    for value in ("true", 1, None):
        row = approval("hardware", subject)
        row["checks"]["parameters"] = value
        assert decision_status(row, "hardware", subject) == "incomplete"


def test_empty_templates_do_not_count_as_verified_physical_devices():
    subject = device()
    subject.update(params={"capacity_mL": None}, wetted_materials=None, verification={"status": "template_only"})
    assert decision_status(approval("hardware", subject), "hardware", subject) == "template_only"


def test_local_evidence_requires_a_matching_hash_and_workspace_path(tmp_path):
    path = tmp_path / "evidence.txt"
    path.write_text("A synthetic evidence fixture", encoding="utf-8")
    row = {"source": "evidence.txt", "sha256": digest(path.read_bytes()), "locator": "line 1", "finding": "fixture"}
    assert evidence_valid([row], tmp_path)
    path.write_text("modified", encoding="utf-8")
    assert not evidence_valid([row], tmp_path)
    row["source"] = "../outside.txt"
    assert not evidence_valid([row], tmp_path)


def test_quality_flag_alone_cannot_promote_a_protocol(tmp_path):
    book = ReviewBook(tmp_path, devices=[device()])
    subject = protocol(book)
    subject["quality"].update(tier="gold", review_record_sha256="fabricated")
    result = book.apply(subject)["quality"]
    assert result["tier"] == "silver" and result["hardware_verification"] == "pending"
    assert "review_record_sha256" not in result


def test_a_valid_protocol_review_still_needs_verified_bound_equipment(tmp_path):
    book = ReviewBook(tmp_path, devices=[device()])
    subject = protocol(book)
    book.records[("protocol", subject["id"])] = approval("protocol", subject)
    assert book.apply(subject)["quality"]["tier"] == "silver"


def test_exact_human_evidence_can_promote_and_changed_steps_expire_it(tmp_path):
    physical = device()
    write_json(tmp_path / "data/reviews/hardware/fixture_vessel.json", approval("hardware", physical))
    book = ReviewBook(tmp_path, devices=[physical])
    subject = protocol(book)
    book.records[("protocol", subject["id"])] = approval("protocol", subject)
    result = book.apply(subject)["quality"]
    assert result["tier"] == "gold" and result["manual_review"] == "approved"
    assert result["full_feasibility_certified"] is False
    subject["steps"].append({"id": "changed", "op": "Wait", "duration_s": 10})
    assert book.apply(subject)["quality"]["tier"] == "silver"


def test_changed_unknown_constraints_require_a_new_decision(tmp_path):
    book = ReviewBook(tmp_path, devices=[device()])
    subject = protocol(book)
    row = approval("protocol", subject)
    subject["quality"]["unknown_constraints"].append({"rule": "A2", "reason": "unknown"})
    assert decision_status(row, "protocol", subject) == "stale_constraints"


def test_malformed_review_is_reported_and_never_approves(tmp_path):
    path = tmp_path / "data/reviews/hardware/fixture_vessel.json"
    path.parent.mkdir(parents=True)
    path.write_text("{incomplete", encoding="utf-8")
    book = ReviewBook(tmp_path, devices=[device()])
    assert book.issues and book.status("hardware", device()) == "invalid"
    assert book.devices()["fixture_vessel"]["verified"] is False


def test_binding_override_uses_existing_device_facts_without_editing_them():
    subject = {"id": "fixture", "steps": []}
    config = {"nodes": {"reactor": "duran_youtility_125", "heater": "julabo_corio_cd200f"},
              "edges": [["reactor", "heater"]], "bindings": {"heater": "heater"}}
    bind_hardware(subject, configuration=config)
    assert subject["hardware"]["nodes"]["reactor"]["params"]["capacity_mL"] == 125
    assert subject["hardware"]["nodes"]["heater"]["verified"] is False
    config["edges"].append(["reactor", "undeclared"])
    with pytest.raises(ValueError, match="Invalid reviewed hardware"):
        bind_hardware(subject, configuration=config)


def test_packet_generation_never_overwrites_existing_reviewer_content(tmp_path, monkeypatch):
    from protocol_risk import reviews
    monkeypatch.setattr(reviews, "ROOT", tmp_path)
    monkeypatch.setattr(reviews, "load_library", lambda _: {"devices": [device()]})
    write_jsonl(tmp_path / "data/positives.jsonl", [])
    first = reviews.prepare_review_packet()
    assert first["human_reviews_created"] == 0 and first["statuses"] == {"pending": 1}
    path = tmp_path / "data/reviews/hardware/fixture_vessel.json"
    row = read_json(path)
    row["notes"] = "Keep this actual reviewer work untouched"
    write_json(path, row)
    before = path.read_bytes()
    reviews.prepare_review_packet()
    assert path.read_bytes() == before
