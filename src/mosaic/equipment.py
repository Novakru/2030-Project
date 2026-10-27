"""Compact apparatus families and evidence-scoped conditional substitution.

Families provide candidate retrieval; they never supply missing instance ratings.
Requirements use explicit units in field names. ``capacity_mL`` requests nominal
capacity in ``capacity_scope``; ``working_volume_mL`` requests working capacity.
Temperature, pressure and flow need their ``*_scope``; rpm needs ``mixing_mode``.
Geometry and material names are exact,
controlled identifiers, not guessed chemical-compatibility or adapter rules.
"""
from __future__ import annotations

import copy
import math
import re

from protocol_risk.io import digest, load_library


def _families(families):
    return load_library("equipment_families.yaml")["families"] if families is None else families


def _label(value):
    return re.sub(r"[\s-]+", "_", str(value or "").strip().lower())


def classify_equipment(device, *, families=None):
    """Return a known family without inferring identity, ratings or capabilities."""
    families = _families(families)
    def lookup(value):
        value = _label(value)
        if value in families:
            return value
        matches = [name for name, spec in families.items()
                   if value and value in {_label(alias) for alias in spec.get("aliases", [])}]
        return matches[0] if len(matches) == 1 else None

    declared = lookup(device.get("family"))
    for field in ("apparatus_kind", "kind", "type"):
        if device.get(field):
            found = lookup(device[field])
            # A specific, unrecognised source kind must not collapse to a generic category.
            return None if declared and found != declared else found
    if declared:
        return declared
    matches = [name for name, spec in families.items()
               if device.get("id") and device["id"] in spec.get("profile_ids", [])]
    if len(matches) == 1:
        return matches[0]
    value = _label(device.get("category"))
    matches = [name for name, spec in families.items()
               if value and value != "vessel" and value == _label(spec.get("category"))]
    return matches[0] if len(matches) == 1 else None


def equipment_groups(devices, observations=(), *, families=None):
    """Index library entries and source observations; anonymous observations stay so.

    Different capacity/model variants remain distinct entries within a family.
    Only observations with an explicit manufacturer and model form an identified
    profile, and contradictory values/scopes form separate profiles.
    """
    families = _families(families)
    devices = devices.values() if isinstance(devices, dict) else devices
    grouped = {name: {"category": spec.get("category"), "capabilities": spec.get("capabilities", []),
                      "source_urls": spec.get("source_urls", []), "device_ids": [], "observation_ids": []}
               for name, spec in families.items()}
    entries, identified, anonymous, unclassified = [], {}, [], []
    for device in devices:
        entry = copy.deepcopy(device)
        identifier = entry.get("id") or "entry_" + digest(entry)[:16]
        family = classify_equipment(entry, families=families)
        entries.append({**entry, "catalog_id": identifier, "family": family})
        if family:
            grouped[family]["device_ids"].append(identifier)
        else:
            unclassified.append({"kind": "catalog_entry", "id": identifier})
    for observation in observations:
        item = copy.deepcopy(observation)
        identifier = item.get("observation_id") or "observation_" + digest(item)[:16]
        family = classify_equipment(item, families=families)
        item.update(observation_id=identifier, family=family)
        if family:
            grouped[family]["observation_ids"].append(identifier)
        else:
            unclassified.append({"kind": "source_observation", "id": identifier})
        identity = item.get("identity") or {}
        if not isinstance(identity, dict) or not all(isinstance(identity.get(field), str) and identity[field].strip()
                                                   for field in ("manufacturer", "model")):
            anonymous.append(item)
            continue
        # Include all supplied facts, including future domain fields. A new
        # sterility, geometry or operating-scope claim must never be discarded.
        facts = {k: copy.deepcopy(v) for k, v in item.items()
                 if k not in ("id", "observation_id", "evidence", "source_evidence", "source_url", "source_locator")}
        key = digest(facts)
        profile = identified.setdefault(key, {"profile_id": "profile_" + key[:16], "family": family,
            "identity": copy.deepcopy(identity), "facts": facts, "observation_ids": [], "evidence": []})
        if identifier not in profile["observation_ids"]:
            profile["observation_ids"].append(identifier)
        for evidence in _evidence(item):
            if evidence not in profile["evidence"]:
                profile["evidence"].append(copy.deepcopy(evidence))
    for group in grouped.values():
        group["device_ids"] = sorted(set(group["device_ids"]))
        group["observation_ids"] = sorted(set(group["observation_ids"]))
    return {"schema": "mosaic.equipment-groups/1", "families": grouped, "catalog_profiles": entries,
            "identified_profiles": list(identified.values()), "anonymous_observations": anonymous,
            "unclassified": unclassified,
            "substitution_groups": [{"family": name, "device_ids": group["device_ids"],
                "observation_ids": group["observation_ids"], "status": "candidates_only"}
                for name, group in grouped.items() if group["device_ids"] or group["observation_ids"]],
            "policy": "Family membership retrieves candidates only. Conditional substitution must check explicit demands and cited individual facts; unidentified observations never invent a manufacturer model."}


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _evidence(candidate):
    evidence = []
    for field in ("evidence", "source_evidence"):
        items = candidate.get(field) or []
        if not isinstance(items, list):
            raise ValueError(field + " must be a list of references")
        for item in items:
            if item not in evidence:
                evidence.append(copy.deepcopy(item))
    if candidate.get("source_url"):
        evidence.append({"source_url": candidate["source_url"], "locator": candidate.get("source_locator")})
    return evidence


