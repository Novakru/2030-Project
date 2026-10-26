"""Single semantic fault mutations with replayable RFC 6902 patches."""
from __future__ import annotations

import copy
from collections import defaultdict

import jsonpatch
import numpy as np

from .io import canonical, digest, load_library
from .symbolic import _known, concentrated_sulfuric, evaluate, hardware_evidence, identify_solvent
from .reactivity import groups as reactive_groups

SOFT = {"C1", "C2", "C3", "C4", "C6"}


def negative_fingerprint(sample):
    from .xdl import canonical_hash
    protocol = sample["protocol"]
    return digest({"xdl": canonical_hash(protocol), "hardware": protocol["hardware"],
                   "context": protocol.get("context"), "risk": sample["label"]["risk_l2"]})


def signature(protocol):
    reagents = {r["id"]: (r.get("smiles") or r["name"], r.get("role")) for r in protocol["reagents"]}
    adds = sorted((reagents[s["reagent"]], canonical(s.get("amount"))) for s in protocol["steps"]
                  if s["op"] == "Add" and s["reagent"] in reagents)
    temperatures = sorted(s["temp_C"] for s in protocol["steps"] if s.get("temp_C") is not None)
    durations = sorted(s["duration_s"] for s in protocol["steps"] if s.get("duration_s") is not None)
    return digest({"class": protocol.get("reaction_class"), "adds": adds, "temperatures": temperatures,
                   "durations": durations, "gas": sorted(s.get("gas") for s in protocol["steps"] if s["op"] == "Atmosphere")})


def make_negative(parent, child, risk, evidence, *, origin="observed_parent"):
    parent_result, child_result = evaluate(parent), evaluate(child)
    if parent_result.risks:
        return None
    soft = risk in SOFT
    if child_result.risks != ([] if soft else [risk]):
        return None
    # Recompute derived exports before constructing the patch; never retain the parent's XML/quality verdict.
    if "quality" in child:
        child["quality"] = {"tier": "perturbed", "full_feasibility_certified": False,
                            "symbolic_violations": child_result.risks, "inherited_parent_review": "pending"}
        child["crosscheck"] = {"status": "intentionally_perturbed", "raw_id": parent.get("raw_id")}
    if "xdl" in child:
        from .xdl import canonical_hash, export_xdl
        child["xdl"] = export_xdl(child)
        child["canonical_sha1"] = canonical_hash(child)
    patch = jsonpatch.make_patch(parent, child).patch
    if not patch:
        return None
    if jsonpatch.apply_patch(copy.deepcopy(parent), patch) != child:
        raise AssertionError("Mutation patch does not reproduce child")
    record = {"id": "neg_" + risk + "_" + digest({"parent": parent["id"], "patch": patch})[:16],
              "parent_id": parent["id"], "source": parent["source"], "origin": origin,
              "benchmark_eligible": (origin != "authored_control" and parent.get("quality", {}).get("tier") == "gold" and not soft),
              "reaction_smiles": parent.get("reaction_smiles"), "protocol": child, "diff": patch,
              "mutation": {"risk": risk, "semantic_fault_count": 1, "precondition_evidence": evidence},
              "label": {"feasible": None if soft else False, "label_type": "soft" if soft else "hard",
                        "p_infeasible": None if soft else 1.0, "risk_l1": risk[0], "risk_l2": risk,
                        "judge": "hypothesis_unadmitted" if soft else "symbolic",
                        "evidence": evidence if soft else child_result.violations,
                        "scope": "declared_constraints_only; no experimental failure claim"},
              "audit": {"parent_risks": parent_result.risks, "child_risks": child_result.risks,
                        "parent_unknown_constraints": len(parent_result.unknowns),
                        "child_unknown_constraints": len(child_result.unknowns), "replay_exact": True}}
    if risk.startswith("A"):
        record["audit"]["hardware_evidence_levels"] = sorted({level for node in child["hardware"]["nodes"].values()
                                                                 if (level := hardware_evidence(node))})
    if soft:
        record["label"]["evidence"] = evidence
        record["label"]["calibrated"] = False
    return record


def corpus_reference(raws):
    data = defaultdict(lambda: {"temperatures": [], "durations": [], "solvents": set()})
    props = load_library("properties.yaml")
    for raw in raws:
        entry = data[raw["reaction_class"]]
        if raw.get("temperature"):
            entry["temperatures"].append(raw["temperature"]["value"])
        if raw.get("duration"):
            entry["durations"].append(raw["duration"]["value"])
        for r in raw["components"]:
            if r["role"] == "SOLVENT" and (not r.get("amount") or r["amount"]["value"] > 0):
                entry["solvents"].add(identify_solvent(r, props) or r.get("smiles") or r["name"])
    return data


