"""Canonical vocabulary with reversible, current-value analysis projections.

Names and aliases belong to the representation. An analysis recipe records how
to read the *current* representation; it never caches a pre-normalization step.
Consequently a deliberately wrong quantity or reference survives this seam.
"""
from __future__ import annotations

import copy
import math

from .io import digest, load_library

SCHEMA = "mosaic.normalization/1"
PROFILE = "mosaic-canonical/1"
_CORE = {"Add", "Transfer", "HeatChill", "Stir", "Wait", "Atmosphere", "Filter",
         "Separate", "Evaporate", "Irradiate", "Purify"}
_META_FIELDS = {"name", "display_name", "label", "description", "aliases", "mappings",
                "mapping_revision", "semantic_sha256", "source_urls", "evidence", "origins"}
_UNRESOLVED = {"id": "op.unresolved", "name": "Unresolved", "kind": "provenance",
               "domain": "general", "parameters": {}, "preconditions": [], "effects": [],
               "capabilities": [], "status": "unresolved"}
_UNITS = {
    "s": ("s", 1), "sec": ("s", 1), "min": ("s", 60), "h": ("s", 3600), "d": ("s", 86400),
    "mL": ("mL", 1), "uL": ("mL", .001), "µL": ("mL", .001), "μL": ("mL", .001), "L": ("mL", 1000),
    "mg": ("mg", 1), "g": ("mg", 1000), "ug": ("mg", .001), "µg": ("mg", .001),
    "mmol": ("mmol", 1), "mol": ("mmol", 1000), "umol": ("mmol", .001), "µmol": ("mmol", .001),
    "C": ("C", 1), "°C": ("C", 1), "mbar": ("mbar", 1), "rpm": ("rpm", 1), "nm": ("nm", 1),
}


def _semantic(value):
    if isinstance(value, dict):
        return {key: _semantic(item) for key, item in value.items() if key not in _META_FIELDS}
    if isinstance(value, list):
        return [_semantic(item) for item in value]
    return value


def semantic_contract_hash(contract):
    """Version semantics independently of labels, aliases and source citations."""
    semantic = {key: copy.deepcopy(contract[key]) for key in
                ("kind", "domain", "parameters", "preconditions", "effects", "capabilities")
                if key in contract}
    semantic["id"] = contract.get("id", contract.get("operation_id"))
    return digest(_semantic(semantic))


def is_normalized(protocol):
    return isinstance(protocol, dict) and protocol.get("normalization", {}).get("schema") == SCHEMA


def _vocabulary(vocabulary):
    if vocabulary is None:
        operations = load_library("atomic_operations.yaml")
        mappings = load_library("operation_mappings.yaml")
        return operations.get("operations", operations), mappings
    operations = vocabulary.get("operations", vocabulary.get("atomic_operations", {}))
    operations = operations.get("operations", operations)
    mappings = vocabulary.get("mappings", vocabulary.get("operation_mappings", {}))
    if not mappings and any(key in vocabulary for key in ("aliases", "migrations", "contracts")):
        mappings = {key: vocabulary[key] for key in ("aliases", "migrations", "contracts") if key in vocabulary}
    return operations, mappings


def _text(value):
    return " ".join(str(value).strip().casefold().split())


def _value(value):
    return value.get("value") if isinstance(value, dict) and "value" in value else value


def _context_matches(guard, protocol, step):
    """Only declared guards are understood; an unknown guard cannot admit a match."""
    if not guard:
        return True
    if not isinstance(guard, dict):
        return False
    parameters = {**step, **step.get("parameters", {})}
    context = {**protocol.get("context", {}), **step.get("meta", {})}
    for key, expected in guard.items():
        if key == "ambiguous_without_context":
            continue
        if key in {"domain", "domains"}:
            actual = context.get("domain", protocol.get("domain", protocol.get("mosaic", {}).get("domain")))
            choices = expected if isinstance(expected, list) else [expected]
            if actual not in choices:
                return False
        elif key in {"required_parameters", "requires_parameters"}:
            if any(name not in parameters for name in expected):
                return False
        elif key in {"parameter_equals", "parameters"}:
            if any(_value(parameters.get(name)) != value for name, value in expected.items()):
                return False
        elif key in context or key in parameters:
            actual = _value(parameters.get(key, context.get(key)))
            if (actual not in expected) if isinstance(expected, list) else (actual != expected):
                return False
        else:
            return False
    return True


