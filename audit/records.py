"""Small adapters for flat positive records and wrapped negative protocols."""
import json
from typing import Any, Dict, List


def as_dict(value: Any) -> Dict:
    return value if isinstance(value, dict) else {}


def protocol(record: Dict) -> Dict:
    return as_dict(record.get("protocol")) or record


def field(record: Dict, name: str, default=None):
    if name in record:
        return record[name]
    return protocol(record).get(name, default)


def quality_owner(record: Dict) -> Dict:
    """Use the existing quality location; never copy parent/protocol identifiers."""
    if "quality" in record:
        return record
    inner = as_dict(record.get("protocol"))
    return inner if "quality" in inner else record


def quality(record: Dict) -> Dict:
    return as_dict(quality_owner(record).get("quality"))


def list_values(value: Any) -> List:
    if value is None or value == "" or value is False or value == {}:
        return []
    return value if isinstance(value, list) else [value]


def kind(record: Dict) -> str:
    return "other" if record.get("record_type") == "other" else "positive"


def index_fields(record: Dict) -> Dict:
    q = quality(record)
    cross = as_dict(field(record, "crosscheck"))
    blockers = list_values(cross.get("gold_blockers")) + list_values(q.get("gold_blockers"))
    tier = q.get("tier") or cross.get("tier") or "unrated"
    return {
        "tier": str(tier), "record_type": kind(record),
        "has_gold_blockers": int(bool(blockers)),
    }


def step_rows(record: Dict) -> List[Dict]:
    """Show stated amounts and capacities; no density or cumulative-volume guesses."""
    hardware = as_dict(field(record, "hardware"))
    nodes = hardware.get("nodes", {})
    if isinstance(nodes, list):
        nodes = {str(n.get("id")): n for n in nodes if isinstance(n, dict)}
    nodes = as_dict(nodes)
    reagents = field(record, "reagents", [])
    names = {str(r.get("id")): r.get("name", r.get("id"))
             for r in reagents if isinstance(r, dict)} if isinstance(reagents, list) else {}
    steps = field(record, "steps", [])
    rows = []
    for index, step in enumerate(steps if isinstance(steps, list) else []):
        if not isinstance(step, dict):
            rows.append({"step_id": str(index + 1), "other": json.dumps(step, ensure_ascii=False)})
            continue
        vessel = step.get("vessel", step.get("to_vessel", ""))
        node = as_dict(nodes.get(str(vessel)))
        capacity = as_dict(node.get("params")).get("capacity_mL", node.get("capacity_mL"))
        amount = step.get("amount", step.get("volume", step.get("mass", "")))
        amount = (f"{amount.get('value', '')} {amount.get('unit', '')}"
                  if isinstance(amount, dict) else str(amount))
        rows.append({
            "step_id": step.get("step_id", step.get("id", str(index + 1))),
            "action": step.get("op", step.get("action", step.get("type", ""))),
            "reagent": names.get(str(step.get("reagent")), step.get("reagent", "")),
            "amount": amount, "vessel": str(vessel), "capacity_mL": capacity,
            "temp_C": step.get("temp_C"), "duration_s": step.get("duration_s"),
            "evidence": as_dict(step.get("meta")).get("evidence", ""),
        })
    return rows