def proposals(parent, reference):
    """Preconditions precede mutation; there is no fallback that changes extra fields to force acceptance."""
    props = load_library("properties.yaml")
    ref = reference.get(parent.get("reaction_class"), {})
    adds = [i for i, s in enumerate(parent["steps"]) if s["op"] == "Add"]
    heat = [i for i, s in enumerate(parent["steps"]) if s["op"] == "HeatChill" and s.get("temp_C") is not None]
    reagents_by_id = {r["id"]: r for r in parent["reagents"]}
    nodes = parent["hardware"]["nodes"]
    for i in adds:
        step = parent["steps"][i]
        vessel = nodes.get(step.get("vessel", "reactor"), {})
        capacity = _known(vessel, "capacity_mL")
        if capacity is not None and capacity > 0 and (step.get("amount") or {}).get("unit") == "mL":
            child = copy.deepcopy(parent)
            child["steps"][i]["amount"]["value"] = capacity + max(1, capacity * 0.1)
            yield "A1", child, {"precondition": "sourced_capacity_and_existing_volume", "capacity_mL": capacity}
            break
    controller = nodes.get(parent["hardware"].get("bindings", {}).get("heater", "heater"), {})
    for i in heat:
        step = parent["steps"][i]
        field = "controller_setpoint_C" if "controller_setpoint_C" in step else "temp_C" if controller.get("sample_temperature_validated") else None
        if field:
            for name, delta in (("T_min_C", -10), ("T_max_C", 10)):
                bound = _known(controller, name)
                if bound is not None:
                    child = copy.deepcopy(parent)
                    child["steps"][i][field] = bound + delta
                    yield "A2", child, {"precondition": "verified_range_and_explicit_temperature_mapping", "parameter": field, "bound": name}
        elif _known(controller, "T_max_C") is not None:
            # Inject an explicit device command, rather than infer the original
            # controller setpoint from a reported liquid temperature.
            child = copy.deepcopy(parent)
            child["steps"][i]["controller_setpoint_C"] = _known(controller, "T_max_C") + 10
            yield "A2", child, {"precondition": "sourced_controller_setpoint_limit", "introduced_parameter": True,
                                "scope": "explicit device request; no sample-to-controller conversion inferred"}
    for i, step in enumerate(parent["steps"]):
        upper = _known(controller, "rpm_max")
        if "rpm" in step and step["op"] in ("Stir", "HeatChill") and upper is not None:
            child = copy.deepcopy(parent)
            child["steps"][i]["rpm"] = upper + max(1, abs(upper) * 0.1)
            yield "A3", child, {"precondition": "existing_rpm_and_verified_speed_range", "rpm_max": upper}
            break
    for i in adds:
        step = parent["steps"][i]
        vessel = nodes.get(step.get("vessel", "reactor"), {})
        reagent = reagents_by_id.get(step["reagent"], {})
        if not hardware_evidence(vessel) or reagent.get("role") not in ("REAGENT", "CATALYST"):
            continue
        pairs = [p for p in props.get("compatibility", []) if p["chemical"] == "hydrofluoric_acid"
                 and p["material"] in (vessel.get("wetted_materials") or [])]
        if pairs:
            child = copy.deepcopy(parent)
            replacement = next(r for r in child["reagents"] if r["id"] == reagent["id"])
            replacement.update(name="hydrofluoric acid", chemical="hydrofluoric_acid", smiles="F")
            yield "A4", child, {"precondition": "verified_wetted_material_and_sourced_incompatibility", "source_url": pairs[0]["source_url"]}
            break
    solids = [i for i in adds if reagents_by_id[parent["steps"][i]["reagent"]].get("role") != "SOLVENT"]
    if len(solids) >= 2:
        first, second = [reagents_by_id[parent["steps"][i]["reagent"]] for i in solids[:2]]
        # An existing free acid and a substituted reagent meet before any other
        # non-solvent input or reaction hold. Do not assume a neutralized acid remains free.
        if (first.get("role") in ("REAGENT", "CATALYST") and "carboxylic_acid" in reactive_groups(second)
                and not any(s["op"] not in ("Add", "Atmosphere") for s in parent["steps"][:solids[1]])):
            child = copy.deepcopy(parent)
            replacement = next(r for r in child["reagents"] if r["id"] == first["id"])
            replacement.update(name="sodium cyanide", smiles="[C-]#N.[Na+]", chemical="sodium_cyanide")
            yield "B4", child, {"precondition": "free_carboxylic_acid_before_other_solutes", "substituted_reagent": first["id"],
                                "source_url": "https://cameochemicals.noaa.gov/reactivity/documentation/RG3-RG11"}
    if heat:
        child = copy.deepcopy(parent)
        binding = child["hardware"]["bindings"].get("heater")
        if binding in child["hardware"]["nodes"]:
            del child["hardware"]["nodes"][binding]
            yield "A5", child, {"precondition": "bound_controller_present"}
        if parent.get("context", {}).get("pressure_control") == "SEALED" and not parent["context"].get("reflux"):
            solvents = {identify_solvent(r, props) for r in parent["reagents"] if r.get("role") == "SOLVENT"}
            solvents.discard(None)
            if len(solvents) == 1:
                name = next(iter(solvents))
                bp = props["solvents"][name].get("bp_C")
                if bp is not None and any(parent["steps"][i]["temp_C"] > bp for i in heat):
                    child = copy.deepcopy(parent)
                    child["context"]["pressure_control"] = "OPEN"
                    yield "B1", child, {"precondition": "sealed_above_normal_bp", "solvent": name, "bp_C": bp}
        solvents = {identify_solvent(r, props) for r in parent["reagents"] if r.get("role") == "SOLVENT"}
        solvents.discard(None)
        if len(solvents) == 1:
            solvent = next(iter(solvents))
            melting = props["solvents"][solvent].get("mp_C")
            if parent.get("context", {}).get("pure_solvent") and melting is not None:
                child = copy.deepcopy(parent)
                child["steps"][heat[-1]]["temp_C"] = melting - 10
                yield "B2", child, {"precondition": "explicit_pure_solvent_and_known_melting_point", "solvent": solvent}
            flash = props["solvents"][solvent].get("flash_C")
            context = parent.get("context", {})
            if (context.get("vapor_exposed") and context.get("ignition_source") is False
                    and context.get("pressure_control") in ("OPEN", "AMBIENT") and flash is not None
                    and any(parent["steps"][i]["temp_C"] > flash for i in heat)):
                child = copy.deepcopy(parent)
                child["context"]["ignition_source"] = True
                yield "B3", child, {"precondition": "explicit_exposed_flammable_vapor_above_flashpoint", "solvent": solvent}
    for op, component in (("Filter", "filter"), ("Separate", "separator")):
        if component in nodes and any(s["op"] == op for s in parent["steps"]):
            child = copy.deepcopy(parent)
            del child["hardware"]["nodes"][component]
            yield "A5", child, {"precondition": "existing_" + op.lower() + "_requires_component", "component": component}
    for vessel in sorted({parent["steps"][i].get("vessel", "reactor") for i in adds}):
        local = [i for i in adds if parent["steps"][i].get("vessel", "reactor") == vessel]
        if len(local) >= 2 and parent.get("context", {}).get("purpose") == "acid_dilution":
            water, acid = [reagents_by_id[parent["steps"][i]["reagent"]] for i in local[:2]]
            if water.get("chemical") == "water" and concentrated_sulfuric(acid):
                child = copy.deepcopy(parent)
                a, b = local[:2]
                child["steps"][a], child["steps"][b] = child["steps"][b], child["steps"][a]
                yield "B5", child, {"precondition": "documented_concentrated_acid_dilution_order"}
    required = parent.get("constraints", {}).get("required_steps", [])
    for requirement in required:
        if requirement.get("source_url"):
            for i, step in enumerate(parent["steps"]):
                if step["id"] == requirement["id"]:
                    child = copy.deepcopy(parent)
                    del child["steps"][i]
                    yield "D2", child, {"precondition": "explicit_source_required_step", "requirement": requirement}
    gas_steps = [i for i, s in enumerate(parent["steps"]) if s["op"] == "Atmosphere"]
    if parent.get("context", {}).get("inert_required") and len(gas_steps) == 1:
        child = copy.deepcopy(parent)
        del child["steps"][gas_steps[0]]
        yield "C5", child, {"precondition": "source_explicit_oxygen_sensitivity", "basis": parent["context"]["inert_required"]}
    if adds:
        child = copy.deepcopy(parent)
        child["steps"][adds[0]]["reagent"] = "undeclared_reagent"
        yield "D3", child, {"precondition": "declared_initial_reagent"}
        child = copy.deepcopy(parent)
        child["steps"][adds[0]]["amount"]["unit"] = "s"
        yield "D4", child, {"precondition": "material_quantity", "dimension_change": "material_to_time"}
    # Undefined vessel and undefined reagent are distinct reference failures;
    # use only operations actually present in the source-derived procedure.
    for op in ("Add", "HeatChill", "Transfer", "Filter", "Separate"):
        target = next((i for i, s in enumerate(parent["steps"]) if s["op"] == op), None)
        if target is not None:
            child = copy.deepcopy(parent)
            key = "to_vessel" if op == "Transfer" else "vessel"
            child["steps"][target][key] = "undeclared_vessel"
            yield "D3", child, {"precondition": "existing_operation_with_declared_vessel", "operation": op, "reference_type": key}
    if heat and adds:
        # This is a data-flow dependency: a reaction hold requires its charged inputs.
        child = copy.deepcopy(parent)
        held = child["steps"].pop(heat[-1])
        child["steps"].insert(0, held)
        yield "D1", child, {"precondition": "charged_input_dependencies"}
    for i, reagent in enumerate(parent["reagents"]):
        if reagent.get("role") != "SOLVENT":
            continue
        original = identify_solvent(reagent, props)
        if not original:
            continue
        for replacement, parameters in props["solvents"].items():
            if replacement in ref.get("solvents", set()) or replacement == original:
                continue
            if parameters["family"] == props["solvents"][original]["family"]:
                continue
            child = copy.deepcopy(parent)
            # One reagent identity substitution; amounts and operations remain untouched.
            child["reagents"][i].update(name=replacement, smiles=parameters["smiles"])
            yield "C1", child, {"original": original, "replacement": replacement,
                               "seen_in_observed_class": False, "corpus_class": parent.get("reaction_class"),
                               "calibration": "unavailable", "precondition": "different_solvent_family"}
    if heat and len(ref.get("temperatures", [])) >= 20:
        low, high = np.quantile(ref["temperatures"], [0.01, 0.99]).tolist()
        child = copy.deepcopy(parent)
        original = child["steps"][heat[-1]]["temp_C"]
        child["steps"][heat[-1]]["temp_C"] = round(low - 10, 4)
        if child["steps"][heat[-1]]["temp_C"] != original:
            yield "C2", child, {"q01_C": low, "q99_C": high, "class_count": len(ref["temperatures"]), "shift_C": -10}
    catalyst_ids = {r["id"] for r in parent["reagents"] if r.get("role") == "CATALYST"}
    catalyst_adds = [i for i in adds if parent["steps"][i]["reagent"] in catalyst_ids]
    if catalyst_adds:
        child = copy.deepcopy(parent)
        removed = child["steps"].pop(catalyst_adds[0])
        yield "C3", child, {"removed_catalyst": removed["reagent"], "outcome": "unknown"}
    mutated_roles = set()
    for i in adds:
        amount = parent["steps"][i].get("amount")
        role = reagents_by_id[parent["steps"][i]["reagent"]].get("role")
        if amount and amount["unit"] == "mmol" and role not in mutated_roles:
            mutated_roles.add(role)
            child = copy.deepcopy(parent)
            child["steps"][i]["amount"]["value"] *= 10
            yield "C4", child, {"amount_scale": 10, "original": amount, "reagent_role": role}
    durations = [i for i, s in enumerate(parent["steps"]) if s.get("duration_s", 0) > 0]
    if durations and len(ref.get("durations", [])) >= 20:
        low = float(np.quantile(ref["durations"], 0.01))
        child = copy.deepcopy(parent)
        target = durations[-1]
        child["steps"][target]["duration_s"] = round(max(0.001, low * 0.001), 6)
        yield "C6", child, {"q01_seconds": low, "class_count": len(ref["durations"]), "factor": 0.001}


