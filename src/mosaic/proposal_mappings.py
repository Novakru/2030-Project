"""Resolve registered model expressions before the internal extraction grammar."""
import copy

from protocol_risk.extract import OPERATIONS, STEP_FIELDS
from protocol_risk.io import load_library
from protocol_risk.normalization import _context_matches, _convert, _unit_conversion

_CORE = {"op.add": "Add", "op.mix": "Stir", "op.heat": "HeatChill", "op.cool": "HeatChill",
         "op.temperature": "HeatChill", "op.wait": "Wait", "op.transfer": "Transfer",
         "op.filter": "Filter", "op.separate": "Separate", "op.evaporate": "Evaporate",
         "op.irradiate": "Irradiate", "op.atmosphere": "Atmosphere", "op.purify": "Purify"}
_UNITS = {"temp_C": "C", "duration_s": "s", "rpm": "rpm", "pressure_mbar": "mbar", "wavelength_nm": "nm"}


def resolve_proposal(proposal, registry, *, core_only=False):
    """Return a validated-grammar proposal and expression traces; no fact repair.

    These adapters supply names and typed containers only. Existing independent
    source/quantity checks still validate every value before persistence.
    """
    output, traces = copy.deepcopy(proposal), {}
    if not isinstance(output, dict) or not isinstance(output.get("steps"), list):
        return output, traces
    snapshot = registry.snapshot if hasattr(registry, "snapshot") else registry or {}
    operations = snapshot.get("canonical_operations") or load_library("atomic_operations.yaml")["operations"]
    mappings = snapshot.get("operation_mappings") or load_library("operation_mappings.yaml")
    for index, step in enumerate(output["steps"]):
        expression = step.get("op") if isinstance(step, dict) else None
        if not isinstance(expression, str) or expression in OPERATIONS:
            continue
        probe = {**step, "meta": {"object_role": step.get("object_role")}}
        candidates = [rule for rule in mappings.get("aliases", [])
                      if expression.strip().casefold() in {word.strip().casefold() for word in rule.get("expressions", [])}
                      and _context_matches(rule.get("context"), {}, probe)]
        if len(candidates) != 1:
            continue
        rule = candidates[0]
        contract = operations.get(rule.get("operation_id"))
        if not contract:
            continue
        if not isinstance(step.get("parameters", {}), dict):
            raise ValueError("Alias parameters must be an object")
        trace = {"expression": expression, "mapping_id": rule["id"],
                 "object_role": step.get("object_role"), "parameter_evidence": {}}
        legacy = _CORE.get(rule["operation_id"])
        if rule.get("composition"):
            if rule["id"] != "alias.heat_and_stir":
                continue
            legacy = "HeatChill"
        if rule["operation_id"] == "op.mix" and rule.get("defaults", {}).get("method") != "stir":
            legacy = None
        fields = {key: copy.deepcopy(value) for key, value in step.items()
                  if key not in {"op", "parameters", "object_role"}}
        for key, item in step.get("parameters", {}).items():
            target = rule.get("parameter_map", {}).get(key, key)
            if not isinstance(target, str):
                legacy = None
                continue
            if isinstance(item, dict) and "value" in item:
                trace["parameter_evidence"][key] = item.get("evidence")
                target = {"temperature": "temp_C", "duration": "duration_s", "speed": "rpm"}.get(target, target)
                converted = _convert(item, _unit_conversion(item, {}, {}))
                fields[target] = ({k: converted[k] for k in ("value", "unit") if k in converted}
                                  if target == "amount" else converted["value"])
            else:
                legacy = None
        if legacy and set(fields) <= STEP_FIELDS[legacy] | {"evidence", "stage", "vessel"}:
            if rule.get("composition"):
                fields["stir"] = True
            output["steps"][index] = {"op": legacy, **fields}
        else:
            if core_only:
                continue
            # One private adapter per canonical concept, independent of wording.
            # It never becomes another public operation or an instrument executor.
            adapter = "Mapped" + contract["name"]
            parameters = copy.deepcopy(step.get("parameters", {}))
            for key, value in step.items():
                if key in {"op", "parameters", "evidence", "stage", "vessel", "object_role"}:
                    continue
                parameters[key] = {"value": value, "evidence": step.get("evidence", ""),
                                   **({"unit": _UNITS[key]} if key in _UNITS else {})}
            specification = {}
            for key, item in parameters.items():
                kind = "string"
                value = item.get("value") if isinstance(item, dict) else None
                if isinstance(value, bool):
                    kind = "boolean"
                elif isinstance(value, (int, float)):
                    kind = "number"
                elif isinstance(item, dict) and "marker" in item:
                    declared = contract.get("parameters", {}).get(key, {}).get("type")
                    kind = "number" if declared == "quantity" else declared or "string"
                specification[key] = {"type": kind, "required": False}
                declared = contract.get("parameters", {}).get(key, {})
                if declared.get("dimension"):
                    specification[key]["dimension"] = declared["dimension"]
                if isinstance(item, dict) and "unit" in item:
                    specification[key]["unit"] = item["unit"]
                elif kind == "number" and key in _UNITS:
                    specification[key]["unit"] = _UNITS[key]
            definition = {"name": adapter, "domain": contract.get("domain", "general"),
                          "description": contract["description"], "parameters": specification,
                          "effects": contract.get("effects", []), "hardware_roles": contract.get("capabilities", [])}
            definitions = output.setdefault("definitions", {})
            if adapter in definitions:
                previous = definitions[adapter]
                if any(key in previous["parameters"] and previous["parameters"][key] != spec
                       for key, spec in specification.items()):
                    continue
                previous["parameters"].update(specification)
            else:
                definitions[adapter] = definition
            output["steps"][index] = {"op": adapter, "evidence": step.get("evidence", ""),
                "parameters": parameters, **{key: step[key] for key in ("stage", "vessel") if key in step}}
        traces[index] = trace
        trace.update(internal_operation=output["steps"][index]["op"], quote=step.get("evidence"))
        if expression in output.get("definitions", {}) and expression != output["steps"][index]["op"]:
            output["definitions"].pop(expression)
    return output, traces