def _scope(value):
    value = _label(value)
    return {"sample": "sample_temperature", "liquid": "sample_temperature",
            "liquid_temperature": "sample_temperature", "plate_setpoint": "heating_plate_setpoint",
            "bath": "bath_temperature", "bath_setpoint": "bath_temperature",
            "circulating_bath_working_range": "bath_temperature"}.get(value, value)


def check_substitution(requirement, candidate, *, families=None):
    """Check supplied demands, returning compatible / incompatible / unknown.

    This is a conditional evidence check, not execution approval. No constraints
    are silently ignored, no missing rating is borrowed from a family, and a
    generic family match alone never returns compatible. Numeric facts must have
    source references; those references are not independently re-certified here.
    ``wetted_materials`` lists all acceptable contact materials, ``ports`` lists
    required port identifiers, and ``geometry`` requires exact keyed values.
    """
    if not isinstance(requirement, dict) or not isinstance(candidate, dict):
        raise TypeError("Requirement and candidate must be dictionaries")
    for field in ("capabilities", "ports", "wetted_materials"):
        for record in (requirement, candidate):
            value = record.get(field)
            if value is not None and (not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value)):
                raise ValueError(field + " must be a list of nonempty identifiers")
        if field in requirement and not requirement[field]:
            raise ValueError(field + " must specify at least one identifier")
    if "geometry" in requirement and not isinstance(requirement["geometry"], dict):
        raise ValueError("geometry must be a dictionary")
    for field in ("sterile", "sealed"):
        if field in requirement and not isinstance(requirement[field], bool):
            raise ValueError(field + " must be a boolean")
    if candidate.get("params") is not None and not isinstance(candidate["params"], dict):
        raise ValueError("Candidate params must be a dictionary")
    families, checks = _families(families), []
    params, evidence = candidate.get("params") or {}, _evidence(candidate)

    def add(field, status, needed, actual, reason):
        checks.append({"field": field, "status": status, "required": needed, "actual": actual,
                       "reason": reason, "evidence": copy.deepcopy(evidence)})

    def known(field, needed, actual, matches):
        if actual is None:
            add(field, "unknown", needed, actual, "Candidate fact is missing")
        elif not evidence:
            add(field, "unknown", needed, actual, "Candidate fact has no source reference")
        else:
            add(field, "compatible" if matches else "incompatible", needed, actual,
                "Supplied cited fact satisfies demand" if matches else "Supplied cited fact conflicts with demand")

    def interval(field, low_key, high_key):
        target = requirement[field]
        if not _number(target):
            raise ValueError(field + " must be a finite number")
        low, high = params.get(low_key), params.get(high_key)
        bounds = {low_key: low, high_key: high}
        if not evidence:
            add(field, "unknown", target, bounds, "Candidate limits have no source reference")
        elif _number(low) and _number(high) and low > high:
            add(field, "unknown", target, bounds, "Candidate range is internally contradictory")
        elif (_number(low) and target < low) or (_number(high) and target > high):
            add(field, "incompatible", target, bounds, "Demand exceeds a supplied cited limit")
        elif not _number(low) or not _number(high):
            add(field, "unknown", target, bounds, "Both applicable range limits are required")
        else:
            add(field, "compatible", target, bounds, "Demand lies within the supplied cited range")

    family = classify_equipment(candidate, families=families)
    if requirement.get("family"):
        requested = classify_equipment({"family": requirement["family"]}, families=families)
        status = "unknown" if requested is None or family is None else "compatible" if family == requested else "incompatible"
        add("family", status, requirement["family"], family, "Candidate grouping only; individual constraints still apply")
    capabilities = requirement.get("capabilities")
    if capabilities:
        actual = candidate.get("capabilities")
        known("capabilities", capabilities, actual, actual is not None and set(capabilities).issubset(actual))
    for field in ("capacity_mL", "working_volume_mL"):
        if field not in requirement:
            continue
        needed, actual = requirement[field], params.get(field)
        if not _number(needed) or needed <= 0:
            raise ValueError(field + " must be a positive finite number")
        expected_scope = requirement.get("capacity_scope")
        actual_scope = candidate.get("capacity_scope")
        if not expected_scope or not actual_scope:
            add("capacity_scope", "unknown", expected_scope, actual_scope, "Capacity needs an explicit compatible per-vessel/per-well scope")
        elif _label(expected_scope) != _label(actual_scope):
            add("capacity_scope", "unknown", expected_scope, actual_scope, "Capacity facts have a different scope and do not establish the requested capacity")
        else:
            known("capacity_scope", expected_scope, actual_scope, True)
        if not expected_scope or not actual_scope or _label(expected_scope) != _label(actual_scope):
            add(field, "unknown", needed, actual, "Capacity rating cannot be applied without matching scope")
        elif not _number(actual):
            add(field, "unknown", needed, actual, "Candidate capacity is missing or invalid")
        else:
            known(field, needed, actual, actual >= needed)
    if "temperature_C" in requirement:
        expected_scope, actual_scope = requirement.get("temperature_scope"), candidate.get("temperature_scope") or candidate.get("parameter_scope")
        if not expected_scope or not actual_scope:
            add("temperature_scope", "unknown", expected_scope, actual_scope, "Temperature needs an explicit scope")
        elif _scope(expected_scope) != _scope(actual_scope):
            add("temperature_scope", "unknown", expected_scope, actual_scope, "Controller/bath/sample scopes differ; no sample-temperature mapping is inferred")
        else:
            known("temperature_scope", expected_scope, actual_scope, True)
        if not expected_scope or not actual_scope or _scope(expected_scope) != _scope(actual_scope):
            add("temperature_C", "unknown", requirement["temperature_C"],
                {"T_min_C": params.get("T_min_C"), "T_max_C": params.get("T_max_C")},
                "Temperature limits do not establish the requested scope")
        else:
            interval("temperature_C", "T_min_C", "T_max_C")
    for field, low, high in (("rpm", "rpm_min", "rpm_max"), ("flow_mL_min", "flow_min_mL_min", "flow_max_mL_min"),
                            ("pressure_bar", "pressure_min_bar", "pressure_max_bar")):
        if field in requirement:
            scope_field = {"rpm": "mixing_mode", "flow_mL_min": "flow_scope", "pressure_bar": "pressure_scope"}[field]
            expected, actual = requirement.get(scope_field), candidate.get(scope_field)
            if not expected or not actual:
                add(scope_field, "unknown", expected, actual, "Numeric rating needs its operating mode/scope")
            elif _label(expected) != _label(actual) and scope_field != "mixing_mode":
                add(scope_field, "unknown", expected, actual, "Rating scope differs; no numeric conversion is inferred")
            elif scope_field != "mixing_mode":
                known(scope_field, expected, actual, True)
            if not _number(requirement[field]):
                raise ValueError(field + " must be a finite number")
            if expected and actual and _label(expected) == _label(actual):
                interval(field, low, high)
            else:
                add(field, "unknown", requirement[field], {low: params.get(low), high: params.get(high)},
                    "Numeric limits cannot be applied without matching mode/scope")
    if "wetted_materials" in requirement:
        acceptable, actual = requirement["wetted_materials"], candidate.get("wetted_materials")
        known("wetted_materials", acceptable, actual, bool(actual) and {_label(m) for m in actual}.issubset({_label(m) for m in acceptable}))
    if "ports" in requirement:
        needed, actual = requirement["ports"], candidate.get("ports")
        known("ports", needed, actual, actual is not None and set(needed).issubset(actual))
    if "geometry" in requirement:
        for name, value in requirement["geometry"].items():
            actual = (candidate.get("geometry") or {}).get(name)
            known("geometry." + name, value, actual, value == actual)
    for field in ("sterile", "mixing_mode", "sealed", "atmosphere_mode"):
        if field in requirement:
            actual = candidate.get(field)
            known(field, requirement[field], actual, requirement[field] == actual)
    for field, paired in (("capacity_scope", ("capacity_mL", "working_volume_mL")),
                          ("temperature_scope", ("temperature_C",)), ("flow_scope", ("flow_mL_min",)),
                          ("pressure_scope", ("pressure_bar",))):
        if field in requirement and not any(name in requirement for name in paired):
            actual = candidate.get(field)
            if field == "temperature_scope":
                actual = actual or candidate.get("parameter_scope")
            known(field, requirement[field], actual, _scope(requirement[field]) == _scope(actual))
    supported = {"family", "capabilities", "capacity_mL", "working_volume_mL", "capacity_scope", "temperature_C",
                 "temperature_scope", "rpm", "flow_mL_min", "pressure_bar", "wetted_materials", "ports", "geometry",
                 "sterile", "mixing_mode", "sealed", "atmosphere_mode", "id", "description", "evidence"}
    supported.update(("flow_scope", "pressure_scope"))
    for field in requirement.keys() - supported:
        add(field, "unknown", requirement[field], None, "Unsupported requirement; no compatibility inferred")
    if not any(check["field"] != "family" for check in checks):
        add("functional_requirements", "unknown", None, None, "Family alone does not specify a substitution demand")
    unknowns = [check for check in checks if check["status"] == "unknown"]
    incompatible = [check for check in checks if check["status"] == "incompatible"]
    return {"status": "incompatible" if incompatible else "unknown" if unknowns else "compatible", "family": family,
            "checks": checks, "unknowns": unknowns, "incompatibilities": incompatible,
            "scope": "Only supplied demands and cited facts; not universal equivalence, process success or execution approval."}
