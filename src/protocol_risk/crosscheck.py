"""Independent literal-text checks and isolated, non-authoritative ORD comparisons."""
from __future__ import annotations

import math
import re

from .amounts import verify_amount

NUMBER = r"[-+−]?\d+(?:\.\d+)?(?:e[-+]?\d+)?"


def quantities_in_text(text, dimension):
    text = text.replace("−", "-").replace("µ", "u").replace("μ", "u")
    patterns = {
        "temp_C": [(rf"({NUMBER})\s*(?:(?:°|º|o|degrees?)\s*)?C\b", 1)],
        "duration_s": [(rf"({NUMBER})\s*(?:hours?|hrs?|h)\b", 3600),
                       (rf"({NUMBER})\s*(?:days?|d)\b", 86400),
                       (rf"({NUMBER})\s*(?:minutes?|mins?)\b", 60),
                       (rf"({NUMBER})\s*(?:seconds?|secs?|s)\b", 1)],
        "rpm": [(rf"({NUMBER})\s*rpm\b", 1)],
        "pressure_mbar": [(rf"({NUMBER})\s*mbar\b", 1)],
        "wavelength_nm": [(rf"({NUMBER})\s*nm\b", 1)],
        "mL": [(rf"({NUMBER})\s*mL\b", 1), (rf"({NUMBER})\s*uL\b", 0.001),
               (rf"({NUMBER})\s*nL\b", 1e-6), (rf"({NUMBER})\s*L\b", 1000)],
        "mg": [(rf"({NUMBER})\s*mg\b", 1), (rf"({NUMBER})\s*g\b", 1000),
               (rf"({NUMBER})\s*ug\b", .001), (rf"({NUMBER})\s*kg\b", 1e6)],
        "mmol": [(rf"({NUMBER})\s*mmol\b", 1), (rf"({NUMBER})\s*umol\b", 0.001),
                 (rf"({NUMBER})\s*nmol\b", 1e-6), (rf"({NUMBER})\s*mol\b", 1000)],
    }
    return [float(m.group(1)) * factor for pattern, factor in patterns.get(dimension, [])
            for m in re.finditer(pattern, text, re.IGNORECASE)]


def _matches(value, candidates, rel=0.001, absolute=1e-6):
    return any(math.isclose(value, candidate, rel_tol=rel, abs_tol=absolute) for candidate in candidates)


def _reference_comparison(protocol, raw):
    """An ORD annotation may disagree; it cannot overwrite a textual process fact."""
    checks, conflicts, missing, component_checks = {}, [], [], []
    by_name = {}
    for reagent in protocol.get("reagents", []):
        by_name.setdefault(str(reagent.get("name", "")).casefold(), []).append(reagent)
    for component in raw.get("components") or []:
        if not isinstance(component, dict):
            continue
        name = str(component.get("name", "")).casefold()
        candidates = by_name.get(name, [])
        if len(candidates) != 1:
            component_checks.append({"reference_id": component.get("id"), "status": "unknown", "reason": "literal_name_alignment_unavailable"})
            continue
        reagent = candidates[0]
        adds = [step for step in protocol["steps"] if step["op"] == "Add" and step["reagent"] == reagent["id"]
                and step.get("meta", {}).get("stage", "reaction") == "reaction"]
        expected = component.get("amount")
        comparable = [step["amount"] for step in adds if step.get("amount") and isinstance(expected, dict)
                      and step["amount"].get("unit") == expected.get("unit")]
        status = "unknown"
        if comparable and isinstance(expected.get("value"), (int, float)):
            status = "matched" if _matches(expected["value"], [sum(x["value"] for x in comparable)], rel=.1) else "conflict"
        component_checks.append({"reference_id": component.get("id"), "text_reagent_id": reagent["id"],
                                 "status": status, "reference_amount": expected, "text_additions": comparable})
        if status == "conflict":
            conflicts.append("reference_quantity_disagreement:" + str(component.get("id")))
    for key, op_field, ops in (("temperature", "temp_C", {"HeatChill"}),
                                ("duration", "duration_s", {"HeatChill", "Stir", "Wait", "Irradiate"})):
        annotated = raw.get(key)
        target = annotated.get("value") if isinstance(annotated, dict) else None
        observed = [step[op_field] for step in protocol["steps"] if step["op"] in ops and op_field in step
                    and step.get("meta", {}).get("stage", "reaction") == "reaction"]
        if isinstance(target, (int, float)) and observed:
            checks[key + "_match"] = _matches(target, observed, rel=.1, absolute=5 if key == "temperature" else 1e-6)
            if not checks[key + "_match"]:
                conflicts.append("reference_" + key + "_disagreement")
        elif target is not None:
            missing.append("reference_" + key + "_not_comparable")
    return {"authority": "comparison_only_never_process_input", "checks": checks,
            "component_checks": component_checks, "conflicts": conflicts, "missing": missing}


def crosscheck(protocol, raw):
    conflicts, missing, quantity_checks = [], [], []
    checks = {"text_only_extraction": protocol.get("extraction", {}).get("input_contract") == "text-only/1"}
    reagents = {reagent["id"]: reagent for reagent in protocol.get("reagents", [])}
    procedure = raw.get("procedure") or ""
    for step in protocol["steps"]:
        meta = step.get("meta", {})
        evidence = meta.get("evidence", "")
        if not evidence or evidence not in procedure:
            conflicts.append(f"{step['id']}:nonliteral_evidence")
        for key in ("temp_C", "duration_s", "rpm", "pressure_mbar", "wavelength_nm"):
            if key in step and not _matches(step[key], quantities_in_text(evidence, key)):
                conflicts.append(f"{step['id']}:{key}_not_grounded")
        if step["op"] == "Add":
            reagent = reagents.get(step["reagent"], {"id": step["reagent"]})
            alias = meta.get("source_alias", reagent.get("name"))
            check = verify_amount(reagent, step.get("amount"), evidence, alias, tolerance=.001)
            check.update(step_id=step["id"], comparison="text_extraction_vs_independent_literal_parser")
            quantity_checks.append(check)
            if check["status"] == "conflict":
                conflicts.append(f"{step['id']}:independent_quantity_conflict")
    checks["literal_steps_grounded"] = not conflicts
    checks["amount_comparison_is_independent"] = bool(quantity_checks) and all(q["status"] == "matched" for q in quantity_checks)
    if not checks["amount_comparison_is_independent"]:
        missing.append("independent_quantity_evidence_incomplete")
    missing.extend(protocol.get("extraction", {}).get("unresolved", []))
    if protocol.get("extraction", {}).get("unmapped_actions"):
        missing.append("unmapped_actions_require_review")
    reference = _reference_comparison(protocol, raw)
    blockers = ["hardware_human_verification_pending", "manual_protocol_review_pending"]
    if not checks["amount_comparison_is_independent"]:
        blockers.insert(0, "independent_quantity_review_pending")
    if reference["conflicts"]:
        blockers.append("source_reference_disagreement_requires_review")
    return {"checks": checks, "quantity_checks": quantity_checks, "conflicts": conflicts, "missing": missing,
            "reference_comparison": reference, "tier": "rejected" if conflicts else "silver", "gold_blockers": blockers}
