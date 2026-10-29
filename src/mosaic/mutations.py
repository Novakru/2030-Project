"""Mechanism proposals share a program-enforced single-intervention contract."""
from __future__ import annotations

import copy
import math
from collections import Counter, defaultdict

import jsonpatch
from jsonpointer import JsonPointerException

from protocol_risk.diversity import features
from protocol_risk.io import canonical, digest, load_library
from protocol_risk.mutation_rules import SOFT, corpus_reference, make_negative, negative_fingerprint, proposals
from protocol_risk.symbolic import _known, evaluate, identify_solvent


def _leaves(value, prefix=""):
    if isinstance(value, dict):
        result = {}
        for key, child in value.items():
            result.update(_leaves(child, prefix + "/" + str(key)))
        return result or {prefix: value}
    return {prefix: value}


def assess_intervention(parent, child):
    """Check actual semantic edits, never trust a declared fault count."""
    from protocol_risk.normalization import analysis_protocol, is_normalized
    if is_normalized(parent) or is_normalized(child):
        return assess_intervention(analysis_protocol(parent), analysis_protocol(child))
    operational = {"steps", "reagents", "hardware", "context", "initial_contents"}
    derived = {"quality", "crosscheck", "xdl", "canonical_sha1"}
    for key in set(parent) | set(child):
        if key not in operational | derived and parent.get(key) != child.get(key):
            raise ValueError("Mutation changed provenance or an unsupported field")
    changed = [key for key in operational if parent.get(key) != child.get(key)]
    if len(changed) != 1:
        raise ValueError("Expected exactly one operational intervention")
    section = changed[0]
    if section == "steps":
        left, right = parent[section], child[section]
        a, b = [s["id"] for s in left], [s["id"] for s in right]
        if len(set(a)) != len(a) or len(set(b)) != len(b):
            raise ValueError("Step IDs must remain unique")
        old, new = {s["id"]: s for s in left}, {s["id"]: s for s in right}
        if any(old[k] != new[k] for k in set(a) & set(b)):
            if a != b:
                raise ValueError("Step modification cannot also change sequence")
            edits = [k for k in a if old[k] != new[k]]
            if len(edits) != 1:
                raise ValueError("Multiple steps were changed")
            x, y = _leaves(old[edits[0]]), _leaves(new[edits[0]])
            fields = [k for k in set(x) | set(y) if x.get(k) != y.get(k)]
            permitted = {"/amount/value", "/amount/unit", "/temp_C", "/controller_setpoint_C", "/duration_s", "/rpm",
                         "/reagent", "/vessel", "/from_vessel", "/to_vessel", "/gas", "/mode"}
            if len(fields) != 1 or fields[0] not in permitted:
                raise ValueError("Step intervention must change one supported operational field")
            value = y.get(fields[0])
            if fields[0] in {"/amount/value", "/temp_C", "/controller_setpoint_C", "/duration_s", "/rpm"}:
                if not isinstance(value, (float, int)) or isinstance(value, bool) or not math.isfinite(value):
                    raise ValueError("Operational number must be finite and numeric")
            elif not isinstance(value, str) or not value:
                raise ValueError("Operational reference or unit must be a nonempty string")
            return {"count": 1, "kind": "step_parameter", "step_id": edits[0], "field": fields[0]}
        removed, added = set(a) - set(b), set(b) - set(a)
        if len(removed) == 1 and not added and [k for k in a if k not in removed] == b:
            return {"count": 1, "kind": "remove_step", "step_id": next(iter(removed))}
        if not removed and not added and a != b:
            for identifier in a:
                if [k for k in a if k != identifier] == [k for k in b if k != identifier]:
                    return {"count": 1, "kind": "move_step", "step_id": identifier}
        raise ValueError("Unsupported or compound sequence intervention")
    if section == "reagents":
        left, right = parent[section], child[section]
        if len(left) != len(right):
            raise ValueError("Reagent declaration deletion is not a material intervention")
        edits = [i for i, (a, b) in enumerate(zip(left, right)) if a != b]
        if len(edits) != 1:
            raise ValueError("Multiple reagent identities changed")
        a, b = left[edits[0]], right[edits[0]]
        keys = {k for k in set(a) | set(b) if a.get(k) != b.get(k)}
        if not keys <= {"name", "smiles", "chemical"}:
            raise ValueError("Identity substitution cannot alter amount, role or evidence")
        return {"count": 1, "kind": "reagent_identity", "reagent_id": a["id"]}
    if section == "hardware":
        a, b = copy.deepcopy(parent[section]), copy.deepcopy(child[section])
        old_nodes, new_nodes = a.pop("nodes"), b.pop("nodes")
        removed = set(old_nodes) - set(new_nodes)
        if len(removed) == 1 and not set(new_nodes) - set(old_nodes) and all(new_nodes[k] == old_nodes[k] for k in new_nodes) and a == b:
            return {"count": 1, "kind": "remove_device", "device_id": next(iter(removed))}
        if old_nodes != new_nodes:
            raise ValueError("Mutation cannot rewrite equipment specifications or source evidence")
        old_edges, new_edges = a.pop("edges", []), b.pop("edges", [])
        if a == b and len(old_edges) == len(new_edges) + 1 and all(e in old_edges for e in new_edges):
            return {"count": 1, "kind": "remove_path"}
        if old_edges != new_edges:
            raise ValueError("Compound topology intervention")
        old_bindings, new_bindings = a.pop("bindings", {}), b.pop("bindings", {})
        keys = [k for k in set(old_bindings) | set(new_bindings) if old_bindings.get(k) != new_bindings.get(k)]
        if a == b and len(keys) == 1:
            if not isinstance(new_bindings.get(keys[0]), str) or not new_bindings[keys[0]]:
                raise ValueError("Binding target must be a nonempty identifier")
            return {"count": 1, "kind": "binding", "binding": keys[0]}
        raise ValueError("Compound hardware intervention")
    if section == "context":
        left, right = parent[section], child[section]
        keys = [k for k in set(left) | set(right) if left.get(k) != right.get(k)]
        if len(keys) == 1 and keys[0] in ("pressure_control", "reflux", "ignition_source", "oxygen_present"):
            if keys[0] == "pressure_control" and right[keys[0]] not in ("OPEN", "AMBIENT", "SEALED", "UNKNOWN"):
                raise ValueError("Unsupported pressure-control context")
            ignition_kind = keys[0] == "ignition_source" and right[keys[0]] in ("bunsen_burner", "hot_air_gun")
            if keys[0] != "pressure_control" and not isinstance(right[keys[0]], bool) and not ignition_kind:
                raise ValueError("Operational context flag must be boolean")
            return {"count": 1, "kind": "context", "field": keys[0]}
    raise ValueError("Unsupported intervention")


