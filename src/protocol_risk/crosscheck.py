"""Separate independent source comparisons from facts merely copied from ORD."""
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
                       (rf"({NUMBER})\s*(?:minutes?|mins?)\b", 60),
                       (rf"({NUMBER})\s*(?:seconds?|secs?|s)\b", 1)],
        "rpm": [(rf"({NUMBER})\s*rpm\b", 1)],
        "pressure_mbar": [(rf"({NUMBER})\s*mbar\b", 1)],
        "mL": [(rf"({NUMBER})\s*mL\b", 1), (rf"({NUMBER})\s*uL\b", 0.001)],
        "mg": [(rf"({NUMBER})\s*mg\b", 1), (rf"({NUMBER})\s*g\b", 1000)],
        "mmol": [(rf"({NUMBER})\s*mmol\b", 1), (rf"({NUMBER})\s*umol\b", 0.001), (rf"({NUMBER})\s*mol\b", 1000)],
    }
    return [float(m.group(1)) * factor for pattern, factor in patterns.get(dimension, [])
            for m in re.finditer(pattern, text, re.IGNORECASE)]


def _matches(value, candidates, rel=0.001, absolute=1e-6):
    return any(math.isclose(value, candidate, rel_tol=rel, abs_tol=absolute) for candidate in candidates)


def crosscheck(protocol, raw):
    conflicts, missing, checks = [], [], {}
    initial_ids = {c["id"] for c in raw["components"]}
    initial_adds = [s for s in protocol["steps"] if s["op"] == "Add" and s["reagent"] in initial_ids]
    expected = {c["id"]: c["amount"] for c in raw["components"]}
    extracted = {s["reagent"]: s.get("amount") for s in initial_adds}
    checks["structured_components_preserved"] = set(extracted) == initial_ids
    checks["structured_amounts_preserved"] = extracted == expected
    checks["amount_comparison_is_independent"] = False
    quantity_checks = []
    if protocol["extraction"]["method"] == "llm_evidence_constrained":
        components = {c["id"]: c for c in raw["components"]}
        for step in initial_adds:
            meta = step.get("meta", {})
            check = verify_amount(components[step["reagent"]], expected[step["reagent"]],
                                  meta.get("evidence", ""), meta.get("source_alias"))
            check["step_id"] = step["id"]
            quantity_checks.append(check)
            if check["status"] == "conflict":
                conflicts.append(f"{step['id']}:independent_quantity_conflict")
        checks["amount_comparison_is_independent"] = bool(quantity_checks) and all(q["status"] == "matched" for q in quantity_checks)
        if not checks["amount_comparison_is_independent"]:
            missing.append("independent_quantity_evidence_incomplete")
    if not checks["structured_components_preserved"] or not checks["structured_amounts_preserved"]:
        conflicts.append("component_or_amount_loss")
    solvents = {r["id"] for r in protocol["reagents"] if r.get("role") == "SOLVENT" and r["id"] in initial_ids}
    checks["solvent_set_preserved"] = solvents == {c["id"] for c in raw["components"] if c["role"] == "SOLVENT"}
    if not checks["solvent_set_preserved"]:
        conflicts.append("solvent_set_conflict")
    temperatures = [s["temp_C"] for s in protocol["steps"] if s["op"] == "HeatChill" and s.get("temp_C") is not None]
    target = raw["temperature"]["value"] if raw["temperature"] else None
    checks["temperature_match"] = target is not None and _matches(target, temperatures, rel=0, absolute=5)
    if target is None or not temperatures:
        missing.append("temperature_independent_evidence_missing")
    elif not checks["temperature_match"]:
        conflicts.append("temperature_conflict")
    holds = [s["duration_s"] for s in protocol["steps"] if s.get("meta", {}).get("stage", "reaction") == "reaction"
             and s["op"] in ("HeatChill", "Stir", "Wait", "Irradiate") and s.get("duration_s") is not None]
    duration = raw["duration"]["value"] if raw["duration"] else None
    checks["reaction_duration_match"] = duration is not None and _matches(duration, holds, rel=0.1)
    if duration is None or not holds:
        missing.append("duration_independent_evidence_missing")
    elif not checks["reaction_duration_match"]:
        conflicts.append("duration_conflict")
    gas = raw.get("atmosphere", {}).get("type")
    actual_gases = {s.get("gas", "").lower() for s in protocol["steps"] if s["op"] == "Atmosphere"}
    if gas and gas not in ("UNSPECIFIED", "AIR"):
        checks["atmosphere_match"] = gas.lower() in actual_gases
        if not checks["atmosphere_match"]:
            missing.append("atmosphere_not_represented_in_steps")
    else:
        checks["atmosphere_match"] = None
    if protocol["extraction"]["method"] == "llm_evidence_constrained":
        for step in protocol["steps"]:
            evidence = step.get("meta", {}).get("evidence", "")
            if not evidence or evidence not in raw["procedure"]:
                conflicts.append(f"{step['id']}:nonliteral_evidence")
            for key in ("temp_C", "duration_s", "rpm", "pressure_mbar"):
                if key in step and not _matches(step[key], quantities_in_text(evidence, key)):
                    conflicts.append(f"{step['id']}:{key}_not_grounded")
            if step["op"] == "Add" and step["reagent"] not in initial_ids and step.get("amount"):
                amount = step["amount"]
                if not _matches(amount["value"], quantities_in_text(evidence, amount["unit"])):
                    conflicts.append(f"{step['id']}:workup_amount_not_grounded")
    else:
        checks["independent_text_crosscheck"] = False
        missing.append("structured_reconstruction_not_independent_text_extraction")
    missing.extend(protocol["extraction"].get("unresolved", []))
    if protocol["extraction"].get("unmapped_actions"):
        missing.append("unmapped_actions_require_review")
    # Copying fields is a lossless transform, not an independent gold annotation.
    blockers = ["hardware_human_verification_pending", "manual_protocol_review_pending"]
    if not checks["amount_comparison_is_independent"]:
        blockers.insert(0, "independent_quantity_review_pending")
    return {"checks": checks, "quantity_checks": quantity_checks, "conflicts": conflicts, "missing": missing,
            "tier": "rejected" if conflicts else "silver",
            "gold_blockers": blockers}
