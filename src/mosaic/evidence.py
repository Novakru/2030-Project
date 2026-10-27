"""Exact source locators and explicit uncertainty; no inferred source facts."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from protocol_risk.io import digest


@dataclass(frozen=True)
class SourceSpan:
    source_id: str
    source_sha256: str
    start: int
    end: int
    quote: str

    @classmethod
    def locate(cls, source_id, text, quote, *, start=None):
        if not isinstance(quote, str) or not quote:
            raise ValueError("Evidence quote must be nonempty")
        position = text.find(quote) if start is None else start
        if not isinstance(position, int) or isinstance(position, bool) or position < 0 or text[position:position + len(quote)] != quote:
            raise ValueError("Evidence quote does not match source")
        return cls(source_id, digest(text), position, position + len(quote), quote)

    def to_dict(self):
        return asdict(self)


def chunk_document(source_id, text, size=6000, overlap=400):
    if size <= 0 or not 0 <= overlap < size:
        raise ValueError("Invalid chunk size or overlap")
    chunks = []
    for start in range(0, len(text), size - overlap):
        quote = text[start:start + size]
        chunks.append(SourceSpan.locate(source_id, text, quote, start=start).to_dict())
        if start + size >= len(text):
            break
    return chunks


def cited_claim(source_id: str, text: str, field: str, value: Any, quote: str):
    return {"field": field, "value": value, "evidence": SourceSpan.locate(source_id, text, quote).to_dict(),
            "status": "source_reported", "human_verified": False}


def validate_span(citation, sources):
    text = sources.get(citation.get("source_id"))
    start, end = citation.get("start"), citation.get("end")
    if (not isinstance(text, str) or digest(text) != citation.get("source_sha256")
            or any(not isinstance(v, int) or isinstance(v, bool) for v in (start, end))
            or not 0 <= start < end <= len(text) or text[start:end] != citation.get("quote")):
        raise ValueError("Evidence does not match a pinned source")
    return text[start:end]