def _mapping(protocol, step, definitions, mappings, operations):
    source_name = step.get("op", "")
    trace = step.get("meta", {}).get("source_expression", {})
    if trace:
        contextual = {**step, "meta": {**step.get("meta", {}), "object_role": trace.get("object_role")}}
        matching = [rule for rule in mappings.get("aliases", []) if rule.get("id") == trace.get("mapping_id")
                    and _text(trace.get("expression")) in {_text(word) for word in rule.get("expressions", [])}
                    and _context_matches(rule.get("context"), protocol, contextual)]
        if len(matching) == 1:
            return matching[0]
    definition = definitions.get(source_name, {})
    contract_hash = definition.get("semantic_sha256")
    exact = mappings.get("contracts", {}).get(contract_hash)
    if exact and exact.get("legacy_name", source_name) == source_name:
        if isinstance(contract_hash, str) and len(contract_hash) == 64:
            from .extensions import normalize_definition
            normalize_definition(source_name, definition)
        return {"id": "contract:" + contract_hash, **exact}
    if definition and source_name in mappings.get("migrations", {}):
        # An unrecognized contract is a new semantic proposal, even when its
        # author reused a familiar legacy name. Names cannot certify effects.
        return None
    # A contract-specific migration wins over an ambiguous surface form. A
    # source extension with an unknown contract may still use an explicit
    # declared migration; no fuzzy name matching is performed.
    migration = mappings.get("migrations", {}).get(source_name)
    if (migration and not migration.get("requires_exact_contract")
            and _context_matches(migration.get("context"), protocol, step)):
        return {"id": "legacy:" + source_name, **migration}
    candidates = [item for item in mappings.get("aliases", [])
                  if _text(source_name) in {_text(expression) for expression in item.get("expressions", [])}
                  and _context_matches(item.get("context"), protocol, step)]
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        decisions = {digest({key: item.get(key) for key in
                            ("operation_id", "parameter_map", "defaults", "composition")}) for item in candidates}
        if len(decisions) == 1:
            return sorted(candidates, key=lambda item: item.get("id", ""))[0]
        return None
    canonical = [identifier for identifier, item in operations.items() if source_name == item.get("name")]
    if len(canonical) == 1:
        return {"id": "canonical:" + canonical[0], "operation_id": canonical[0],
                "classification": "canonical"}
    return None


def _pointer(field, name):
    parts = str(name).split(".") if field == "parameters" else [str(name)]
    return "/" + field + "/" + "/".join(part.replace("~", "~0").replace("/", "~1") for part in parts)


def _put(values, path, value):
    parts = path.split(".")
    for part in parts[:-1]:
        if part not in values:
            values[part] = {}
        if not isinstance(values[part], dict) or "value" in values[part]:
            return False
        values = values[part]
    if parts[-1] in values and values[parts[-1]] != value:
        return False
    values[parts[-1]] = value
    return True


def _read(step, pointer):
    value = step
    for part in pointer.strip("/").split("/"):
        key = part.replace("~1", "/").replace("~0", "~")
        if not isinstance(value, dict) or key not in value:
            raise ValueError("Normalization binding no longer exists: " + pointer)
        value = value[key]
    return copy.deepcopy(value)


def _target(specification, source):
    if isinstance(specification, str):
        return specification, {}
    if isinstance(specification, dict):
        return specification.get("target", specification.get("name", source)), specification
    return source, {}


