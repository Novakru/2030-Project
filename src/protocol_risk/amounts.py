"""Independently read a quantity next to a literal reagent alias in source text."""
from __future__ import annotations

import math
import re
from functools import lru_cache

NUMBER = r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?"
UNIT = r"(?:nmol|umol|mmol|mol|ug|mg|kg|g|nL|uL|mL|L)"
MEASUREMENT = re.compile(rf"(?<![\w.])({NUMBER})\s*({UNIT})\b", re.I)
SCALE = {"nmol": ("mmol", 1e-6), "umol": ("mmol", 0.001), "mmol": ("mmol", 1), "mol": ("mmol", 1000),
         "ug": ("mg", 0.001), "mg": ("mg", 1), "g": ("mg", 1000), "kg": ("mg", 1e6),
         "nl": ("mL", 1e-6), "ul": ("mL", 0.001), "ml": ("mL", 1), "l": ("mL", 1000)}
GENERIC = re.compile(r"^(?:the\s+)?(?:catalysts?|solvents?|ligands?|reagents?|substrates?|starting materials?|(?:solid |liquid )?bases?|acids?|reaction components)$", re.I)


def _normalize(text):
    return text.replace("µ", "u").replace("μ", "u").replace("−", "-")


def _after_alias(text):
    text = text.lstrip()
    if text.startswith("("):
        depth = 0
        for i, character in enumerate(text):
            depth += (character == "(") - (character == ")")
            if depth == 0:
                return text[1:i]
        return ""
    # Only an adjacent quantity is accepted. Do not borrow the next reagent's dose.
    match = re.match(rf"^({NUMBER}\s*{UNIT})(?!\w)", text, re.I)
    return match[0] if match else ""


def local_measurements(evidence, alias):
    if not alias or GENERIC.fullmatch(alias.strip()):
        return [], "missing_or_generic_alias"
    positions = list(re.finditer(re.escape(alias), evidence))
    if len(positions) != 1:
        return [], "alias_absent_or_ambiguous"
    position = positions[0]
    after = _after_alias(_normalize(evidence[position.end():]))
    before = _normalize(evidence[:position.start()])
    leading = re.search(rf"({NUMBER}\s*{UNIT})(?:\s+of)?\s*$", before, re.I)
    segment = after or (leading[1] if leading else "")
    if not segment:
        return [], "no_adjacent_quantity"
    if re.search(rf"{NUMBER}\s*(?:-|–|to)\s*{NUMBER}\s*{UNIT}", segment, re.I):
        return [], "quantity_range_not_a_setpoint"
    values = []
    for match in MEASUREMENT.finditer(segment):
        tail = segment[match.end():]
        if re.match(r"\s*(?:%|percent\b|/|per\b|mL\s*[-−]1)", tail, re.I):
            continue  # Loading percentages and concentrations are not absolute amounts.
        unit, factor = SCALE[match[2].lower()]
        mantissa, _, exponent = match[1].lower().partition("e")
        decimals = len(mantissa.split(".")[1]) if "." in mantissa else 0
        rounding_half = 0.5 * 10 ** (int(exponent or 0) - decimals) * factor
        values.append({"value": float(match[1]) * factor, "unit": unit, "quote": match[0],
                       "printed_rounding_half_unit": rounding_half, "source_segment": segment})
    return values, "adjacent_literal_quantity" if values else "no_absolute_quantity"


@lru_cache(maxsize=4096)
def molecular_weight(smiles):
    if not smiles:
        return None
    from rdkit import Chem
    from rdkit.Chem import Descriptors
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None
    return Descriptors.MolWt(mol)


def verify_amount(reagent, expected, evidence, alias, tolerance=0.1):
    measurements, reason = local_measurements(evidence, alias)
    result = {"reagent": reagent["id"], "alias": alias, "expected": expected,
              "measurements": measurements, "status": "unknown", "basis": reason}
    if not expected or not measurements:
        return result
    comparable = []
    for amount in measurements:
        value, basis = amount["value"], "direct_source_quantity"
        rounding_half = amount["printed_rounding_half_unit"]
        if amount["unit"] != expected["unit"]:
            if {amount["unit"], expected["unit"]} != {"mg", "mmol"}:
                continue
            if re.search(r"dispersion|solution|\d\s*%\s*(?:w/w|w/v|in\b)|hydrate", amount["source_segment"] + " " + (alias or ""), re.I):
                continue  # No purity, solvation, or active-fraction assumptions.
            weight = molecular_weight(reagent.get("smiles"))
            if not weight:
                continue
            value = value / weight if amount["unit"] == "mg" else value * weight
            rounding_half = rounding_half / weight if amount["unit"] == "mg" else rounding_half * weight
            basis = "source_quantity_with_structure_derived_molecular_weight"
        strong = math.isclose(value, expected["value"], rel_tol=tolerance, abs_tol=1e-8)
        compatible = abs(value - expected["value"]) <= abs(expected["value"]) * tolerance + rounding_half + 1e-8
        comparable.append({"value": value, "unit": expected["unit"], "basis": basis,
                           "within_tolerance": strong, "compatible_with_printed_rounding": compatible,
                           "printed_rounding_half_unit": rounding_half})
    result["comparable_quantities"] = comparable
    if comparable:
        if not all(x["compatible_with_printed_rounding"] for x in comparable):
            result["status"] = "conflict"
        elif any(x["within_tolerance"] for x in comparable):
            result["status"] = "matched"
        else:
            result["basis"] = "printed_precision_insufficient_for_independent_confirmation"
    return result


def scan_amounts():
    from collections import Counter
    from .crosscheck import crosscheck
    from .ingest import read_raw
    from .io import ROOT, read_json, write_json
    extracts = {p.stem: read_json(p) for p in (ROOT / "data/intermediate/extractions").glob("*.json")}
    counts, conflicts = Counter(), []
    for raw in read_raw(ids=set(extracts)):
        result = crosscheck(extracts[raw["id"]], raw)
        counts["all_amounts_independently_matched"] += result["checks"]["amount_comparison_is_independent"]
        for check in result["quantity_checks"]:
            counts[check["status"]] += 1
            if check["status"] == "conflict":
                conflicts.append({"raw_id": raw["id"], **check})
    write_json(ROOT / "reports/independent_amount_scan.json", {"counts": dict(counts), "conflicts": conflicts,
               "claim": "Numeric checks use literal source quantities; molecular-weight comparisons assume the supplied structure. Chemical identity alignment still requires review."})
    return dict(counts)
