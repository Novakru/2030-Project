"""Mechanical use of admitted representations; candidate semantics never execute."""
from __future__ import annotations

import copy

from protocol_risk.io import digest
from .evolution import CurationPolicy


def _snapshot(registry):
    return registry.snapshot if hasattr(registry, "snapshot") else registry


def trusted_representations(snapshot, *, allowed_operations=None):
    """Return prompt-safe active aliases/macros after verifying their contracts.

    The default supported backend is the text-to-XDL chemistry implementation.
    Another domain must explicitly supply its supported primitive names.
    """
    from protocol_risk.extract import OPERATIONS

    snapshot = _snapshot(snapshot)
    allowed = set(OPERATIONS if allowed_operations is None else allowed_operations)
    definitions = snapshot["operations"]
    aliases, macros = {}, {}
    for name in snapshot.get("aliases", {}):
        cursor, visited = name, set()
        while cursor in snapshot["aliases"]:
            if cursor in visited:
                raise ValueError("Active operation aliases form a cycle")
            visited.add(cursor)
            target = snapshot["aliases"][cursor]
            if cursor not in definitions or target not in definitions or definitions[cursor] != definitions[target]:
                raise ValueError("Active operation alias loses its full contract")
            cursor = target
        if cursor not in allowed:
            raise ValueError("Active alias targets an unsupported primitive: " + str(cursor))
        aliases[name] = cursor
    for representation in snapshot.get("representations", {}).values():
        if representation.get("status") != "admitted_representation":
            raise ValueError("Active representations contain an unadmitted candidate")
        certificate = representation.get("certificate", {})
        template = {key: representation.get(key) for key in ("contract", "expansion", "parameter_mapping")}
        if (certificate.get("lossless") is not True or certificate.get("effects_preserved") is not True
                or certificate.get("guards_preserved") is not True
                or certificate.get("domain") != representation.get("domain")
                or certificate.get("contract_sha256") != digest(template)
                or certificate.get("witness_sha256") != digest(representation.get("witnesses"))):
            raise ValueError("Active macro lacks a matching lossless domain certificate")
        name = representation.get("name")
        if not isinstance(name, str) or not name or name in definitions or name in aliases or name in macros:
            raise ValueError("Active macro has an ambiguous operation name")
        for operation in representation.get("expansion", []):
            if aliases.get(operation, operation) not in allowed:
                raise ValueError("Active macro expands to an unsupported primitive: " + str(operation))
        macros[name] = {key: copy.deepcopy(representation[key]) for key in
                        ("domain", "name", "contract", "expansion", "parameter_mapping", "witnesses")}
    return {"aliases": aliases, "macros": macros}


def expand_plan(plan, snapshot, *, source=None, allowed_operations=None):
    """Expand only certified aliases/macros and preserve all source context.

    Missing parameters and unexpected dimensions are errors, never silent drops.
    ``source`` optionally performs the final chemistry evidence check here; the
    extraction caller must otherwise run its domain validator after expansion.
    """
    from protocol_risk.extract import OPERATIONS, validate_evidence

    snapshot = _snapshot(snapshot)
    trusted = trusted_representations(snapshot, allowed_operations=allowed_operations)
    allowed = set(OPERATIONS if allowed_operations is None else allowed_operations)
    if not isinstance(plan, dict) or not isinstance(plan.get("steps"), list):
        raise ValueError("Representation expansion requires a steps array")
    output, expanded = copy.deepcopy(plan), []
    for step in plan["steps"]:
        if not isinstance(step, dict):
            raise ValueError("Representation step must be an object")
        name = step.get("op")
        canonical = trusted["aliases"].get(name, name)
        if canonical in allowed:
            expanded.append({**copy.deepcopy(step), "op": canonical})
            continue
        macro = trusted["macros"].get(name)
        if macro is None:
            raise ValueError("Operation has no admitted representation: " + str(name))
        parameters = macro["contract"]["parameters"]
        permitted = set(parameters) | {"op", "evidence", "stage", "vessel"}
        extra, missing = set(step) - permitted, set(parameters) - set(step)
        if extra:
            raise ValueError("Macro would drop unmapped dimensions: " + ", ".join(sorted(extra)))
        if missing:
            raise ValueError("Macro lacks source parameters: " + ", ".join(sorted(missing)))
        if not isinstance(step.get("evidence"), str) or not step["evidence"]:
            raise ValueError("Macro needs literal source evidence")
        policy = CurationPolicy(macro["domain"], {name: {key: macro[key] for key in
                               ("contract", "expansion", "parameter_mapping")}})
        # Replaying the supplied certificate witnesses also validates mapping
        # coverage and required primitive fields before using this representation.
        policy.verify_macro(macro, snapshot)
        values = {key: copy.deepcopy(step[key]) for key in parameters}
        policy.verify_witness(values, macro["contract"])
        children = []
        for operation in macro["expansion"]:
            child = {key: copy.deepcopy(step[key]) for key in ("evidence", "stage", "vessel") if key in step}
            child["op"] = trusted["aliases"].get(operation, operation)
            children.append(child)
        for target, parameter in macro["parameter_mapping"].items():
            index, field = target.split(".", 1)
            children[int(index)][field] = copy.deepcopy(values[parameter])
        expanded.extend(children)
    output["steps"] = expanded
    if source is not None:
        errors = validate_evidence(source, output)
        if errors:
            raise ValueError("Expanded representation failed source evidence: " + "; ".join(errors))
    return output
