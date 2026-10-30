"""Independent XML conservation checks and reference-fact scoring, never model gold."""
from collections import Counter
import copy
import re

from .facts import text_hash
from .protocol.xdl_document import read_document
from .units import equivalent

REFERENCE_RECALL_MIN = .95


def _value_from_xml(raw, expected, parameters, step, prop, entities):
    value = expected["value"]
    kind = value["value_type"]
    if kind == "missing" or value["status"] == "qualitative":
        marker = "__" + value["status"].upper() + "__"
        if raw not in parameters or marker not in raw or "value" in parameters[raw]:
            return False
        return kind == "missing" or step.get(prop + "_description") == value["text"]
    if kind == "quantity":
        match = re.fullmatch(r"([+\-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+\-]?\d+)?)(?:–([+\-]?[\d.]+))?\s+(.+)", raw or "")
        if not match:
            return False
        actual = {**value, "value": match[1], "upper_value": match[2], "unit": match[3]}
        try:
            return equivalent(value, actual)
        except ValueError:
            return False
    if kind == "reference":
        entity = entities.get(value["ref"], {})
        return raw == (entity["name"] if entity.get("kind") in {"material", "sample"} else value["ref"])
    return raw == value["text"]


def check_conservation(graph, bound, output):
    """Read actual output, not a re-export or a compiler's 'preserved' flag.

    Location pointers are untrusted: subject/event/reagent/vessel, property name,
    scope, value, physical tag, subtype and temporal constraints are cross-checked.
    """
    errors, preserved = [], []
    try:
        doc = read_document(output["xml"], extensions=output["extensions"])
    except (ValueError, KeyError, TypeError) as error:
        return {"passed": False, "preserved": 0, "total": len(graph["facts"]), "issues": [{"kind": "invalid_xdl", "error": str(error)}]}
    parameters = {p["id"]: p for p in doc["parameters"]}
    hardware = {c["id"]: c for c in doc["hardware"]}
    reagent_names = {r["name"] for r in doc["reagents"]}
    entities = {e["entity_id"]: e for e in graph["entities"]}
    events = {e["event_id"]: e for e in graph["events"]}
    for entity in entities.values():
        identifier = entity["entity_id"]
        if entity["kind"] == "equipment":
            if hardware.get(identifier, {}).get("type") != bound["equipment"].get(identifier, {}).get("type") or identifier not in hardware:
                errors.append({"kind": "equipment_subtype_loss", "object_id": identifier})
        elif entity["name"] not in reagent_names:
            errors.append({"kind": "material_loss", "object_id": identifier})
    for event in graph["events"]:
        if event["kind"] == "observation":
            continue
        positions = output["event_locations"].get(event["event_id"], [])
        binding = bound["events"].get(event["event_id"], {})
        expected_tag = binding.get("name")
        if binding.get("operation_id") == "op.mix":
            expected_tag = {"stir": "Stir", "shake": "Shake", "vortex": "Vortex"}.get(binding.get("defaults", {}).get("method"), "MixContents")
        tags = [doc["steps"][p]["op"] for p in positions if isinstance(p, int) and 0 <= p < len(doc["steps"])]
        valid = bool(tags) and len(tags) == len(positions)
        if binding.get("operation_id") in {"op.heat", "op.cool", "op.temperature", "op.hold_temperature"}:
            valid = valid and all(t in {"HeatChill", "HeatChillToTemp"} for t in tags)
        elif expected_tag == "Stir" and tags and all(t in {"HeatChill", "HeatChillToTemp"} for t in tags):
            valid = valid and all(doc["steps"][p].get("stir") == "true" for p in positions)
        else:
            valid = valid and all(t == expected_tag for t in tags)
        if not valid:
            errors.append({"kind": "event_loss_or_changed_action", "object_id": event["event_id"]})
        for p in positions:
            if not isinstance(p, int) or not 0 <= p < len(doc["steps"]):
                continue
            step = doc["steps"][p]
            if event["vessel_id"] and step.get("vessel") != event["vessel_id"]:
                errors.append({"kind": "event_vessel_binding", "object_id": event["event_id"]})
            if any(step.get("apparatus_" + str(i + 1)) != gear for i, gear in enumerate(event["equipment_ids"])):
                errors.append({"kind": "event_equipment_binding", "object_id": event["event_id"]})
        if expected_tag == "Add":
            actual_names = Counter(doc["steps"][p].get("reagent") for p in positions if isinstance(p, int) and 0 <= p < len(doc["steps"]))
            expected_names = Counter(entities[p]["name"] for p in event["participant_ids"])
            if actual_names != expected_names:
                errors.append({"kind": "event_material_binding", "object_id": event["event_id"]})
    for fact in graph["facts"]:
        identifier = fact["fact_id"]
        location = output["fact_locations"].get(identifier, {})
        destination, valid = location.get("kind"), False
        if destination == "step" and fact["category"] == "process":
            position = location.get("position")
            if isinstance(position, int) and 0 <= position < len(doc["steps"]):
                step, prop = doc["steps"][position], location.get("property", "")
                event = events.get(fact["event_id"])
                valid = event is not None and position in output["event_locations"].get(fact["event_id"], [])
                valid = valid and location.get("event_id") == fact["event_id"] and location.get("subject_id") == fact["subject_id"]
                valid = valid and _value_from_xml(step.get(prop), fact, parameters, step, prop, entities)
                subject = entities.get(fact["subject_id"])
                if fact["attribute"] == "identity" and prop == "reagent":
                    valid = valid and subject is not None and step.get("reagent") == subject["name"]
                else:
                    valid = valid and step.get(prop + "_scope") == fact["scope"]
                    # Compare the physical parameter role separately from its value.
                    expected_props = {fact["attribute"]}
                    expected_props |= {"time"} if fact["attribute"] in {"duration", "duration_s"} else set()
                    expected_props |= {"temp"} if fact["attribute"] in {"temperature", "temp_C"} else set()
                    expected_props |= {"stir_speed"} if fact["attribute"] in {"rotation_speed", "speed"} else set()
                    if fact["attribute"] in {"dose", "amount"}:
                        expected_props |= {"mass", "volume", "amount"}
                    actual_prop = prop.removeprefix("subject_" + fact["subject_id"] + "_")
                    actual_prop = re.sub(r"_\d+$", "", actual_prop)
                    valid = valid and actual_prop in expected_props
                    if subject and subject["kind"] == "material" and step.get("op") == "Add":
                        valid = valid and step.get("reagent") == subject["name"]
                    elif subject and fact["subject_id"] != event["vessel_id"]:
                        expected = subject["entity_id"] if subject["kind"] == "equipment" else subject["name"]
                        valid = valid and step.get("subject_" + subject["entity_id"]) == expected
                    if fact["value"]["value_type"] == "quantity" and fact["value"]["quantity_kind"] in {"relative_loading", "equivalents"}:
                        basis = step.get(prop + "_basis")
                        valid = valid and (basis == fact["value"].get("basis_ref") if fact["value"].get("basis_ref") else basis in parameters and "__NOT_REPORTED__" in basis)
        elif destination == "hardware_config" and fact["category"] == "equipment":
            subject = fact["subject_id"]
            actual = output["hardware_config"].get(subject, {}).get("properties", {}).get(location.get("property"))
            valid = subject in hardware and location.get("subject_id") == subject and actual == {"value": fact["value"], "scope": fact["scope"], "attribute": fact["attribute"]}
        elif destination in {"observations", "context"} and fact["category"] in {"observation", "context", "provenance"}:
            valid = output.get(destination, {}).get(identifier) == fact
        (preserved if valid else errors).append(identifier if valid else {"kind": "fact_loss_or_binding", "fact_id": identifier})
    for relation in graph["relations"]:
        if relation not in output.get("relations", []):
            errors.append({"kind": "relation_loss", "object_id": relation["relation_id"]})
            continue
        a, b = relation["subject_id"], relation["object_id"]
        positions_a, positions_b = output["event_locations"].get(a, []), output["event_locations"].get(b, [])
        if relation["relation"] == "precedes" and positions_a and positions_b and max(positions_a) >= min(positions_b):
            errors.append({"kind": "temporal_order", "object_id": relation["relation_id"]})
        if relation["relation"] == "same_interval" and positions_a and positions_b and set(positions_a) != set(positions_b):
            errors.append({"kind": "concurrent_interval_loss", "object_id": relation["relation_id"]})
    errors.extend(_check_extra_outputs(graph, bound, output, doc))
    return {"passed": not errors, "preserved": len(preserved), "total": len(graph["facts"]), "issues": errors}