def generate_observed(parents, raw_records, per_risk=12, success_index=None):
    from .diversity import select_diverse, summarize
    refs = corpus_reference(raw_records)
    pools, output, rejected, seen = defaultdict(list), [], defaultdict(int), set()
    success_signatures = {signature(p) for p in parents if p.get("yield_percent", 0) and p["yield_percent"] >= 30}
    for parent in sorted(parents, key=lambda p: p["id"]):
        for risk, child, evidence in proposals(parent, refs):
            if risk in SOFT and signature(child) in success_signatures:
                rejected["observed_success_match"] += 1
                continue
            if risk in SOFT and success_index is not None and success_index.match(child):
                rejected["full_ord_corpus_observed_success_match"] += 1
                continue
            negative = make_negative(parent, child, risk, evidence)
            if negative:
                fingerprint = negative_fingerprint(negative)
                if fingerprint in seen:
                    rejected["canonical_negative_duplicate"] += 1
                    continue
                seen.add(fingerprint)
                negative["audit"]["false_negative_filter_scope"] = "all_pinned_ORD_sources" if success_index is not None else "exported_positives_only"
                pools[risk].append(negative)
            else:
                rejected["precondition_or_multi_rule"] += 1
    parent_map = {p["id"]: p for p in parents}
    selection = {}
    for risk, candidates in sorted(pools.items()):
        selected = select_diverse(candidates, per_risk, parent_map)
        output.extend(selected)
        selection[risk] = {"candidate_pool": summarize(candidates, parent_map),
                           "selected": summarize(selected, parent_map)}
    counts = {risk: len([s for s in output if s["label"]["risk_l2"] == risk]) for risk in sorted(pools)}
    return output, {"counts": counts, "rejected": dict(rejected), "selection": selection}