def _convert(value, conversion, *, inverse=False):
    result = copy.deepcopy(value)
    scale, offset = conversion.get("scale", 1), conversion.get("offset", 0)
    if scale == 0:
        raise ValueError("Parameter mappings cannot use a zero scale")
    scalar = _value(result)
    if (scale != 1 or offset != 0) and isinstance(scalar, (int, float)) and not isinstance(scalar, bool):
        number = (scalar - offset) / scale if inverse else scalar * scale + offset
        if not math.isfinite(number):
            raise ValueError("Parameter mapping produced a nonfinite number")
        if isinstance(result, dict):
            result["value"] = number
        else:
            result = number
    # Missing-marker objects pass through intact; unit conversion is applied
    # only to actual reported quantities, never to a qualitative marker.
    if isinstance(result, dict) and "value" in result:
        unit = conversion.get("source_unit" if inverse else "unit")
        if unit is not None:
            result["unit"] = unit
        if inverse and conversion.get("source_had_unit") is False:
            result.pop("unit", None)
        if inverse and conversion.get("source_numeric_type") == "int" and isinstance(result["value"], float) and result["value"].is_integer():
            result["value"] = int(result["value"])
        elif inverse and conversion.get("source_numeric_type") == "float" and isinstance(result["value"], (int, float)):
            result["value"] = float(result["value"])
    return result


def _unit_conversion(value, conversion, specification):
    """Only declared numeric units convert; qualitative markers stay untouched."""
    if not isinstance(value, dict) or not isinstance(value.get("value"), (int, float)) or isinstance(value["value"], bool):
        return conversion
    unit = value.get("unit", specification.get("unit"))
    if "scale" in conversion or "offset" in conversion or unit not in _UNITS:
        return conversion
    target, scale = _UNITS[unit]
    return {**conversion, "source_unit": unit, "unit": target, "scale": scale,
            "source_had_unit": "unit" in value, "source_numeric_type": type(value["value"]).__name__}


def _default(value, evidence):
    if isinstance(value, dict):
        return copy.deepcopy(value)
    return {"value": value, "evidence": evidence, "origin": "declared_mapping"}


def _contract(identifier, operations):
    contract = copy.deepcopy(operations.get(identifier, _UNRESOLVED if identifier == "op.unresolved" else None))
    if not isinstance(contract, dict):
        raise ValueError("Mapping refers to an undeclared operation: " + str(identifier))
    contract["id"] = identifier
    contract["semantic_sha256"] = semantic_contract_hash(contract)
    return contract


def _normalize_step(step, mapping, operations):
    original = copy.deepcopy(step)
    result = copy.deepcopy(step)
    unresolved = mapping is None
    mapping = mapping or {"id": "unresolved", "operation_id": "op.unresolved", "classification": "unresolved"}
    identifier = mapping["operation_id"]
    contract = _contract(identifier, operations)
    result.update(op=contract["name"], operation_id=identifier)
    source_parameters = result.pop("parameters", {})
    if not isinstance(source_parameters, dict):
        raise ValueError("Step parameters must be an object")
    parameters, reported, bindings, conflicts = {}, {}, {}, []
    parameter_map = mapping.get("parameter_map", {})
    for source, value in source_parameters.items():
        target, conversion = _target(parameter_map.get(source, source), source)
        conversion = _unit_conversion(value, conversion, mapping.get("source_parameters", {}).get(source, {}))
        if target.split(".")[0] in contract.get("parameters", {}):
            converted = _convert(value, conversion)
            if _put(parameters, target, converted):
                pointer = _pointer("parameters", target)
            else:
                reported[source] = copy.deepcopy(value)
                pointer = _pointer("reported_parameters", source)
                conflicts.append({"source": source, "target": target, "reason": "conflicting_reported_values"})
        else:
            reported[source] = copy.deepcopy(value)
            pointer = _pointer("reported_parameters", source)
        binding = {"path": pointer}
        if conversion:
            binding["conversion"] = copy.deepcopy(conversion)
            if isinstance(value, dict) and "unit" in value:
                binding["conversion"].setdefault("source_unit", value["unit"])
        bindings[source] = binding
    generated = []
    evidence = step.get("meta", {}).get("evidence", step.get("evidence", ""))
    for key, value in mapping.get("defaults", {}).items():
        # A mapping is allowed to add semantic method information. It may not
        # replace a source quantity, an explicit unknown, or a deliberate error.
        if key not in parameters and key not in result:
            if source_parameters or key in contract.get("parameters", {}):
                parameters[key] = _default(value, evidence)
                generated.append(key)
    if parameters:
        result["parameters"] = parameters
    if reported:
        result["reported_parameters"] = reported
    recipe = {"mapping_id": mapping.get("id", "declared"),
              "source_operation": original.get("op"),
              "classification": mapping.get("classification", "synonym"),
              "status": "unresolved" if unresolved or conflicts else "resolved",
              "source_had_parameters": "parameters" in original,
              "parameter_bindings": bindings,
              "generated_parameters": generated,
              "analysis_kind": "legacy_core" if original.get("op") in _CORE else "opaque",
              "original_field_names": sorted(original)}
    if conflicts:
        recipe["conflicts"] = conflicts
    if reported:
        recipe["unmapped_parameters"] = sorted(reported)
    if "attachment" in mapping:
        recipe["attachment"] = copy.deepcopy(mapping["attachment"])
    result["normalization"] = recipe
    return result, contract