def _check_extra_outputs(graph, bound, output, doc):
    """Conservation includes additions as well as losses; a copied ledger is insufficient."""
    from .protocol.io import canonical, load_library
    issues, allowed = [], {i: set() for i in range(len(doc["steps"]))}
    entities = {e["entity_id"]: e for e in graph["entities"]}
    parameters = {p["id"]: p for p in doc["parameters"]}
    used = set()
    standards = load_library("xdl_steps.yaml")["steps"]
    for event in graph["events"]:
        if event["kind"] == "observation":
            continue
        binding = bound["events"].get(event["event_id"], {})
        for position in output["event_locations"].get(event["event_id"], []):
            if position not in allowed:
                continue
            used.add(position)
            step = doc["steps"][position]
            if event["vessel_id"]:
                allowed[position].add("vessel")
            if step["op"] == "Add":
                allowed[position].add("reagent")
            else:
                for i, participant in enumerate(event["participant_ids"]):
                    prop = "material_" + str(i + 1)
                    allowed[position].add(prop)
                    if step.get(prop) != entities[participant]["name"]:
                        issues.append({"kind": "participant_binding", "event_id": event["event_id"], "property": prop})
            allowed[position].update("apparatus_" + str(i + 1) for i in range(len(event["equipment_ids"])))
            for prop, value in binding.get("defaults", {}).items():
                if prop == "method" and binding["operation_id"] == "op.mix" and value in {"stir", "shake", "vortex"}:
                    continue
                allowed[position].add(prop)
                if step.get(prop) != str(value):
                    issues.append({"kind": "semantic_parameter_loss", "event_id": event["event_id"], "property": prop})
            if binding.get("operation_id") == "op.mix" and step["op"] in {"HeatChill", "HeatChillToTemp"}:
                related = [r for r in graph["relations"] if r["relation"] == "same_interval" and event["event_id"] in {r["subject_id"], r["object_id"]}]
                if related:
                    allowed[position].add("stir")
            required = set(standards.get(step["op"], {}).get("required", []))
            required |= {dict(duration="time", duration_s="time", temperature="temp", temp_C="temp", rotation_speed="stir_speed", speed="stir_speed", substance_amount="amount").get(p, p)
                         for p in binding.get("required_parameters", [])}
            for prop in required:
                value = step.get(prop)
                if value in parameters and "__NOT_REPORTED__" in value and "value" not in parameters[value]:
                    allowed[position].add(prop)
    for fact in graph["facts"]:
        location = output["fact_locations"].get(fact["fact_id"], {})
        if location.get("kind") != "step" or location.get("position") not in allowed:
            continue
        position, prop = location["position"], location["property"]
        allowed[position].add(prop)
        if prop != "reagent" or fact["attribute"] != "identity":
            allowed[position].add(prop + "_scope")
        if fact["value"]["status"] == "qualitative":
            allowed[position].add(prop + "_description")
        if fact["value"]["value_type"] == "quantity" and fact["value"]["quantity_kind"] in {"relative_loading", "equivalents"}:
            allowed[position].add(prop + "_basis")
        if prop.startswith("subject_" + fact["subject_id"] + "_"):
            allowed[position].add("subject_" + fact["subject_id"])
    if used != set(allowed):
        issues.append({"kind": "unsupported_physical_steps", "positions": sorted(set(allowed) - used)})
    for position, step in enumerate(doc["steps"]):
        extras = set(step) - {"op"} - allowed[position]
        if extras:
            issues.append({"kind": "unsupported_experimental_parameters", "position": position, "properties": sorted(extras)})
    expected_hardware = {e["entity_id"] for e in graph["entities"] if e["kind"] == "equipment"}
    if {c["id"] for c in doc["hardware"]} != expected_hardware:
        issues.append({"kind": "unsupported_hardware"})
    expected_reagents = {e["name"] for e in graph["entities"] if e["kind"] != "equipment"}
    if {r["name"] for r in doc["reagents"]} != expected_reagents:
        issues.append({"kind": "unsupported_reagents"})
    for identifier in expected_hardware:
        expected_props = {loc["property"] for loc in output["fact_locations"].values()
                          if loc.get("kind") == "hardware_config" and loc.get("subject_id") == identifier}
        config = output.get("hardware_config", {}).get(identifier, {})
        if set(config) != {"properties"} or set(config.get("properties", {})) != expected_props:
            issues.append({"kind": "unsupported_hardware_configuration", "subject_id": identifier})
    if set(output.get("hardware_config", {})) != expected_hardware:
        issues.append({"kind": "unbound_hardware_configuration"})
    if {canonical(r) for r in graph["relations"]} != {canonical(r) for r in output.get("relations", [])}:
        issues.append({"kind": "unsupported_relation"})
    return issues


