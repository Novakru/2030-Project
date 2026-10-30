"""The single source-fact contract shared by extraction, evolution and export."""
from __future__ import annotations

import hashlib
import re
from decimal import Decimal, InvalidOperation
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


Identifier = Annotated[str, Field(pattern=r"^[A-Za-z][A-Za-z0-9_]*$", max_length=100)]


class Evidence(StrictModel):
    evidence_id: Identifier
    quote: str = Field(min_length=1)
    occurrence: int | None = Field(default=None, ge=0)
    start: int | None = Field(default=None, ge=0)
    end: int | None = Field(default=None, ge=0)


class Quantity(StrictModel):
    value_type: Literal["quantity"]
    quantity_kind: str = Field(min_length=1)
    value: str
    unit: str = Field(min_length=1)
    upper_value: str | None = None
    status: Literal["reported"] = "reported"
    basis_ref: Identifier | None = None
    basis_status: Literal["reported", "not_reported", "not_applicable"] = "not_applicable"

    @field_validator("value", "upper_value")
    @classmethod
    def decimal_literal(cls, value):
        if value is not None:
            try:
                if not Decimal(value).is_finite():
                    raise ValueError("Quantity must be finite")
            except InvalidOperation:
                raise ValueError("Quantity must be a decimal string, without a unit") from None
        return value


class TextValue(StrictModel):
    value_type: Literal["text"]
    text: str = Field(min_length=1)
    status: Literal["reported", "qualitative"] = "reported"


class ReferenceValue(StrictModel):
    value_type: Literal["reference"]
    ref: Identifier
    status: Literal["reported"] = "reported"


class MissingValue(StrictModel):
    value_type: Literal["missing"]
    status: Literal["not_reported", "ambiguous"]
    reason: str = Field(min_length=1)


Value = Annotated[Union[Quantity, TextValue, ReferenceValue, MissingValue], Field(discriminator="value_type")]


class Entity(StrictModel):
    entity_id: Identifier
    kind: Literal["material", "equipment", "sample"]
    name: str = Field(min_length=1)
    expression: str = Field(min_length=1, description="Professional equipment term, not model or rating; material name otherwise")
    evidence_ids: list[Identifier] = Field(min_length=1)


class Event(StrictModel):
    event_id: Identifier
    kind: Literal["action", "observation", "condition"]
    expression: str = Field(min_length=1, description="Single semantic action lemma; not restricted to existing XDL")
    action_surface: str = Field(min_length=1)
    participant_ids: list[Identifier] = Field(default_factory=list)
    equipment_ids: list[Identifier] = Field(default_factory=list)
    vessel_id: Identifier | None = None
    participant_order: Literal["unspecified", "reported"] = "unspecified"
    evidence_ids: list[Identifier] = Field(min_length=1)


class Fact(StrictModel):
    fact_id: Identifier
    subject_id: Identifier
    event_id: Identifier | None = None
    attribute: Identifier = Field(description="Stable semantic slot: identity, dose, relative_loading, equivalents, concentration, duration, temperature, pressure, atmosphere, method, nominal_volume; extend only for a different meaning")
    value: Value
    scope: str = Field(min_length=1, description="e.g. added_portion, per_vial, heater_setpoint, sample_actual; never guess")
    category: Literal["process", "equipment", "observation", "context", "provenance"] = "process"
    evidence_ids: list[Identifier] = Field(default_factory=list)


class Relation(StrictModel):
    relation_id: Identifier
    subject_id: Identifier
    relation: Literal["precedes", "during", "same_interval", "located_in", "applies_to", "repeat"]
    object_id: Identifier
    evidence_ids: list[Identifier] = Field(min_length=1)


class Facts(StrictModel):
    schema_version: Literal["mosaic.facts/1"]
    entities: list[Entity]
    events: list[Event] = Field(min_length=1)
    facts: list[Fact]
    relations: list[Relation] = Field(default_factory=list)
    evidence: list[Evidence]


