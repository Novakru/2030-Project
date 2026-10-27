"""Source, quantity, apparatus and XDL checks for the chemistry domain."""
from __future__ import annotations
import copy
import re
from .crosscheck import crosscheck
from .extract import text_source
from .io import digest
from .symbolic import evaluate
from .xdl import PROFILE, bind_hardware, canonical_hash, export_xdl, validate_xdl

def annotate_dependencies(protocol):
    reagent_roles = {r["id"]: r.get("role") for r in protocol["reagents"]}
    charged = []
    for step in protocol["steps"]:
        if step["op"] == "Add" and reagent_roles.get(step["reagent"]) in ("REACTANT", "SOLVENT"):
            charged.append(step["id"])
        if step["op"] == "HeatChill" and step.get("duration_s") and charged:
            step["requires"] = list(charged)
    return protocol


def represented_setup(evidence, protocol):
    nodes = protocol["hardware"]["nodes"]
    vessel_fact = re.search(r"\b(micro[- ]?reactor|flask|vial)\s+(?:was|is)\s+charged(?:\s+with)?\s*$", evidence, re.I)
    heater_fact = re.search(r"\bplaced\s+into\s+(?:a\s+)?(?:pre[- ]heated|heated|alumin(?:um|ium))[^.]*\bblock\b", evidence, re.I)
    for identifier, node in nodes.items():
        if node.get("binding_basis") != "source_reported":
            continue
        cited = any(isinstance(c.get("value"), str) and evidence in c["value"] for c in node.get("source_evidence", []))
        if not cited:
            continue
        if vessel_fact and node.get("category") == "vessel":
            return {"kind": "source_vessel_setup", "device_id": identifier, "evidence": evidence}
        if heater_fact and node.get("category") == "heater":
            step = next((s for s in protocol["steps"] if s["op"] == "HeatChill" and evidence in s.get("meta", {}).get("evidence", "")), None)
            if step:
                return {"kind": "source_heater_setup", "device_id": identifier, "step_id": step["id"], "evidence": evidence}
    return None

def prepare_protocol(protocol, raw, reviews=None, devices=None):
    protocol = copy.deepcopy(protocol)
    document = text_source(raw)
    protocol["reference_metadata"] = {key: copy.deepcopy(raw[key]) for key in
        ("reaction_smiles", "reaction_class", "yield_percent", "yield_evidence") if key in raw}
    protocol["reference_metadata"]["authority"] = "reference_only_not_process_input"
    # Outcomes and database labels are not textual operating instructions.
    for key in ("yield_percent", "yield_evidence", "reaction_smiles", "reaction_class"):
        protocol.pop(key, None)
    for step in protocol["steps"]:
        evidence = step.get("meta", {}).get("evidence", "")
        bound = re.search(r"maximum\s+temperature(?:\s+of)?\s*([-+]?\d+(?:\.\d+)?)\s*(?:(?:°|º|o)\s*)?C\b", evidence, re.I)
        if step["op"] == "Evaporate" and "temp_C" in step and bound and abs(float(bound[1]) - step["temp_C"]) < 1e-6:
            step.setdefault("meta", {})["temp_upper_bound_C"] = step.pop("temp_C")
            step["meta"]["normalization"] = "source upper bound retained as a constraint, not an invented setpoint"
    bind_hardware(protocol, devices=devices, configuration=reviews.configuration(protocol["id"]) if reviews else None, raw=document)
    if protocol["extraction"]["method"] == "llm_evidence_constrained":
        pending, observations, events = [], [], []
        for action in protocol["extraction"].get("unmapped_actions", []):
            evidence = action.get("evidence", "") if isinstance(action, dict) else str(action)
            # Analytical results do not become synthesis steps. Classify explicitly and keep the source text.
            physical = re.search(r"\b(add(?:ed|ition)?|wash(?:ed)?|extract(?:ed)?|dri(?:ed|ng)|quench(?:ed)?|filter(?:ed)?|heat(?:ed)?|stirr?ed|cool(?:ed)?|chromatograph\w*|remov(?:ed|al))\b", evidence, re.I)
            analytical = re.search(r"NMR|TLC|GC/MS|GC.?MS|\byield\b|\bisomer\b|\banalys\w*", evidence, re.I)
            product_result = re.search(r"\b(?:gave|afforded|yielded)\b.*\bproduct\b.*\d+(?:\.\d+)?\s*%", evidence, re.I)
            if (analytical or product_result) and not physical:
                observations.append(action)
            elif re.search(r"\bcapped\b|\bsealed\b", evidence, re.I) and protocol["context"].get("pressure_control") == "SEALED":
                events.append({"kind": "vessel_sealed", "evidence": evidence})
            elif represented_setup(evidence, protocol):
                events.append(represented_setup(evidence, protocol))
            else:
                pending.append(action)
        protocol["extraction"]["analytical_observations"] = observations
        protocol["context"]["source_context_events"] = events
        protocol["extraction"]["unmapped_actions"] = pending
        if pending:
            raise ValueError("source actions not mapped; requires review")
    protocol["crosscheck"] = crosscheck(protocol, raw)
    if protocol["crosscheck"]["conflicts"]:
        raise ValueError("crosscheck: " + ";".join(protocol["crosscheck"]["conflicts"]))
    annotate_dependencies(protocol)
    check = evaluate(protocol)
    if check.risks:
        raise ValueError("symbolic violations: " + ",".join(check.risks))
    for step in protocol["steps"]:
        required = {"Add": ("amount",), "HeatChill": ("temp_C",), "Stir": ("duration_s",),
                    "Wait": ("duration_s",), "Irradiate": ("duration_s",),
                    "Transfer": ("from_vessel", "to_vessel", "amount")}.get(step["op"], ())
        absent = [key for key in required if step.get(key) is None]
        if absent:
            raise ValueError(f"{step['id']}: faithful XDL export needs unknown source parameters: {', '.join(absent)}")
    xml = export_xdl(protocol)
    validate_xdl(xml)
    protocol["xdl"] = xml
    protocol["canonical_sha1"] = canonical_hash(protocol)
    protocol["quality"] = {"tier": "silver", "source_grounded": True, "source_input_contract": "text-only/1",
                           "outcome_annotation_scope": "reference_metadata_only",
                           "xdl_profile": PROFILE, "xdl_profile_schema_passed": True,
                           "official_platform_compiled": False, "symbolic_violations": [],
                           "unknown_constraints": check.unknowns, "manual_review": "pending",
                           "hardware_verification": "pending", "full_feasibility_certified": False}
    if reviews:
        reviews.apply(protocol)
        if protocol["quality"]["manual_review"] == "rejected":
            raise ValueError("manual_protocol_review_rejected")
    return protocol

def split_group(protocol):
    smiles = protocol.get("reaction_smiles") or ""
    try:
        from rdkit import Chem, RDLogger
        from rdkit.Chem.Scaffolds import MurckoScaffold
        RDLogger.DisableLog("rdApp.error")
        product = smiles.split(">")[-1]
        mol = Chem.MolFromSmiles(product)
        if mol:
            scaffold = MurckoScaffold.MurckoScaffoldSmiles(mol=mol)
            if scaffold:
                return "product_scaffold:" + scaffold
            return "acyclic_product:" + Chem.MolToSmiles(mol)
    except ImportError:
        pass
    return "source_procedure:" + str(protocol.get("extraction", {}).get("procedure_sha256") or protocol.get("raw_id") or protocol["id"])