def fault_instances(protocol, violations):
    """Group repeated downstream reports of the same corrupted constraint object."""
    from protocol_risk.normalization import analysis_protocol, is_normalized
    if is_normalized(protocol):
        return fault_instances(analysis_protocol(protocol), violations)
    steps = {s["id"]: s for s in protocol["steps"]}
    instances = set()
    for entry in violations:
        values, risk = entry.get("values", {}), entry["risk"]
        step = steps.get(values.get("step_id"), {})
        vessel = step.get("to_vessel", step.get("vessel", "reactor"))
        if risk == "A5":
            target = values.get("controller") or values.get("component") or (values.get("from"), values.get("to"))
        elif risk == "D3":
            target = tuple(values.get("references", []))
        elif risk == "D4":
            target = values.get("step_id")
        elif risk == "D1":
            target = (values.get("step_id"), entry["rule_id"])
        elif risk == "B4":
            target = (vessel, canonical(values.get("pair")))
        elif risk == "A1":
            target = ("syringe" if "syringe" in entry["rule_id"] else "vessel", vessel)
        else:
            target = (vessel, values.get("controller"), values.get("solvent"), values.get("material"))
        instances.add((risk, canonical(target)))
    return sorted(instances)


def extra_proposals(parent):
    nodes = parent["hardware"]["nodes"]
    controller = nodes.get(parent["hardware"].get("bindings", {}).get("heater"), {})
    low = _known(controller, "rpm_min")
    properties = load_library("properties.yaml")
    solvents = {identify_solvent(r, properties) for r in parent["reagents"] if r.get("role") == "SOLVENT"}
    if (len(solvents) == 1 and None not in solvents and parent.get("context", {}).get("pressure_control") in ("OPEN", "AMBIENT")
            and not parent.get("context", {}).get("reflux")):
        solvent_name = next(iter(solvents))
        boiling_point = properties["solvents"][solvent_name].get("bp_C")
        if boiling_point is not None:
            for i, step in enumerate(parent["steps"]):
                if step["op"] == "HeatChill" and step.get("temp_C") is not None and step["temp_C"] <= boiling_point:
                    child = copy.deepcopy(parent)
                    child["steps"][i]["temp_C"] = boiling_point + 10
                    yield "B1", child, {"precondition": "source_open_single_known_solvent_without_reflux", "solvent": solvent_name,
                                        "bp_C": boiling_point, "source_url": properties["solvents"][solvent_name]["source_url"]}
    volumes = defaultdict(float)
    for i, step in enumerate(parent["steps"]):
        vessel = step.get("vessel", "reactor")
        amount = step.get("amount", {})
        capacity = _known(nodes.get(vessel, {}), "capacity_mL")
        if step["op"] == "Evaporate":
            volumes[vessel] = 0
        if step["op"] == "Add" and amount.get("unit") == "mL":
            previous = volumes[vessel]
            if capacity and 0 < previous < capacity:
                child = copy.deepcopy(parent)
                child["steps"][i]["amount"]["value"] = capacity - previous / 2
                yield "A1", child, {"mechanism": "A1.cumulative_overfill", "precondition": "earlier_quantified_liquid_in_same_vessel"}
            if capacity and any(s["op"] in ("HeatChill", "Stir") and s.get("vessel", "reactor") == vessel for s in parent["steps"][i + 1:]):
                value = .75 * capacity - previous
                if value > 0:
                    child = copy.deepcopy(parent)
                    child["steps"][i]["amount"]["value"] = value
                    yield "A1", child, {"mechanism": "A1.active_fill_fraction", "precondition": "configured_two_thirds_fill_rule",
                                       "scope": "declared analysis constraint; not a universal vessel rating"}
            volumes[vessel] += amount["value"]
        if "rpm" in step and low is not None and low > 1:
            child = copy.deepcopy(parent)
            child["steps"][i]["rpm"] = low / 2
            yield "A3", child, {"mechanism": "A3.below_active_speed_range", "precondition": "positive_source_controller_minimum"}
        if amount and step["op"] == "Add":
            child = copy.deepcopy(parent)
            child["steps"][i]["amount"]["value"] = -abs(amount["value"])
            yield "D4", child, {"mechanism": "D4.nonpositive_quantity", "precondition": "quantified_existing_add"}
    if any(s["op"] == "HeatChill" for s in parent["steps"]) and "heater" in parent["hardware"].get("bindings", {}):
        for target, mechanism in (("reactor", "A5.incompatible_bound_capability"), ("undeclared_controller", "A5.unresolved_binding")):
            child = copy.deepcopy(parent)
            child["hardware"]["bindings"]["heater"] = target
            yield "A5", child, {"mechanism": mechanism, "precondition": "existing_heat_request_and_controller_binding"}
    reagents = {r["id"]: r for r in parent["reagents"]}
    solvent = next((r for r in parent["reagents"] if r.get("role") == "SOLVENT" and r.get("smiles")), None)
    if solvent:
        for i, reagent in enumerate(parent["reagents"]):
            if reagent.get("role") == "CATALYST" and reagent.get("smiles") != solvent["smiles"]:
                child = copy.deepcopy(parent)
                for key in ("name", "smiles", "chemical"):
                    if key in solvent:
                        child["reagents"][i][key] = solvent[key]
                    else:
                        child["reagents"][i].pop(key, None)
                yield "C3", child, {"precondition": "existing_catalyst_and_source_solvent", "replacement": solvent["id"],
                                    "scope": "Wrong material in the catalyst slot; outcome remains an uncalibrated hypothesis."}
    for i, step in enumerate(parent["steps"]):
        if step["op"] == "Add" and step.get("amount", {}).get("unit") == "mmol":
            child = copy.deepcopy(parent)
            child["steps"][i]["amount"]["value"] *= .01
            yield "C4", child, {"precondition": "source_molar_loading", "direction": "depleted",
                                "reagent_role": reagents[step["reagent"]].get("role"), "observed_failure": False}
        if step.get("duration_s", 0) > 0:
            child = copy.deepcopy(parent)
            child["steps"][i]["duration_s"] *= 100
            yield "C6", child, {"precondition": "explicit_source_hold", "direction": "extended", "observed_failure": False}