def _key(value):
    return re.sub(r"[\W_]+", "", value.casefold())


def _reference_value(value):
    value = copy.deepcopy(value)
    if value["value_type"] == "missing" and value["status"] == "qualitative":
        return {"value_type": "text", "status": "qualitative", "text": value["raw"]}
    if value["value_type"] == "quantity":
        value.setdefault("basis_ref", None)
        value.setdefault("basis_status", "not_applicable")
        value.setdefault("upper_value", None)
    return {k: v for k, v in value.items() if k not in {"marker", "raw"}}


def _metric(tp, fp, fn):
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    return {"tp": tp, "fp": fp, "fn": fn, "precision": precision, "recall": recall,
            "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0}


def score_reference(graph, reference, *, text, bindings=None):
    """One-to-one deterministic matches. Partial drafts cannot yield global precision."""
    if reference["source_sha256"] != text_hash(text):
        raise ValueError("Reference source hash does not match literal input")
    evidence = {e["evidence_id"]: e["quote"] for e in graph["evidence"]}
    entity_map, event_map = {}, {}
    for ref in reference["entities"]:
        name = _key(ref.get("name", ref.get("source_surface", "")))
        matches = [e["entity_id"] for e in graph["entities"] if e["kind"] == ref["kind"] and
                   (name in {_key(e["name"]), _key(e["expression"])} or
                    any(name and name in _key(evidence[i]) for i in e["evidence_ids"]))]
        if len(matches) == 1 and matches[0] not in entity_map.values():
            entity_map[ref["entity_id"]] = matches[0]
    for ref in reference["events"]:
        action = _key(ref["action_surface"])
        participants = {entity_map.get(i) for i in ref.get("participant_ids", [])}
        acceptable_ops = ref.get("acceptable_operation_ids") or ([ref["operation_id"]] if ref.get("operation_id") else [])
        matches = [e["event_id"] for e in graph["events"] if
                   (action in {_key(e["action_surface"]), _key(e["expression"])} or
                    bool(bindings and bindings.get("events", {}).get(e["event_id"], {}).get("operation_id") in acceptable_ops)) and
                   (not participants or participants == set(e["participant_ids"])) and
                   (not ref.get("vessel_id") or entity_map.get(ref["vessel_id"]) == e["vessel_id"])]
        if len(matches) == 1 and matches[0] not in event_map.values():
            event_map[ref["event_id"]] = matches[0]
    object_map = {**entity_map, **event_map}
    used, matches, misses, details = set(), [], [], []
    category_counts = {}
    required = [f for f in reference["facts"] if f.get("requirement", "required") == "required"]
    for ref in required:
        value = _reference_value(ref["value"])
        if value.get("basis_ref"):
            value["basis_ref"] = object_map.get(value["basis_ref"], "__unresolved_reference_basis")
        binding_candidates, value_candidates = [], []
        for fact in graph["facts"]:
            if fact["fact_id"] in used or fact["attribute"] != ref["attribute"]:
                continue
            try:
                equal = equivalent(value, fact["value"])
            except (ValueError, KeyError):
                equal = False
            binding = (fact["subject_id"] == object_map.get(ref["subject_id"]) and
                       fact["event_id"] == event_map.get(ref.get("event_id")) and
                       ("scope" not in ref or ref["scope"] == fact["scope"]))
            if equal:
                value_candidates.append(fact)
            if equal and binding:
                binding_candidates.append(fact)
        if len(binding_candidates) == 1:
            fact = binding_candidates[0]
            used.add(fact["fact_id"])
            matches.append({"reference_id": ref["fact_id"], "fact_id": fact["fact_id"]})
            if value["value_type"] == "quantity":
                details.append({"reference_id": ref["fact_id"], "numeric_and_unit_equivalent": True,
                                "printed_value_preserved": value["value"] == fact["value"]["value"],
                                "unit_literal_preserved": value["unit"] == fact["value"]["unit"]})
        else:
            misses.append({"reference_id": ref["fact_id"], "critical": ref.get("critical", False),
                           "reason": "wrong_binding_or_scope" if value_candidates else "missing_or_wrong_value"})
        category = "quantity" if value["value_type"] == "quantity" else ref.get("category", "other")
        category_counts.setdefault(category, [0, 0])
        category_counts[category][0 if len(binding_candidates) == 1 else 1] += 1
    optional_matches = []
    for ref in reference["facts"]:
        if ref.get("requirement") != "optional":
            continue
        expected = _reference_value(ref["value"])
        for fact in graph["facts"]:
            if fact["fact_id"] in used or fact["attribute"] != ref["attribute"]:
                continue
            if fact["subject_id"] != object_map.get(ref["subject_id"]) or fact["event_id"] != event_map.get(ref.get("event_id")):
                continue
            if "scope" in ref and fact["scope"] != ref["scope"]:
                continue
            if equivalent(expected, fact["value"]):
                used.add(fact["fact_id"])
                optional_matches.append(fact["fact_id"])
                break
    relation_matches, relation_misses = [], []
    actual_relations = {(r["subject_id"], r["relation"], r["object_id"]) for r in graph.get("relations", [])}
    # Source partial order admits transitive precedence, never an inferred order
    # between two participants merely because their arrays have that order.
    closure = {(a, b) for a, relation, b in actual_relations if relation == "precedes"}
    while True:
        expanded = closure | {(a, d) for a, b in closure for c, d in closure if b == c}
        if expanded == closure:
            break
        closure = expanded
    for relation in reference.get("relations", []):
        if relation.get("requirement", "required") != "required":
            continue
        a = object_map.get(relation.get("subject_id", relation.get("from")))
        b = object_map.get(relation.get("object_id", relation.get("to")))
        kind = relation["relation"]
        found = (a, b) in closure if kind == "precedes" else (a, kind, b) in actual_relations or kind == "same_interval" and (b, kind, a) in actual_relations
        (relation_matches if found else relation_misses).append(relation)
    unknown_states, unknown_violations = Counter(), []
    for expectation in reference.get("unknown_expectations", []):
        subject = object_map.get(expectation["subject_id"])
        candidates = [f for f in graph["facts"] if f["subject_id"] == subject and f["attribute"] == expectation["attribute"]]
        actual = candidates[0]["value"]["status"] if len(candidates) == 1 else "absent" if not candidates else "multiple"
        unknown_states[expectation["status"] + "→" + actual] += 1
        if any(f["value"]["status"] != expectation["status"] for f in candidates) or not candidates and expectation.get("requirement") == "required":
            unknown_violations.append({"expectation": expectation, "actual": actual})
    complete = reference.get("coverage_status") == "complete"
    review = reference.get("manual_review", {})
    expert = bool(reference.get("is_gold") and review.get("reviewer") and review.get("reviewed_at") and review.get("decision") == "accept")
    fp = len(graph["facts"]) - len(used)
    metrics = _metric(len(matches), fp if complete else 0, len(misses))
    if not complete:
        metrics.update(precision=None, f1=None, fp=None)
    return {"reference_id": reference["reference_id"], "is_gold": expert,
            "status": "expert_reference" if expert else "provisional_unreviewed_reference",
            "complete_reference": complete, "metrics": metrics, "categories": {
                category: {"matched": counts[0], "missed": counts[1], "recall": counts[0] / sum(counts)} for category, counts in category_counts.items()},
            "entity_alignment": entity_map, "event_alignment": event_map, "matches": matches, "misses": misses,
            "optional_matches": optional_matches,
            "quantity_details": details, "unscored_output_facts": fp if not complete else 0,
            "relations": {"matched": len(relation_matches), "missed": relation_misses,
                          "recall": len(relation_matches) / (len(relation_matches) + len(relation_misses)) if relation_matches or relation_misses else None},
            "unknown_state_confusion": dict(unknown_states), "unknown_violations": unknown_violations,
            "event_recall": len(event_map) / len(reference["events"]) if reference["events"] else 1,
            "entity_recall": len(entity_map) / len(reference["entities"]) if reference["entities"] else 1,
            "critical_misses": sum(m["critical"] for m in misses),
            "gate_passed": bool(expert and complete and metrics["recall"] >= REFERENCE_RECALL_MIN and not any(m["critical"] for m in misses)
                                and not fp and not relation_misses and not unknown_violations)}


def _score_output_concepts(record, reference, score):
    """A correct surface phrase is insufficient if the chosen XDL operation is wrong."""
    missing_annotations, issues = [], []
    bindings = record.get("bindings", {})
    for ref in reference["events"]:
        if ref.get("kind") == "observation":
            continue
        expected = ref.get("acceptable_operation_ids") or ([ref["operation_id"]] if ref.get("operation_id") else [])
        if not expected:
            missing_annotations.append({"event_id": ref["event_id"], "field": "operation_id"})
            continue
        actual_id = score["event_alignment"].get(ref["event_id"])
        if bindings.get("events", {}).get(actual_id, {}).get("operation_id") not in expected:
            issues.append({"event_id": ref["event_id"], "kind": "wrong_operation_concept", "expected": expected})
    for ref in reference["entities"]:
        if ref["kind"] != "equipment":
            continue
        expected = ref.get("acceptable_subtype_ids") or ([ref["subtype_id"]] if ref.get("subtype_id") else [])
        if not expected:
            missing_annotations.append({"entity_id": ref["entity_id"], "field": "subtype_id"})
            continue
        actual_id = score["entity_alignment"].get(ref["entity_id"])
        if bindings.get("equipment", {}).get(actual_id, {}).get("subtype_id") not in expected:
            issues.append({"entity_id": ref["entity_id"], "kind": "wrong_equipment_concept", "expected": expected})
    return {"annotations_complete": not missing_annotations, "missing_annotations": missing_annotations, "issues": issues}


def evaluate_run(run_dir, references=()):
    """All source inputs remain in the denominator, including failed conversions."""
    from pathlib import Path
    from .protocol.io import read_json, read_jsonl
    from .verification import verify_conversion
    from .store import file_digest
    root = Path(run_dir)
    verification = verify_conversion(root)
    records = {r["raw_id"]: r for r in read_jsonl(root / "records.jsonl")}
    candidates = {r["raw_id"]: r for r in read_jsonl(root / "candidates.jsonl")}
    sources = {r["id"]: r for r in read_jsonl(root / "sources.jsonl")}
    scores, reference_hashes = [], {}
    for path in references:
        reference_hashes[str(Path(path).resolve())] = file_digest(path)
        reference = read_json(path)
        source_id = reference["source_id"]
        if source_id not in sources:
            raise ValueError("Reference is not for this batch: " + source_id)
        record = records.get(source_id, candidates.get(source_id, {}))
        graph = record.get("facts") or {"entities": [], "events": [], "facts": [], "evidence": []}
        score = score_reference(graph, reference, text=sources[source_id]["procedure"], bindings=record.get("bindings"))
        score["output_concepts"] = _score_output_concepts(record, reference, score)
        score["gate_passed"] = bool(score["gate_passed"] and score["output_concepts"]["annotations_complete"] and not score["output_concepts"]["issues"])
        score.update(source_id=source_id, conversion_complete=source_id in records)
        scores.append(score)
    gold = [s for s in scores if s["is_gold"] and s["complete_reference"]]
    tp, fp, fn = (sum(s["metrics"][key] for s in gold) for key in ("tp", "fp", "fn"))
    all_gold = len({s["source_id"] for s in gold}) == len(sources)
    return {"schema": "mosaic.reference-evaluation/1", "verification": verification,
            "evaluator_sha256": file_digest(__file__), "reference_sha256": reference_hashes,
            "input_count": len(sources), "converted": len(records), "failed": len(sources) - len(records),
            "reference_count": len(scores), "expert_complete_reference_count": len(gold), "scores": scores,
            "gold_micro": _metric(tp, fp, fn) if gold else None,
            "gold_macro_recall": sum(s["metrics"]["recall"] for s in gold) / len(gold) if gold else None,
            "bulk_gate_passed": bool(verification["passed"] and all_gold and len(records) == len(sources) and all(s["gate_passed"] for s in gold)),
            "gate_reason": "Every input needs a complete expert reference and independent compilation checks before bulk approval.",
            "runtime": read_json(root / "evaluation.json")}
