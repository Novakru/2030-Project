"""Literal source gaps, kept outside numerical fields and executable values."""
from __future__ import annotations

import re

from .amounts import local_measurements
from .crosscheck import quantities_in_text

MISSING_MARKERS = {
    "not_reported": "__NOT_REPORTED__",
    "qualitative": "__QUALITATIVE__",
    "ambiguous": "__AMBIGUOUS__",
}
REQUIRED_PARAMETERS = {
    "Add": ("amount",), "HeatChill": ("temp_C",),
    "Stir": ("duration_s",), "Wait": ("duration_s",),
    "Irradiate": ("duration_s",),
    "Transfer": ("from_vessel", "to_vessel", "amount"),
    "Separate": ("keep_phase",), "Purify": ("method",),
}


def missing_parameter(evidence, status="not_reported", raw=None):
    """Describe a source gap; raw is an exact qualitative/ambiguous substring."""
    if not isinstance(status, str) or status not in MISSING_MARKERS:
        raise ValueError("Unknown missing-parameter status: " + str(status))
    if not isinstance(evidence, str) or not evidence.strip():
        raise ValueError("A missing parameter needs literal source evidence")
    if raw is not None and (not isinstance(raw, str) or not raw or raw not in evidence):
        raise ValueError("A missing parameter's raw value must occur literally in its evidence")
    return {"status": status, "marker": MISSING_MARKERS[status], "evidence": evidence, "raw": raw}


def is_missing_parameter(value):
    if not isinstance(value, dict) or set(value) != {"status", "marker", "evidence", "raw"}:
        return False
    try:
        return value == missing_parameter(value["evidence"], value["status"], value["raw"])
    except (TypeError, ValueError):
        return False


def parameter_absent(step, field):
    value = step.get(field)
    return value is None or isinstance(value, str) and value.strip().lower() in ("", "unknown", "unspecified")


_NUMBER = r"[-+]?\d+(?:\.\d+)?"
_UNITS = {
    "duration_s": r"(?:seconds?|secs?|s|minutes?|mins?|hours?|hrs?|h|days?|d)",
    "temp_C": r"(?:(?:°|º|degrees?)\s*)?C",
    "amount": r"(?:nL|uL|µL|μL|mL|L|ug|µg|μg|mg|kg|g|nmol|umol|µmol|μmol|mmol|mol)",
}
_QUALITATIVE = {
    "duration_s": r"\bovernight\b|\bbriefly\b|\buntil\s+[^.;]+",
    "temp_C": r"\b(?:room|ambient)\s+temperature\b|\breflux\b|\b(?:ice|water)[- ]bath\b|\bgentl(?:e|y)\s+heat(?:ing|ed)?\b",
    "amount": r"\b(?:dropwise|excess|catalytic\s+amount|small\s+amount|portionwise)\b",
}


def _gap(step, field, evidence, reagents):
    alias = None
    if field == "amount" and step["op"] == "Add":
        reagent = reagents.get(step.get("reagent"), {})
        alias = step.get("meta", {}).get("source_alias") or step.get("alias") or reagent.get("name") or step.get("reagent")
        measurements, reason = local_measurements(evidence, alias)
        if measurements:
            raise ValueError(f"{step.get('id', '?')}: explicit source amount cannot be marked missing")
        if reason == "alias_absent_or_ambiguous" and isinstance(alias, str) and evidence.count(alias) > 1:
            return missing_parameter(evidence, "ambiguous", alias)
    unit = _UNITS.get(field)
    if unit:
        # Ranges and bounds are reported information, but not a numeric setpoint.
        pattern = rf"(?:between\s+)?{_NUMBER}\s*(?:-|–|−|to|and|or)\s*{_NUMBER}\s*{unit}\b|(?:<|>|≤|≥|up\s+to|at\s+(?:least|most))\s*{_NUMBER}\s*{unit}\b"
        match = re.search(pattern, evidence, re.I)
        if match and alias:
            # Another reagent's range is not a missing dose for this reagent.
            positions = list(re.finditer(re.escape(alias), evidence))
            adjacent = any(
                match.end() <= position.start() and evidence[match.end():position.start()].strip() in ("", "of", "of a", "of an")
                or position.end() <= match.start() and not evidence[position.end():match.start()].strip(" (,:")
                for position in positions
            )
            if not adjacent:
                match = None
        if match:
            return missing_parameter(evidence, "ambiguous", match[0])
    if field in ("temp_C", "duration_s") or field == "amount" and step["op"] == "Transfer":
        dimension = "mL" if field == "amount" else field
        values = quantities_in_text(evidence, dimension)
        if len(set(values)) > 1:
            return missing_parameter(evidence, "ambiguous", evidence)
        if values:
            raise ValueError(f"{step.get('id', '?')}: explicit source {field} cannot be marked missing")
    qualitative = _QUALITATIVE.get(field)
    match = re.search(qualitative, evidence, re.I) if qualitative else None
    if match:
        return missing_parameter(evidence, "qualitative", match[0])
    return missing_parameter(evidence)


def annotate_missing(protocol):
    """Idempotently annotate absent required core fields, without inventing values.

    Extended operations own their parameter envelopes. Source text, when supplied,
    must contain each gap's exact evidence. An omitted explicit number is an
    extraction error, not permission to label the source incomplete.
    """
    reagents = {item["id"]: item for item in protocol.get("reagents", [])}
    source = protocol.get("source_text")
    for step in protocol.get("steps", []):
        required = REQUIRED_PARAMETERS.get(step.get("op"), ())
        if not required:
            continue
        gaps = step.get("missing_parameters", {})
        if not isinstance(gaps, dict) or any(key not in required for key in gaps):
            raise ValueError("Missing-parameter entries must target required core fields")
        evidence = step.get("meta", {}).get("evidence", step.get("evidence", ""))
        for field in required:
            if not parameter_absent(step, field):
                if field in gaps:
                    raise ValueError(f"{step.get('id', '?')}: known {field} also has a missing marker")
                continue
            if source is not None and (not isinstance(source, str) or not evidence or evidence not in source):
                raise ValueError("A missing parameter needs an exact quote from source_text")
            gap = _gap(step, field, evidence, reagents)
            if field in gaps and (not is_missing_parameter(gaps[field]) or gaps[field] != gap):
                raise ValueError("Missing-parameter marker disagrees with literal source evidence")
            step.pop(field, None)
            gaps[field] = gap
        if gaps:
            step["missing_parameters"] = gaps
    return protocol