def _mechanism(parent, child, risk, evidence, intervention):
    # A model's chosen name is never evidence of a new mechanism.
    rules = {v["rule_id"] for v in evaluate(child).violations if v["risk"] == risk}
    if risk == "A1":
        if "A1.fill_fraction" in rules:
            return "A1.active_fill_fraction"
        if intervention["kind"] == "step_parameter":
            step = next(s for s in child["steps"] if s["id"] == intervention["step_id"])
            capacity = _known(child["hardware"]["nodes"].get(step.get("vessel", "reactor"), {}), "capacity_mL")
            value = step.get("amount", {}).get("value")
            if capacity and value is not None:
                return "A1.single_add_overfill" if value > capacity else "A1.cumulative_overfill"
    if risk == "A5":
        if intervention["kind"] == "binding":
            return "A5.incompatible_bound_capability" if "A5.controller_capability_mismatch" in rules else "A5.unresolved_binding"
        if intervention["kind"] == "remove_device":
            device = parent["hardware"]["nodes"][intervention["device_id"]]
            category = device.get("category", "unknown")
            return "A5.missing_" + ("controller" if category in ("heater", "heater_stirrer", "chiller") else category)
        return "A5.disconnected_path"
    if risk == "D4":
        return "D4.nonpositive_quantity" if "D4.nonpositive_quantity" in rules else "D4.incompatible_dimension"
    if risk == "B1":
        return "B1.overheat_open_liquid" if intervention["kind"] == "step_parameter" else "B1.open_hot_closed_vessel"
    if risk == "C1":
        return "C1.solvent_family_substitution"
    if risk == "C3":
        return "C3.catalyst_omission" if intervention["kind"] == "remove_step" else "C3.catalyst_identity_substitution"
    if risk == "C2" and intervention["kind"] == "step_parameter":
        before = next(s for s in parent["steps"] if s["id"] == intervention["step_id"])
        after = next(s for s in child["steps"] if s["id"] == intervention["step_id"])
        return "C2." + ("cooler_than_source" if after["temp_C"] < before["temp_C"] else "hotter_than_source")
    if risk in ("A2", "A3") and intervention["kind"] == "step_parameter":
        step = next(s for s in child["steps"] if s["id"] == intervention["step_id"])
        field = intervention["field"].strip("/")
        original = next(s for s in parent["steps"] if s["id"] == intervention["step_id"])
        direction = "below" if field in original and step[field] < original[field] else "above"
        return risk + "." + direction + "_controller_range"
    if intervention["kind"] == "step_parameter":
        original = next(s for s in parent["steps"] if s["id"] == intervention["step_id"])
        if risk == "C4":
            reagent = next(r for r in parent["reagents"] if r["id"] == original.get("reagent"))
            modified = next(s for s in child["steps"] if s["id"] == intervention["step_id"])
            direction = "depleted" if modified["amount"]["value"] < original["amount"]["value"] else "excess"
            return "C4." + direction + "_" + str(reagent.get("role", "unknown")).lower()
        if risk == "C6":
            modified = next(s for s in child["steps"] if s["id"] == intervention["step_id"])
            direction = "shortened" if modified["duration_s"] < original["duration_s"] else "extended"
            return "C6." + direction + "_" + original["op"].lower()
        if risk == "D3":
            return "D3.undefined_" + intervention["field"].strip("/")
    return risk + "." + intervention["kind"]