def text_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def validate_facts(value, text):
    """Validate types, exact source occurrences, reference sorts and chronology.

    This establishes structural grounding, not scientific correctness. The
    independent verifier and expert reference evaluator cover semantics.
    """
    graph = Facts.model_validate(value).model_dump()
    entities = {e["entity_id"]: e for e in graph["entities"]}
    events = {e["event_id"]: e for e in graph["events"]}
    evidence = {e["evidence_id"]: e for e in graph["evidence"]}
    groups = [(graph["entities"], "entity_id"), (graph["events"], "event_id"),
              (graph["facts"], "fact_id"), (graph["relations"], "relation_id"), (graph["evidence"], "evidence_id")]
    all_ids = [item[key] for items, key in groups for item in items]
    if len(set(all_ids)) != len(all_ids):
        raise ValueError("IDs must be unique across the entire facts graph")
    for span in evidence.values():
        starts = [m.start() for m in re.finditer(re.escape(span["quote"]), text)]
        occurrence = span["occurrence"]
        if not starts or occurrence is None and len(starts) != 1:
            raise ValueError("Quote missing or repeated without an occurrence: " + span["evidence_id"])
        occurrence = 0 if occurrence is None else occurrence
        if occurrence >= len(starts):
            raise ValueError("Evidence occurrence does not exist")
        start, end = starts[occurrence], starts[occurrence] + len(span["quote"])
        if span["start"] not in (None, start) or span["end"] not in (None, end):
            raise ValueError("Evidence offsets disagree with literal source")
        span.update(start=start, end=end, occurrence=occurrence)
    objects = {**entities, **events}
    for items, _ in groups[:-1]:
        for item in items:
            if any(identifier not in evidence for identifier in item["evidence_ids"]):
                raise ValueError("Undefined evidence reference")
    for event in events.values():
        if len(set(event["participant_ids"])) != len(event["participant_ids"]) or len(set(event["equipment_ids"])) != len(event["equipment_ids"]):
            raise ValueError("Duplicate participant/equipment references")
        if any(i not in entities or entities[i]["kind"] == "equipment" for i in event["participant_ids"]):
            raise ValueError("An event participant must be a material/sample entity")
        gear = event["equipment_ids"] + ([event["vessel_id"]] if event["vessel_id"] else [])
        if any(i not in entities or entities[i]["kind"] != "equipment" for i in gear):
            raise ValueError("An event equipment reference must name a reported equipment entity")
        if not any(event["action_surface"] in evidence[i]["quote"] for i in event["evidence_ids"]):
            raise ValueError("Action surface is not literal event evidence")
    for fact in graph["facts"]:
        if fact["subject_id"] not in objects or fact["event_id"] is not None and fact["event_id"] not in events:
            raise ValueError("Undefined fact subject/event")
        value = fact["value"]
        if value["value_type"] != "missing" and not fact["evidence_ids"]:
            raise ValueError("Reported facts require evidence")
        if value["value_type"] == "reference" and value["ref"] not in objects:
            raise ValueError("Undefined fact value reference")
        if value["value_type"] == "quantity":
            from .units import normalized_quantity, source_quantity_present
            normalized_quantity(value)
            if not source_quantity_present(value, [evidence[i]["quote"] for i in fact["evidence_ids"]]):
                raise ValueError("Quantity literal, precision or unit absent from cited source: " + fact["fact_id"])
            if value.get("basis_ref") and value["basis_ref"] not in objects:
                raise ValueError("Undefined relative quantity basis")
            if value.get("basis_ref") and value["basis_status"] != "reported":
                raise ValueError("Relative quantity basis status contradicts reference")
            if value["basis_status"] == "reported" and not value.get("basis_ref"):
                raise ValueError("A reported relative basis requires a reference")
            if value["quantity_kind"] in {"relative_loading", "equivalents"} and value["basis_status"] == "not_applicable":
                raise ValueError("Relative loading/equivalents need an explicit reported or unknown basis")
            if value.get("upper_value") and Decimal(value["upper_value"]) < Decimal(value["value"]):
                raise ValueError("Quantity interval is reversed")
    for relation in graph["relations"]:
        if relation["subject_id"] not in objects or relation["object_id"] not in objects:
            raise ValueError("Undefined relation endpoint")
        if relation["subject_id"] == relation["object_id"]:
            raise ValueError("Reflexive source relation")
        if relation["relation"] in {"precedes", "during", "same_interval"} and not {relation["subject_id"], relation["object_id"]} <= events.keys():
            raise ValueError("Temporal relations must bind events")
    ordered_events(graph)  # Reject cycles before compilation.
    return graph


def ordered_events(graph):
    """A stable topological realization; array order is not a source relation."""
    pending = {e["event_id"]: e for e in graph["events"]}
    edges = {(r["subject_id"], r["object_id"]) for r in graph["relations"] if r["relation"] == "precedes"}
    result = []
    while pending:
        ready = [i for i in pending if not any(b == i and a in pending for a, b in edges)]
        if not ready:
            raise ValueError("Cyclic temporal constraints")
        identifier = ready[0]
        result.append(pending.pop(identifier))
    return result


def number_candidates(text):
    """High-recall hints for the verifier; never ground truth or auto facts."""
    pattern = r"(?<![\w])\d+(?:\.\d+)?(?:\s*[–-]\s*\d+(?:\.\d+)?)?\s*(?:mmol|mol%|equiv|mL|µL|μL|uL|mg|kg|rpm|°C|oC|h|min|sec|%|g|L|M)(?!\w)"
    return [{"quote": m.group(), "start": m.start(), "end": m.end()} for m in re.finditer(pattern, text)]