def _enabled(member, step):
    condition = member.get("when")
    if not condition:
        return True
    parameter = condition.get("parameter")
    value = _value(step.get("parameters", {}).get(parameter, step.get(parameter)))
    if "one_of" in condition:
        return value in condition["one_of"]
    return value == condition.get("equals")


def _core_composition(step, mapping):
    if step.get("op") != "HeatChill" or step.get("stir") is not True:
        return mapping
    result = copy.deepcopy(mapping)
    result["classification"] = "composition"
    result["composition"] = {"steps": [
        {"key": "temperature", "operation_id": mapping["operation_id"]},
        {"key": "mix", "operation_id": "op.mix", "defaults": {"method": "stir"}}],
        "relations": [{"from": "temperature", "to": "mix", "relation": "same_interval"}]}
    return result


def _compose(step, mapping, operations, used_ids):
    composition = mapping["composition"]
    members = [member for member in composition.get("steps", []) if _enabled(member, step)]
    if not members:
        raise ValueError("Composition has no applicable members")
    group_id = "composition:" + step["id"]
    normalized, contracts, keys = [], {}, {}
    for index, member in enumerate(members):
        member_mapping = {**mapping, **member, "id": mapping.get("id", "declared") + ":" + member["key"]}
        member_mapping.pop("composition", None)
        if index:
            original = {key: copy.deepcopy(value) for key, value in step.items()
                        if key in {"id", "vessel", "meta", "requires", "evidence"}}
            candidate = step["id"] + "__" + member["key"]
            while candidate in used_ids:
                candidate += "_"
            used_ids.add(candidate)
            original["id"] = candidate
            original["op"] = step["op"]
            original["parameters"] = copy.deepcopy(step.get("parameters", {}))
        else:
            original = step
        item, contract = _normalize_step(original, member_mapping, operations)
        item["normalization"].update(group_id=group_id, member_key=member["key"], synthetic_member=index > 0)
        if index:
            # Unassigned source facts are stored on the anchor only, rather
            # than duplicated into every synthetic member.
            item.pop("reported_parameters", None)
            item["normalization"]["parameter_bindings"] = {
                key: binding for key, binding in item["normalization"]["parameter_bindings"].items()
                if binding["path"].startswith("/parameters/")}
        normalized.append(item)
        contracts[contract["name"]] = contract
        keys[member["key"]] = item["id"]
    relations = [{"from": keys[relation["from"]], "to": keys[relation["to"]],
                  "relation": relation["relation"], "group_id": group_id}
                 for relation in composition.get("relations", [])
                 if relation["from"] in keys and relation["to"] in keys]
    # Every original parameter must have a current binding. Prefer a member
    # whose canonical contract understands it over the anchor's reported bag.
    bindings = {}
    for item in normalized:
        for source, binding in item["normalization"]["parameter_bindings"].items():
            candidate = {"step_id": item["id"], **binding}
            if source not in bindings or (bindings[source]["path"].startswith("/reported_parameters/")
                                          and binding["path"].startswith("/parameters/")):
                bindings[source] = candidate
    group = {"source_step_id": step["id"], "source_operation": step["op"],
             "member_ids": [item["id"] for item in normalized], "parameter_bindings": bindings}
    return normalized, contracts, relations, group


