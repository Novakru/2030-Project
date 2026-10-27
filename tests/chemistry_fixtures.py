"""Authored rule fixtures, explicitly separate from observed experimental data."""
from __future__ import annotations

import copy

from protocol_risk.io import load_library
from protocol_risk.mutation_rules import SOFT, make_negative


def reference(risk, number):
    # Values are definitions of simulated fixtures, not manufacturer specifications.
    variant = number + 1
    nodes = {
        "reactor": {"category": "vessel", "params": {"capacity_mL": 100 + variant},
                    "wetted_materials": ["PTFE"], "verified": True, "verification": "authored_simulated_fixture"},
        "product": {"category": "vessel", "params": {"capacity_mL": 100 + variant}, "verified": True},
        "heater": {"category": "heater_stirrer", "params": {"T_min_C": -100, "T_max_C": 200, "rpm_min": 50, "rpm_max": 1500},
                   "sample_temperature_validated": True, "verified": True, "verification": "authored_simulated_fixture"},
        "filter": {"category": "filter", "params": {}, "verified": True},
    }
    solvent = {"id": "r1", "name": "water", "chemical": "water", "smiles": "O", "role": "SOLVENT"}
    reagents = [solvent, {"id": "r2", "name": "reference substrate", "role": "REACTANT", "smiles": None},
                {"id": "r3", "name": "reference catalyst", "role": "CATALYST", "smiles": None}]
    steps = [{"id": "s1", "op": "Add", "vessel": "reactor", "reagent": "r1", "amount": {"value": 10 + variant, "unit": "mL"}},
             {"id": "s2", "op": "Add", "vessel": "reactor", "reagent": "r2", "amount": {"value": 0.1 + variant * 0.01, "unit": "mmol"}},
             {"id": "s3", "op": "Add", "vessel": "reactor", "reagent": "r3", "amount": {"value": 0.01, "unit": "mmol"}},
             {"id": "s4", "op": "HeatChill", "vessel": "reactor", "temp_C": 25 + variant * 0.1, "duration_s": 600 + variant, "rpm": 300 + variant}]
    context = {"pressure_control": "OPEN", "reflux": False, "purpose": "rule_fixture"}
    constraints = {}
    if risk in ("B2",):
        reagents, steps = reagents[:1], [steps[0], steps[-1]]
        context["pure_solvent"] = True
    if risk in ("B3", "C1"):
        solvent.update(name="ethanol", chemical="ethanol", smiles="CCO")
        context.update(vapor_exposed=True, ignition_source=False)
    if risk == "A4":
        reagents[1].update(name="hydrofluoric acid", chemical="hydrofluoric_acid")
    if risk == "B4":
        reagents[1].update(name="hydrochloric acid", chemical="acid")
        reagents[2].update(name="sodium chloride", chemical="chloride", role="REAGENT")
    if risk == "B5":
        reagents = [solvent, {"id": "r2", "name": "concentrated sulfuric acid", "chemical": "sulfuric_acid_concentrated", "role": "REAGENT", "mass_fraction": 0.98}]
        steps = [steps[0], {"id": "s2", "op": "Add", "vessel": "reactor", "reagent": "r2", "amount": {"value": 1 + variant * 0.1, "unit": "mL"}}]
        context["purpose"] = "acid_dilution"
    if risk == "C5":
        reagents[1].update(name="declared air-sensitive reference material", air_sensitive=True,
                           sensitivity_source_url=None, sensitivity_basis="authored_fixture_predicate_not_an_SDS_claim")
        steps.insert(0, {"id": "gas", "op": "Atmosphere", "vessel": "reactor", "gas": "nitrogen", "mode": "environment"})
    if risk == "D1":
        steps = [steps[0], {"id": "move", "op": "Transfer", "from_vessel": "reactor", "to_vessel": "product", "amount": {"value": 5, "unit": "mL"}, "requires": ["s1"]}]
    if risk == "D2":
        solvent.update(name="tetrahydrofuran", chemical="tetrahydrofuran", smiles="C1CCOC1")
        reagents[1].update(name="magnesium sulfate", role="WORKUP", purpose="drying_agent")
        steps = [steps[0], {"id": "dry", "op": "Add", "vessel": "reactor", "reagent": "r2", "amount": {"value": 10 + variant, "unit": "mg"}},
                 {"id": "filter", "op": "Filter", "vessel": "reactor", "keep": "filtrate", "to_vessel": "reactor"},
                 {"id": "evap", "op": "Evaporate", "vessel": "reactor"}]
        constraints["required_steps"] = [{"id": "filter", "basis": "explicit_authored_workflow_contract", "source_url": None}]
    return {"id": f"control_{risk}_{variant:02}", "source": {"db": "AUTHORED_CONTROL", "url": None,
            "license": "CC0-1.0", "note": "Synthetic unit scenario. Not an observed reaction, ORD gold sample or experimental failure."},
            "reaction_class": "authored_rule_fixture", "reaction_smiles": None, "yield_percent": None,
            "reagents": reagents, "steps": steps, "context": context, "constraints": constraints,
            "hardware": {"config_id": "simulated_rule_fixture", "nodes": nodes,
                         "edges": [["reactor", "product"], ["reactor", "filter"]], "bindings": {"heater": "heater"}},
            "label": {"feasible": None, "feasible_under_declared_rules": True, "experimental_outcome": "not_observed"}}