def _soft_intent(risk, intervention, parent):
    kind = intervention["kind"]
    if risk == "C1" and kind == "reagent_identity":
        return any(r["id"] == intervention["reagent_id"] and r.get("role") == "SOLVENT" for r in parent["reagents"])
    if risk == "C3":
        if kind == "reagent_identity":
            return any(r["id"] == intervention["reagent_id"] and r.get("role") == "CATALYST" for r in parent["reagents"])
        if kind == "remove_step":
            step = next(s for s in parent["steps"] if s["id"] == intervention["step_id"])
            return step["op"] == "Add" and any(r["id"] == step.get("reagent") and r.get("role") == "CATALYST" for r in parent["reagents"])
    return kind == "step_parameter" and intervention.get("field") == {"C2": "/temp_C", "C4": "/amount/value", "C6": "/duration_s"}.get(risk)


PERTURB_PROMPT = """You propose counterfactual errors for a source-derived protocol dataset, never perform experiments.
Return JSON {"proposals":[{"risk":str,"patch":[ONE RFC6902 operation],"rationale":str}]}.
Use only known risk classes and existing operations, quantities and apparatus roles.
Vary failure mechanisms, not random numeric values. Each proposal is one semantic intervention.
Allowed targets are one operational step parameter, one reagent identity, a device deletion, one connection deletion, one binding, or one operational context field.
Never edit provenance, evidence, quality, verification, equipment ratings/materials, required-step constraints, or claim observed failure.
Soft risks are uncalibrated hypotheses, not failed reactions. A program independently validates every proposal."""