def normalize_protocol(protocol, *, vocabulary=None):
    """Return a canonical copy without changing facts, reviews or risk labels."""
    if is_normalized(protocol):
        validate_normalized(protocol)
        return copy.deepcopy(protocol)
    operations, mappings = _vocabulary(vocabulary)
    result = copy.deepcopy(protocol)
    definitions = copy.deepcopy(result.get("operation_definitions", {}))
    steps, contracts, temporal, groups, rules = [], {}, [], {}, {}
    used_ids = {step["id"] for step in result.get("steps", [])}
    for source in result.get("steps", []):
        mapping = _mapping(result, source, definitions, mappings, operations)
        if mapping:
            key = source["op"] + ":" + definitions.get(source["op"], {}).get("semantic_sha256", "")
            rules[key] = {"expression": source["op"], "contract_hash": definitions.get(source["op"], {}).get("semantic_sha256"),
                          "mapping": copy.deepcopy(mapping)}
            mapping = {**mapping, "source_parameters": definitions.get(source["op"], {}).get("parameters", {})}
            mapping = _core_composition(source, mapping)
        if mapping and mapping.get("composition"):
            members, declared, relations, group = _compose(source, mapping, operations, used_ids)
            steps.extend(members)
            contracts.update(declared)
            temporal.extend(relations)
            groups["composition:" + source["id"]] = group
        else:
            step, contract = _normalize_step(source, mapping, operations)
            steps.append(step)
            contracts[contract["name"]] = contract
    result["steps"] = steps
    result["operation_definitions"] = contracts
    result["xdl_profile"] = PROFILE
    result["normalization"] = {"schema": SCHEMA, "mappings_revision": digest(mappings),
                               "source_operation_definitions": definitions,
                               "source_xdl_profile": protocol.get("xdl_profile"),
                               "source_had_definitions": "operation_definitions" in protocol,
                               "source_had_temporal_relations": "temporal_relations" in protocol,
                               "groups": groups, "mapping_rules": rules}
    result["normalization"]["unresolved"] = [
        {"step_id": step["id"], "source_operation": step["normalization"]["source_operation"],
         "reason": step["normalization"].get("conflicts", "no_declared_semantic_mapping")}
        for step in steps if step["normalization"]["status"] == "unresolved"]
    if temporal:
        result["temporal_relations"] = copy.deepcopy(result.get("temporal_relations", [])) + temporal
    if "hardware" in result:
        from .equipment_normalization import normalize_equipment
        equipment_kwargs = {}
        if vocabulary:
            if "equipment" in vocabulary:
                equipment_kwargs["catalog"] = vocabulary["equipment"]
            if "equipment_mappings" in vocabulary:
                equipment_kwargs["mappings"] = vocabulary["equipment_mappings"]
        result["hardware"] = normalize_equipment(result["hardware"], **equipment_kwargs)
    validate_normalized(result)
    return result