def mutate(parent, risk, number):
    child = copy.deepcopy(parent)
    steps, nodes = child["steps"], child["hardware"]["nodes"]
    if risk == "A1":
        nodes["reactor"]["params"]["capacity_mL"] = 5 + number * 0.01
    elif risk == "A2":
        # Low temperature is outside controller range but has no B2 proof for a solution.
        steps[-1]["temp_C"] = -101 - number
    elif risk == "A3":
        steps[-1]["rpm"] = 1501 + number
    elif risk == "A4":
        nodes["reactor"]["wetted_materials"] = ["borosilicate_glass"]
    elif risk == "A5":
        del nodes["heater"]
    elif risk == "B1":
        steps[-1]["temp_C"] = 110 + number
    elif risk == "B2":
        steps[-1]["temp_C"] = -1 - number
    elif risk == "B3":
        child["context"]["ignition_source"] = True
    elif risk == "B4":
        child["reagents"][2].update(name="sodium cyanide", chemical="cyanide")
    elif risk == "B5":
        steps[0], steps[1] = steps[1], steps[0]
    elif risk == "C1":
        child["reagents"][0].update(name="toluene", chemical="toluene", smiles="Cc1ccccc1")
    elif risk == "C2":
        steps[-1]["temp_C"] = 5 - number * 0.1
    elif risk == "C3":
        del steps[2]
    elif risk == "C4":
        steps[1]["amount"]["value"] *= 10
    elif risk == "C5":
        del steps[0]
    elif risk == "C6":
        steps[-1]["duration_s"] = 0.1 + number * 0.001
    elif risk == "D1":
        steps[0], steps[1] = steps[1], steps[0]
    elif risk == "D2":
        del steps[2]
    elif risk == "D3":
        steps[0]["reagent"] = "undeclared"
    elif risk == "D4":
        steps[0]["amount"]["unit"] = "s"
    else:
        raise ValueError(risk)
    return child


def generate_controls(per_risk=12):
    parents, negatives = [], []
    for risk in load_library("risks.yaml")["risks"]:
        for number in range(per_risk):
            parent = reference(risk, number)
            child = mutate(parent, risk, number)
            evidence = {"basis": "authored_control_definition", "not_experimental": True,
                        "calibration": "none", "conditions": "specified by the reference fixture"}
            negative = make_negative(parent, child, risk, evidence, origin="authored_control")
            if negative is None:
                from protocol_risk.symbolic import evaluate
                raise AssertionError(f"Invalid fixture {risk}/{number}: parent={evaluate(parent).risks}, child={evaluate(child).risks}")
            parents.append(parent)
            negatives.append(negative)
    return parents, negatives
