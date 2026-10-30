"""Small literal regression case, not an expert-labelled accuracy dataset."""
import copy

TEXT = "Benzamide (24.2 mg, 0.2 mmol) was added to a 5 mL microreactor. The mixture was stirred for 2 min at room temperature."
GRAPH = {
    "schema_version": "mosaic.facts/1",
    "entities": [
        {"entity_id": "benzamide", "kind": "material", "name": "Benzamide", "expression": "Benzamide", "evidence_ids": ["c1"]},
        {"entity_id": "reactor", "kind": "equipment", "name": "microreactor", "expression": "microreactor", "evidence_ids": ["c2"]}],
    "events": [
        {"event_id": "add", "kind": "action", "expression": "add", "action_surface": "added", "participant_ids": ["benzamide"], "vessel_id": "reactor", "evidence_ids": ["c3"]},
        {"event_id": "mix", "kind": "action", "expression": "stir", "action_surface": "stirred", "vessel_id": "reactor", "evidence_ids": ["c4"]}],
    "facts": [
        {"fact_id": "mass", "subject_id": "benzamide", "event_id": "add", "attribute": "dose", "scope": "added_portion", "value": {"value_type": "quantity", "quantity_kind": "mass", "value": "24.2", "unit": "mg"}, "evidence_ids": ["c1"]},
        {"fact_id": "mmol", "subject_id": "benzamide", "event_id": "add", "attribute": "dose", "scope": "added_portion", "value": {"value_type": "quantity", "quantity_kind": "substance_amount", "value": "0.2", "unit": "mmol"}, "evidence_ids": ["c1"]},
        {"fact_id": "capacity", "subject_id": "reactor", "attribute": "nominal_volume", "category": "equipment", "scope": "nominal_capacity", "value": {"value_type": "quantity", "quantity_kind": "volume", "value": "5", "unit": "mL"}, "evidence_ids": ["c2"]},
        {"fact_id": "duration", "subject_id": "mix", "event_id": "mix", "attribute": "duration", "scope": "mix_interval", "value": {"value_type": "quantity", "quantity_kind": "time", "value": "2", "unit": "min"}, "evidence_ids": ["c4"]},
        {"fact_id": "temperature", "subject_id": "mix", "event_id": "mix", "attribute": "temperature", "scope": "mix_interval", "value": {"value_type": "text", "text": "room temperature", "status": "qualitative"}, "evidence_ids": ["c4"]}],
    "relations": [{"relation_id": "r1", "subject_id": "add", "relation": "precedes", "object_id": "mix", "evidence_ids": ["c3", "c4"]}],
    "evidence": [{"evidence_id": "c1", "quote": "Benzamide (24.2 mg, 0.2 mmol)"}, {"evidence_id": "c2", "quote": "5 mL microreactor"},
                 {"evidence_id": "c3", "quote": TEXT.split(". The")[0] + "."}, {"evidence_id": "c4", "quote": "The mixture was stirred for 2 min at room temperature."}]
}


def graph():
    return copy.deepcopy(GRAPH)