def _lower_step(step, *, bindings=None, current_steps=None):
    result = copy.deepcopy(step)
    recipe = result.pop("normalization")
    result["op"] = recipe["source_operation"]
    result.pop("operation_id", None)
    result.pop("reported_parameters", None)
    source_parameters = {}
    for source, binding in (bindings if bindings is not None else recipe["parameter_bindings"]).items():
        owner = current_steps[binding["step_id"]] if "step_id" in binding else step
        value = _read(owner, binding["path"])
        source_parameters[source] = _convert(value, binding.get("conversion", {}), inverse=True)
    # Edits may add a canonical parameter after normalization. Preserve it too;
    # a projection must not quietly repair a newly introduced bad parameter.
    bound_targets = {binding["path"].split("/")[2] for binding in recipe["parameter_bindings"].values()
                     if binding["path"].startswith("/parameters/")}
    for key, value in step.get("parameters", {}).items():
        if key not in bound_targets and key not in recipe.get("generated_parameters", []):
            source_parameters.setdefault(key, copy.deepcopy(value))
    if (recipe.get("source_operation") == "Stir" and "method" in recipe.get("generated_parameters", [])
            and _value(step.get("parameters", {}).get("method")) != "stir"):
        # A changed mixing mechanism must not keep the stirring-specific
        # equipment verifier merely because its original spelling was Stir.
        result["op"] = "Mix"
        source_parameters["method"] = copy.deepcopy(step.get("parameters", {}).get("method"))
    if source_parameters or recipe["source_had_parameters"]:
        result["parameters"] = source_parameters
    else:
        result.pop("parameters", None)
    return result


def analysis_protocol(protocol):
    """Project canonical names to pinned legacy semantics using current data."""
    if not is_normalized(protocol):
        return copy.deepcopy(protocol)
    validate_normalized(protocol)
    result = copy.deepcopy(protocol)
    normalization = result.pop("normalization")
    current_steps = {step["id"]: step for step in protocol["steps"]}
    groups, lowered = normalization.get("groups", {}), []
    for step in protocol["steps"]:
        recipe = step["normalization"]
        if recipe.get("synthetic_member"):
            continue
        group = groups.get(recipe.get("group_id"))
        projected = _lower_step(step, bindings=group["parameter_bindings"] if group else None,
                                current_steps=current_steps)
        if group and projected.get("op") == "HeatChill" and projected.get("stir") is True:
            mixes = [current_steps[identifier] for identifier in group["member_ids"]
                     if current_steps[identifier].get("operation_id") == "op.mix"]
            if any(_value(member.get("parameters", {}).get("method")) != "stir" for member in mixes):
                projected["op"] = "UnresolvedCombinedOperation"
        lowered.append(projected)
    result["steps"] = lowered
    if normalization["source_had_definitions"]:
        result["operation_definitions"] = copy.deepcopy(normalization["source_operation_definitions"])
    else:
        result.pop("operation_definitions", None)
    source_profile = normalization.get("source_xdl_profile")
    if source_profile is None:
        result.pop("xdl_profile", None)
    else:
        result["xdl_profile"] = source_profile
    source_relations = [relation for relation in result.get("temporal_relations", [])
                        if relation.get("group_id") not in groups]
    if source_relations or normalization.get("source_had_temporal_relations"):
        result["temporal_relations"] = source_relations
    else:
        result.pop("temporal_relations", None)
    if "hardware" in result:
        from .equipment_normalization import analysis_equipment
        result["hardware"] = analysis_equipment(result["hardware"])
    return result


def _validate_parameters(step, contract, protocol):
    from .missing import is_missing_parameter
    parameters = step.get("parameters", {})
    if set(parameters) - set(contract.get("parameters", {})):
        raise ValueError("Canonical parameter is not declared by its contract")
    for key, item in parameters.items():
        if is_missing_parameter(item):
            continue
        specification = contract["parameters"][key]
        kind = specification.get("type")
        value = _value(item)
        if kind == "object":
            valid = isinstance(item, dict)
        elif kind == "quantity":
            valid = isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
            if not valid and isinstance(value, str):
                # Some legacy records report a literal quantity string. Keep
                # it as reported text, without pretending it is numeric. The
                # exception needs a pinned source-string contract and binding.
                recipe = step["normalization"]
                original = protocol["normalization"]["source_operation_definitions"].get(recipe["source_operation"], {})
                valid = any(binding["path"] == _pointer("parameters", key)
                            and original.get("parameters", {}).get(source, {}).get("type") == "string"
                            for source, binding in recipe["parameter_bindings"].items())
        elif kind in {"number", "integer"}:
            valid = isinstance(value, int if kind == "integer" else (int, float)) and not isinstance(value, bool) and math.isfinite(value)
        elif kind == "boolean":
            valid = isinstance(value, bool)
        elif kind in {"string", "reference"}:
            valid = isinstance(value, str)
        else:
            raise ValueError("Unsupported canonical parameter type: " + str(kind))
        if not valid:
            raise ValueError("Invalid canonical parameter type: " + key)


