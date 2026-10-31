"""Deterministic document preparation: sentences, characterization data, quantity tags.

Output (``Prepared``) is the single coordinate system shared by every agent,
validator, evaluator and compiler: sentence IDs (S1..), quantity IDs (Q1..)
and character offsets into the frozen source text.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from .quantities import Quantity, tag_quantities

TAGGER_VERSION = "pg-tagger/1"

_ABBREV = r"(?:approx|ca|e\.g|i\.e|vs|Fig|Figs|No|Ex|Eq|ref|cf|resp|et al|wt|aq|sat|conc|soln|temp|vol|min|hr|hrs|equiv|eq|g|mg|ml|mL|C|M|N)\."
# Split after . ! ? ; 。 when followed by space + uppercase/digit/quote/bracket-begins-a-name, or CJK.
_SPLIT = re.compile(r"(?<=[.!?。！？])\s+(?=[A-Z0-9\[\"'“(（]|[a-z]{1,4}-[A-Za-z0-9]|[\u4e00-\u9fff])|(?<=[。！？])(?=\S)")

# Characterization blocks: from the trigger to the end of the sentence (or text).
_CHAR_TRIGGERS = re.compile(
    r"(?:\b(?:1H|13C|19F|31P)[- ]?NMR\s*(?:\(|:|δ|\[)|\bHRMS\b|\bHR-MS\b|\bESI[- ]?MS\b|\bCI MS\b|\bEI MS\b|"
    r"\bLC-?MS\s*\(|\bMS\s*\((?:ESI|EI|CI)|\bm/z\b|\bIR\s*\((?:KBr|neat|film|ATR)|\bmp\s*[:=]?\s*\d|\bm\.p\.|"
    r"\[α\]|\[a\]D|\bR[fF]\s*[=:]|\bAnal\.\s*Calc|\bElemental analysis|δ\s*\d)"
)


@dataclass
class Sentence:
    id: str
    start: int
    end: int
    text: str
    kind: str = "procedure"  # procedure | characterization


@dataclass
class Prepared:
    source_id: str
    text: str
    sha256: str
    sentences: list[Sentence]
    quantities: list[Quantity]
    characterization_spans: list[tuple[int, int]] = field(default_factory=list)
    tagger_version: str = TAGGER_VERSION

    @property
    def q(self):
        return {q.id: q for q in self.quantities}

    @property
    def s(self):
        return {s.id: s for s in self.sentences}

    def sentence_at(self, offset):
        for s in self.sentences:
            if s.start <= offset < s.end:
                return s.id
        return self.sentences[-1].id if self.sentences else ""

    def procedure_quantities(self):
        return [q for q in self.quantities if self.s[q.sentence].kind == "procedure"]

    def render(self):
        """Text for agents: one sentence per line, quantities wrapped as «Q3|25.4 g»."""
        lines = []
        for s in self.sentences:
            if s.kind == "characterization":
                lines.append(f"[{s.id}] (characterization data omitted)")
                continue
            chunk, cursor = [], s.start
            for q in self.quantities:
                if s.start <= q.start < s.end:
                    chunk.append(self.text[cursor:q.start])
                    chunk.append(f"«{q.id}|{self.text[q.start:q.end]}»")
                    cursor = q.end
            chunk.append(self.text[cursor:s.end])
            lines.append(f"[{s.id}] " + "".join(chunk).strip())
        return "\n".join(lines)

    def quantity_table(self):
        rows = []
        for q in self.procedure_quantities():
            value = q.text if q.value is None else (f"{q.value:g}" + (f"–{q.upper:g}" if q.upper is not None else ""))
            rows.append(f"{q.id}: {q.text!r} kind={q.kind} value={value} unit={q.unit} in {q.sentence}")
        return "\n".join(rows)

    def as_dict(self):
        return {
            "source_id": self.source_id, "sha256": self.sha256, "tagger_version": self.tagger_version,
            "sentences": [s.__dict__ for s in self.sentences],
            "quantities": [q.as_dict() for q in self.quantities],
        }


def split_sentences(text):
    spans, cursor = [], 0
    for m in _SPLIT.finditer(text):
        cut = m.start()
        piece = text[cursor:cut]
        # Do not split after known abbreviations followed by lowercase/number/paren continuation.
        tail = piece.rstrip()
        if re.search(r"(?:^|\s)" + _ABBREV + r"$", tail) and re.match(r"\s*[(a-z0-9]", text[m.end():m.end() + 2]):
            continue
        if re.search(r"\b(?:e\.g|i\.e|et al|approx|ca|Fig|No|vs)\.$", tail) or re.search(r"(?:\b[A-Z]\.){2,}$", tail):
            continue
        if piece.strip():
            spans.append((cursor, cut))
        cursor = m.end()
    if text[cursor:].strip():
        spans.append((cursor, len(text)))
    # trim whitespace
    out = []
    for a, b in spans:
        while a < b and text[a].isspace():
            a += 1
        while b > a and text[b - 1].isspace():
            b -= 1
        out.append((a, b))
    return out


def _characterization_spans(text, sentence_spans):
    spans = []
    for a, b in sentence_spans:
        m = _CHAR_TRIGGERS.search(text, a, b)
        if not m:
            continue
        # A trigger after a colon/semicolon/comma inside a product sentence: cut there.
        start = m.start()
        lead = text[a:start]
        cut = max(lead.rfind(":"), lead.rfind(";"))
        if cut >= 0 and start - (a + cut) < 6:
            start = a + cut + 1
        spans.append((start, len(text) if _dense_numbers(text[b:]) else b))
    merged = []
    for s, e in sorted(spans):
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(e, merged[-1][1]))
        else:
            merged.append((s, e))
    return merged


def _dense_numbers(rest):
    """True when the rest of the text is still a characterization tail (δ lists, MS)."""
    if not rest.strip():
        return False
    numbers = len(re.findall(r"\d", rest))
    return numbers / max(1, len(rest)) > 0.25 and len(rest) < 4000


def prepare(source_id, text):
    text = text.replace("\r\n", "\n")
    raw = split_sentences(text)
    char_spans = _characterization_spans(text, raw)
    # Split sentences at characterization boundaries so the procedure part remains visible.
    pieces = []
    for a, b in raw:
        cuts = [a]
        for s, e in char_spans:
            if a < s < b:
                cuts.append(s)
        cuts.append(b)
        for x, y in zip(cuts, cuts[1:]):
            seg = text[x:y]
            lstrip = len(seg) - len(seg.lstrip())
            x2, y2 = x + lstrip, x + len(seg.rstrip())
            if y2 > x2:
                pieces.append((x2, y2))
    sentences = []
    for i, (a, b) in enumerate(pieces, 1):
        kind = "characterization" if any(s <= a and b <= e for s, e in char_spans) else "procedure"
        sentences.append(Sentence(id=f"S{i}", start=a, end=b, text=text[a:b], kind=kind))

    def sentence_of(offset):
        for s in sentences:
            if s.start <= offset < s.end:
                return s.id
        return sentences[-1].id if sentences else ""

    quantities = tag_quantities(text, sentence_of=sentence_of, skip_spans=char_spans)
    return Prepared(source_id=source_id, text=text, sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
                    sentences=sentences, quantities=quantities, characterization_spans=char_spans)