def model_proposals(parent, runner):
    payload = {k: parent[k] for k in ("steps", "reagents", "hardware", "context") if k in parent}
    response = runner.model_call("perturber", PERTURB_PROMPT, payload)
    output = response["data"]
    if not isinstance(output, dict) or not isinstance(output.get("proposals"), list):
        raise ValueError("Invalid model perturbation proposals")
    for proposal in output["proposals"]:
        if not isinstance(proposal, dict):
            continue
        patch = proposal.get("patch", [])
        if not isinstance(patch, list) or len(patch) != 1:
            continue
        edit = patch[0]
        if not isinstance(edit, dict):
            continue
        if edit.get("op") not in ("add", "remove", "replace", "move"):
            continue
        if any(key in edit and not str(edit[key]).startswith(("/steps/", "/reagents/", "/hardware/", "/context/")) for key in ("path", "from")):
            continue
        try:
            child = jsonpatch.apply_patch(copy.deepcopy(parent), patch)
        except (jsonpatch.JsonPatchException, JsonPointerException, KeyError, IndexError, TypeError):
            continue
        yield proposal.get("risk"), child, {"precondition": "model_proposal_program_checked", "rationale": proposal.get("rationale"), "proposal_engine": "llm"}


def generate(parents, raw_records, *, per_risk=12, success_index=None, runner=None, llm_limit=0):
    from protocol_risk.normalization import analysis_protocol, is_normalized
    if any(is_normalized(parent) for parent in parents):
        if not all(is_normalized(parent) for parent in parents):
            raise ValueError("A mutation batch must use one naming standard")
        from .canonical import finalize_negative
        projected = [analysis_protocol(parent) for parent in parents]
        samples, report = generate(projected, raw_records, per_risk=per_risk,
                                   success_index=success_index, runner=runner, llm_limit=llm_limit)
        by_id = {parent["id"]: parent for parent in parents}
        return [finalize_negative(sample, by_id[sample["parent_id"]]) for sample in samples], report
    references = corpus_reference(raw_records)
    pools, rejected, seen = defaultdict(list), Counter(), set()
    known_risks = set(load_library("risks.yaml")["risks"])
    for index, parent in enumerate(parents):
        candidates = list(proposals(parent, references)) + list(extra_proposals(parent))
        if runner and index < llm_limit:
            try:
                candidates.extend(model_proposals(parent, runner))
            except (ValueError, RuntimeError):
                rejected["model_proposal_stage_failed"] += 1
        for risk, child, evidence in candidates:
            if not isinstance(risk, str) or risk not in known_risks:
                rejected["unknown_risk"] += 1
                continue
            try:
                intervention = assess_intervention(parent, child)
            except (ValueError, KeyError, IndexError, TypeError, AttributeError) as error:
                if isinstance(error, AttributeError) and evidence.get("proposal_engine") != "llm":
                    raise
                rejected[str(error)] += 1
                continue
            if risk in SOFT and not _soft_intent(risk, intervention, parent):
                rejected["soft_risk_intervention_mismatch"] += 1
                continue
            if risk in SOFT and success_index is not None and success_index.match(child):
                rejected["known_success"] += 1
                continue
            try:
                result = evaluate(child)
                instances = fault_instances(child, result.violations)
            except (ValueError, KeyError, IndexError, TypeError, AttributeError):
                if evidence.get("proposal_engine") != "llm":
                    raise
                rejected["malformed_model_intervention"] += 1
                continue
            if risk not in SOFT and len(instances) != 1:
                rejected["multiple_or_missing_fault_instances"] += 1
                continue
            origin = "authored_control" if parent.get("source", {}).get("db") == "AUTHORED_CONTROL" else "observed_parent"
            try:
                sample = make_negative(parent, child, risk, evidence, origin=origin)
            except (ValueError, KeyError, IndexError, TypeError, AttributeError):
                if evidence.get("proposal_engine") != "llm":
                    raise
                rejected["malformed_model_intervention"] += 1
                continue
            if sample is None:
                rejected["parent_or_target_risk_mismatch"] += 1
                continue
            fingerprint = negative_fingerprint(sample)
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            sample["id"] = "mosaic_" + sample["id"]
            sample["mutation"].update(mechanism_id=_mechanism(parent, child, risk, evidence, intervention),
                                       intervention=intervention, fault_instances=instances,
                                       semantic_fault_count_verified=True)
            sample["audit"]["false_negative_filter_scope"] = "all_pinned_ORD_sources" if success_index else "not_applied"
            pools[risk].append(sample)
    output, coverage = [], {}
    mapping = {p["id"]: p for p in parents}
    for risk, candidates in sorted(pools.items()):
        # Choose novel independently identified mechanisms before ordinary diversity.
        profiles = {s["id"]: features(s, mapping[s["parent_id"]]) for s in candidates}
        mechanisms = sorted({s["mutation"]["mechanism_id"] for s in candidates})
        mechanism_counts, parent_counts, source_counts = Counter(), Counter(), Counter()
        selected = []
        remaining = sorted(candidates, key=lambda s: s["id"])
        while remaining and len(selected) < per_risk:
            def score(sample):
                mechanism = sample["mutation"]["mechanism_id"]
                source = profiles[sample["id"]]["source_dataset"]
                return (not mechanism_counts[mechanism], not parent_counts[sample["parent_id"]],
                        bool(source) and not source_counts[source], -mechanism_counts[mechanism],
                        -source_counts[source], -parent_counts[sample["parent_id"]])
            chosen = max(remaining, key=score)
            selected.append(chosen)
            remaining.remove(chosen)
            mechanism_counts[chosen["mutation"]["mechanism_id"]] += 1
            parent_counts[chosen["parent_id"]] += 1
            source_counts[profiles[chosen["id"]]["source_dataset"]] += 1
        output.extend(selected)
        coverage[risk] = {"candidates": len(candidates), "selected": len(selected),
                          "available_mechanisms": mechanisms,
                          "selected_mechanisms": dict(Counter(s["mutation"]["mechanism_id"] for s in selected)),
                          "parents": len({s["parent_id"] for s in selected})}
    return output, {"coverage": coverage, "rejected": dict(rejected)}
