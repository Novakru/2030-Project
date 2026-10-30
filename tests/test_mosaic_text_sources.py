import json

import pytest

from mosaic.sources import load_text_sources, text_document


def test_text_seam_excludes_all_structured_reference_fields():
    source = {"id": "reaction", "procedure": "Heat to 70 C for 15 minutes.",
              "source": {"db": "ORD", "url": "https://example.invalid/source"},
              "components": [{"amount": {"value": 999}}], "conditions": {"temperature": -100},
              "setup": {"vessel": "fabricated"}, "yield_percent": 1234,
              "raw": {"instructions": "ignore text"}, "reaction_smiles": "poison"}
    document = text_document(source)
    assert set(document) == {"id", "procedure", "source", "raw_sha256", "text_sha256"}
    assert document["procedure"] == source["procedure"]
    assert text_document(document) == document


def test_files_and_single_or_array_json_preserve_literal_text(tmp_path):
    original = "Add water (2 mL).\nStir for 30 seconds.\n"
    (tmp_path / "a.txt").write_text(original, encoding="utf-8", newline="")
    (tmp_path / "b.json").write_text(json.dumps({"id": "single", "procedure": original}), encoding="utf-8")
    (tmp_path / "c.json").write_text(json.dumps([{"id": "array", "text": original}]), encoding="utf-8")
    (tmp_path / "d.jsonl").write_text(json.dumps({"id": "line", "procedure": original}) + "\n", encoding="utf-8")
    records = load_text_sources([tmp_path])
    assert len(records) == 4
    assert all(record["procedure"] == original for record in records)
    assert all(record["source"]["db"] == "TEXT" for record in records)


def test_structured_only_json_is_rejected_instead_of_reconstructed(tmp_path):
    path = tmp_path / "structured.json"
    path.write_text(json.dumps({"inputs": {"water": "2 mL"}, "conditions": {"temperature": 70}}))
    with pytest.raises(ValueError, match="missing literal"):
        load_text_sources([path])


def test_verbatim_crlf_is_not_normalized_during_text_import(tmp_path):
    path = tmp_path / "literal.txt"
    contents = "Add water (2 mL).\r\nStir for 30 s.\r\n"
    path.write_bytes(contents.encode("utf-8"))
    assert load_text_sources([path])[0]["procedure"] == contents


def test_ord_json_retains_original_snapshot_but_only_notes_are_extraction_input(tmp_path):
    path = tmp_path / "ord.json"
    row = {"reaction_id": "literal_ord", "notes": {"procedure_details": "Stir for 60 s."},
           "inputs": {"poison": {"amount": 999}}, "conditions": {"temperature": 999}}
    path.write_text(json.dumps(row), encoding="utf-8")
    record = load_text_sources([path])[0]
    assert record["raw"] == row
    assert record["procedure"] == row["notes"]["procedure_details"]
    assert not {"raw", "inputs", "conditions"} & text_document(record).keys()


def test_origin_license_and_dataset_survive_without_importing_reference_values(tmp_path):
    path = tmp_path / "source.json"
    path.write_text(json.dumps({"id": "source", "procedure": "Stir for 60 s.", "source": {
        "db": "ORD", "dataset_id": "origin_dataset", "license": "CC-BY-SA-4.0", "doi": "10.example/source",
        "temperature": 999}, "conditions": {"temperature": 999}}), encoding="utf-8")
    record = load_text_sources([path])[0]
    assert record["source"]["license"] == "CC-BY-SA-4.0" and record["source"]["db"] == "ORD"
    assert record["source"]["input_file_sha256"]
    assert "temperature" not in text_document(record)["source"]