def validate_normalized(protocol):
    """Check representation contracts; source gaps and bad negative values remain data.

    This check deliberately does not certify execution, experimental feasibility,
    references, dimensions or positive quantities: those are risk-check inputs.
    """
    if not is_normalized(protocol):
        raise ValueError("Protocol has no canonical normalization provenance")
    definitions = protocol.get("operation_definitions")
    if not isinstance(definitions, dict):
        raise ValueError("Canonical operation definitions must be an object")
    identifiers = {}
    for name, contract in definitions.items():
        if not isinstance(contract, dict) or contract.get("name") != name:
            raise ValueError("Canonical operation definition name disagrees with its key")
        identifier = contract.get("id", contract.get("operation_id"))
        if not isinstance(identifier, str) or not identifier.strip():
            raise ValueError("Canonical operations need stable identifiers")
        if identifier in identifiers and identifiers[identifier] != name:
            raise ValueError("One operation identifier has multiple canonical names")
        identifiers[identifier] = name
        if not isinstance(contract.get("parameters", {}), dict):
            raise ValueError("Canonical parameter contract must be an object")
        for field in ("preconditions", "effects", "capabilities"):
            if not isinstance(contract.get(field, []), list):
                raise ValueError("Canonical contract " + field + " must be a list")
        if contract.get("semantic_sha256") != semantic_contract_hash(contract):
            raise ValueError("Canonical operation semantic hash mismatch")
    steps = protocol.get("steps", [])
    ids = [step.get("id") for step in steps]
    if any(not isinstance(identifier, str) or not identifier for identifier in ids) or len(ids) != len(set(ids)):
        raise ValueError("Canonical steps need unique nonempty identifiers")
    for step in steps:
        contract = definitions.get(step.get("op"))
        if contract is None or contract["id"] != step.get("operation_id"):
            raise ValueError("Canonical step does not match its operation contract")
        recipe = step.get("normalization", {})
        if not isinstance(recipe.get("source_operation"), str) or not isinstance(recipe.get("parameter_bindings"), dict):
            raise ValueError("Canonical step has no reversible source recipe")
        if not isinstance(step.get("parameters", {}), dict) or not isinstance(step.get("reported_parameters", {}), dict):
            raise ValueError("Canonical parameter values must be objects")
        _validate_parameters(step, contract, protocol)
        for binding in recipe["parameter_bindings"].values():
            if not isinstance(binding, dict) or not isinstance(binding.get("path"), str):
                raise ValueError("Invalid normalization parameter binding")
            _read(step, binding["path"])
    for group in protocol["normalization"].get("groups", {}).values():
        if not set(group["member_ids"]) <= set(ids):
            raise ValueError("Normalization composition member is missing")
        for binding in group["parameter_bindings"].values():
            owner = next((step for step in steps if step["id"] == binding["step_id"]), None)
            if owner is None:
                raise ValueError("Normalization composition binding refers to an absent member")
            _read(owner, binding["path"])
    for relation in protocol.get("temporal_relations", []):
        if relation.get("group_id") in protocol["normalization"].get("groups", {}):
            if relation.get("from") not in ids or relation.get("to") not in ids:
                raise ValueError("Canonical temporal relation refers to an absent member")
            if relation.get("relation") not in {"before", "overlaps", "same_interval"}:
                raise ValueError("Unknown canonical temporal relation")
    return []
