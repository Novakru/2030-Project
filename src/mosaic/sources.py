"""Text documents at the generation seam; source metadata is provenance only."""
from __future__ import annotations

import copy
import json
from pathlib import Path

from mosaic.protocol.io import digest

PROVENANCE_FIELDS = {"db", "url", "dataset_id", "dataset_name", "publication_url", "doi", "patent", "path", "document_name",
    "file", "file_sha256", "input_file_sha256", "license", "reaction_id", "row_index", "row_server_url",
    "repository_revision_observed", "row_server_revision_verified", "reaction_payload_sha256", "procedure_sha256", "text_field"}


def text_document(record):
    """Drop reference measurements before any extraction implementation sees them."""
    text = record.get("procedure")
    if not isinstance(text, str) or not text.strip():
        raise ValueError("A nonempty verbatim experimental procedure is required")
    source = {key: copy.deepcopy(value) for key, value in record.get("source", {}).items() if key in PROVENANCE_FIELDS}
    return {"id": record["id"], "procedure": text, "source": source,
            "raw_sha256": record.get("raw_sha256") or digest({"text": text}),
            "text_sha256": digest(text.encode("utf-8"))}


def load_text_sources(paths):
    """Read literal documents or JSON records, without synthesizing text from fields."""
    files = []
    for value in paths:
        path = Path(value).resolve()
        if path.is_dir():
            files.extend(p for p in sorted(path.rglob("*")) if p.suffix.lower() in {".txt", ".md", ".json", ".jsonl"})
        elif path.is_file():
            files.append(path)
        else:
            raise ValueError("Source path does not exist: " + str(path))
    records, seen = [], set()
    for path in sorted(set(files)):
        with path.open(encoding="utf-8-sig", newline="") as stream:
            contents = stream.read()
        if path.suffix.lower() in {".txt", ".md"}:
            rows = [{"procedure": contents}]
        elif path.suffix.lower() == ".jsonl":
            rows = [json.loads(line) for line in contents.splitlines() if line.strip()]
        elif path.suffix.lower() == ".json":
            data = json.loads(contents)
            rows = data if isinstance(data, list) else [data]
        else:
            raise ValueError("Supported sources: .txt, .md, .json, .jsonl")
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                raise ValueError(f"{path.name} record {index + 1}: expected a JSON object")
            notes = row.get("notes") if isinstance(row.get("notes"), dict) else {}
            text = row.get("procedure", row.get("text", notes.get("procedure_details")))
            if not isinstance(text, str) or not text.strip():
                raise ValueError(f"{path.name} record {index + 1}: missing literal procedure/text")
            identifier = row.get("id", row.get("reaction_id")) or "text_" + digest({"text": text, "file": path.name, "row": index})[:20]
            if not isinstance(identifier, str) or identifier in seen:
                raise ValueError("Duplicate or invalid source identifier: " + str(identifier))
            seen.add(identifier)
            raw = {"text": text} if path.suffix.lower() in {".txt", ".md"} else copy.deepcopy(row)
            upstream = row.get("source") if isinstance(row.get("source"), dict) else {}
            provenance = {key: copy.deepcopy(value) for key, value in upstream.items() if key in PROVENANCE_FIELDS}
            source = {"db": "TEXT", "url": path.as_uri(), **provenance, "document_name": path.name,
                      "input_file_sha256": digest(path.read_bytes()), "path": str(path)}
            source.setdefault("file_sha256", source["input_file_sha256"])
            records.append({"id": identifier, "procedure": text, "raw": raw, "raw_sha256": digest(raw), "source": source})
    if not records:
        raise ValueError("No text documents found")
    return records
