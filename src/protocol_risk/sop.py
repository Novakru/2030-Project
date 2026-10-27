"""Small, source-pinned SOP fragments and explicitly instantiated safety scenarios."""
from __future__ import annotations

import copy
import re


from .io import ROOT, digest, load_library, read_json


def source_text(identifier):
    source = next(row for row in read_json(ROOT / "data/sop_sources.lock.json")["sources"] if row["id"] == identifier)
    for path_key, hash_key in (("path", "sha256"), ("text_path", "text_sha256")):
        if digest((ROOT / source[path_key]).read_bytes()) != source[hash_key]:
            raise ValueError("SOP source checksum mismatch: " + identifier)
    return source, (ROOT / source["text_path"]).read_bytes().decode("utf-8")


def volume_pattern(value):
    number = format(value, "g")
    return r"(?<![\d.])" + re.escape(number) + (r"(?:\.0+)?" if "." not in number else "") + r"\s*m[lL]\b"


def recipe_evidence(recipe, source, text):
    start, end = recipe["lines"]
    # pdftotext form feeds are page markers, not additional LF line numbers.
    snippet = "\n".join(text.split("\n")[start - 1:end])
    if not all(re.search(volume_pattern(recipe[key]), snippet) for key in ("acid_mL", "water_mL")):
        raise ValueError("Source volumes not located: " + recipe["id"])
    qualifier = recipe["concentration"]
    if qualifier == "concentrated":
        supported = re.search(r"concentrated|conc\.", snippet, re.I)
    else:
        supported = re.search(r"sp\.\s*gr\.\s*1\.84", snippet, re.I)
    if not supported or not re.search(r"sulfuric|H2SO4", snippet, re.I):
        raise ValueError("Acid concentration not located: " + recipe["id"])
    return {"source_id": source["id"], "source_url": source["url"], "source_sha256": source["sha256"],
            "text_path": source["text_path"], "text_sha256": source["text_sha256"], "lines": [start, end],
            "snippet_sha256": digest(snippet.encode("utf-8")), "section": recipe["section"]}


def base(identifier, source, origin):
    return {"id": "sop_" + identifier, "source": {"db": "PUBLISHED_SOP", "url": source["url"],
            "id": source["id"], "sha256": source["sha256"]}, "origin": origin,
            "reaction_class": "laboratory_reagent_handling", "reaction_smiles": None, "yield_percent": None,
            "quality": {"tier": "silver", "full_feasibility_certified": False, "human_review": "deferred"},
            "hardware": {"config_id": "unspecified_sop_vessel", "nodes": {
                "reactor": {"category": "vessel", "params": {}, "verified": False},
                "heater": {"category": "heater_stirrer", "params": {}, "verified": False}},
                "edges": [["reactor", "heater"]], "bindings": {"heater": "heater"}},
            "context": {}, "steps": [], "reagents": [], "unresolved_instructions": [],
            "split_group": "sop_source_" + source["id"], "split": "train",
            "representation_scope": "SOP fragment or stated scenario only; consult JSON sidecar and original instructions; no hardware execution certificate."}


def acid_parent(recipe):
    source, text = source_text(recipe["source"])
    evidence = recipe_evidence(recipe, source, text)
    parent = base(recipe["id"], source, "published_sop_fragment")
    acid = {"id": "acid", "name": "concentrated sulfuric acid", "chemical": "sulfuric_acid_concentrated",
            "role": "REAGENT", "concentration_evidence": dict(evidence, qualifier=recipe["concentration"])}
    if "acid_mass_fraction" in recipe:
        acid["mass_fraction"] = recipe["acid_mass_fraction"]
    parent["reagents"] = [{"id": "water", "name": "water", "chemical": "water", "role": "SOLVENT", "smiles": "O"}, acid]
    parent["steps"] = [
        {"id": "charge_water", "op": "Add", "vessel": "reactor", "reagent": "water",
         "amount": {"value": recipe["water_mL"], "unit": "mL", "approximate": recipe.get("water_approximate", False)}},
        {"id": "add_acid", "op": "Add", "vessel": "reactor", "reagent": "acid",
         "amount": {"value": recipe["acid_mL"], "unit": "mL"}}]
    parent["context"] = {"purpose": "acid_dilution", "source_evidence": evidence}
    parent["unresolved_instructions"] = recipe["unresolved"]
    parent["source_evidence"] = evidence
    parent["construction"] = {"kind": "literal_source_fragment", "whole_method_reconstructed": False,
                              "claim": "Original two-input order and quantities only; other safety conditions remain unresolved."}
    return parent


def thermal_parent(identifier, source, solvent, specification):
    parent = base(identifier, source, "instantiated_sop")
    prop = load_library("properties.yaml")["solvents"][solvent]
    parent["reagents"] = [{"id": "solvent", "name": solvent, "chemical": solvent, "smiles": prop["smiles"], "role": "SOLVENT"}]
    parent["initial_contents"] = {"reactor": [{"reagent": "solvent", "amount": None}]}
    parent["steps"] = [{"id": "condition", "op": "HeatChill", "vessel": "reactor", "temp_C": specification["parent_temp_C"]}]
    parent["context"] = {"pure_solvent": True, "pressure_control": "OPEN", "reflux": False}
    parent["construction"] = {"kind": "explicit_sop_instantiation", "observed_experiment": False,
                              "assumptions": specification["assumptions"], "parameter_origin": "constructed_within_sourced_constraints",
                              "source_text_sha256": source["text_sha256"]}
    parent["unresolved_instructions"] = ["Preloaded volume and duration are unspecified; no numerical values are invented."]
    return parent


def candidates():
    specification = load_library("sop_recipes.yaml")
    for recipe in specification["acid_dilutions"]:
        parent = acid_parent(recipe)
        child = copy.deepcopy(parent)
        child["steps"][0], child["steps"][1] = child["steps"][1], child["steps"][0]
        yield parent, "B5", child
    dmso = specification["instantiation"]["dmso"]
    source, text = source_text(dmso["source"])
    if not all(phrase in text.lower() for phrase in ("gentle", "freezing point", "40", "venting")):
        raise ValueError("DMSO thawing instructions not found")
    parent = thermal_parent("dmso_thaw", source, "dimethylsulfoxide", dmso)
    parent["context"].update(purpose="thaw_to_bulk_liquid_at_equilibrium", oxygen_present=True)
    for temperature in dmso["bad_temperatures_C"]:
        child = copy.deepcopy(parent)
        child["steps"][0]["temp_C"] = temperature
        yield parent, "B2", child
    flammables = specification["instantiation"]["flammables"]
    source, text = source_text(flammables["source"])
    if not all(phrase in text.lower() for phrase in ("bunsen", "hot air guns", "open containers of flammable liquid")):
        raise ValueError("Open-vessel ignition precautions not found")
    for solvent in flammables["solvents"]:
        parent = thermal_parent("open_" + solvent, source, solvent, flammables)
        parent["context"].update(vapor_exposed=True, oxygen_present=True, ignition_source=False)
        for ignition in flammables["ignition_sources"]:
            child = copy.deepcopy(parent)
            child["context"]["ignition_source"] = ignition
            yield parent, "B3", child
