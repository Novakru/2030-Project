"""Source apparatus facts, kept separate from proposed automation equipment."""
from __future__ import annotations

import copy
import math
import re

from .io import digest

_UNITS = {"MILLILITER": 1, "MICROLITER": .001, "LITER": 1000,
          "ml": 1, "ul": .001, "\u00b5l": .001, "\u03bcl": .001, "l": 1000}
_KINDS = {"VIAL": "vial", "ROUND_BOTTOM_FLASK": "round_bottom_flask",
          "WELL_PLATE": "well_plate", "MICROREACTOR": "microreactor"}
_VESSEL = r"micro[- ]?reactor|round[- ]bottom(?:ed)?\s+flask|vial|flask"
_CAPACITY = re.compile(
    r"(?<![\w.])(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>mL|[u\u00b5\u03bc]L|L)\s*"
    r"(?:(?:Wheaton|weaton|glass|borosilicate|screw[- ]cap(?:ped)?|pressure|reaction|sealed)\s+){0,4}"
    r"(?P<kind>" + _VESSEL + r")\b", re.I)


def _positive(value):
    return isinstance(value, (float, int)) and not isinstance(value, bool) and math.isfinite(value) and value > 0


def source_fact_hash(node):
    """Bind provisional source claims to their values and citation; edits expire evidence."""
    return digest({k: node.get(k) for k in ("apparatus_kind", "params", "capacity_scope",
                   "wetted_materials", "source_parameters", "source_evidence")})


def _citation(protocol, raw, locator, value):
    return {"source_url": (raw or protocol).get("source", {}).get("url"),
            "raw_sha256": (raw or protocol).get("raw_sha256"),
            "locator": locator, "value": copy.deepcopy(value)}


def _node(protocol, raw, kind, params, scope, material, locator, value, description):
    node = {"category": "vessel", "apparatus_kind": kind, "description": description,
            "params": params, "capacity_scope": scope, "wetted_materials": material,
            "ports": [], "model": None, "verified": False, "binding_basis": "source_reported",
            "source_url": (raw or protocol).get("source", {}).get("url"),
            "source_parameters": [k for k, v in params.items() if _positive(v)],
            "source_evidence": [_citation(protocol, raw, locator, value)],
            "verification": {"status": "source_reported", "human_verified": False},
            "note": "Procedure-reported facts; no manufacturer rating, flow capability or port topology inferred."}
    node["source_fact_sha256"] = source_fact_hash(node)
    node["id"] = "source_apparatus_" + node["source_fact_sha256"][:16]
    return node


def _text_facts(protocol, raw):
    # Prefer reaction-stage quotations: later workup flasks must not replace the reactor.
    snippets = [("/steps/" + str(i) + "/meta/evidence", s.get("meta", {}).get("evidence", ""))
                for i, s in enumerate(protocol.get("steps", []))
                if s.get("meta", {}).get("stage") == "reaction"]
    if not any(text for _, text in snippets) and raw:
        snippets = [("/procedure", raw.get("procedure") or "")]
    found = {}
    for locator, text in snippets:
        for match in _CAPACITY.finditer(text):
            capacity = float(match["value"]) * _UNITS[match["unit"].lower()]
            label = match["kind"].lower()
            kind = "microreactor" if "reactor" in label else "round_bottom_flask" if "round" in label else label
            key = (kind, capacity)
            # A short exact quote, plus its containing quotation for inspection.
            found.setdefault(key, _node(protocol, raw, kind, {"capacity_mL": capacity},
                "single_reaction_vessel", None, locator, text, match.group(0)))
    if not found and raw and raw.get("procedure"):
        text = raw["procedure"]
        workup_offsets = [text.find(s.get("meta", {}).get("evidence", "")) for s in protocol.get("steps", [])
                          if s.get("meta", {}).get("stage") != "reaction" and s.get("meta", {}).get("evidence")]
        end = min((offset for offset in workup_offsets if offset >= 0), default=len(text))
        prefix = text[:end]
        # Short reagent quotes may omit the vessel in the same source sentence.
        # Inspect the reaction prefix only, so later workup flasks cannot replace it.
        for match in _CAPACITY.finditer(prefix):
            capacity = float(match["value"]) * _UNITS[match["unit"].lower()]
            label = match["kind"].lower()
            kind = "microreactor" if "reactor" in label else "round_bottom_flask" if "round" in label else label
            found.setdefault((kind, capacity), _node(protocol, raw, kind, {"capacity_mL": capacity},
                "single_reaction_vessel", None, "/procedure", prefix, match.group(0)))
    return list(found.values()), snippets


def source_apparatus(protocol, raw=None):
    """Return one unambiguous vessel or unresolved conflicts, never size by liquid volume."""
    # Text extraction cannot acquire apparatus facts from ORD setup, even when a
    # caller accidentally passes its full raw record at this downstream seam.
    text_only = protocol.get("extraction", {}).get("input_contract") == "text-only/1"
    setup = {} if text_only else ((raw or {}).get("setup", protocol.get("context", {}).get("source_setup", {})) or {})
    vessel = setup.get("vessel", {}) or {}
    candidates, snippets = _text_facts(protocol, raw)
    structured = None
    if vessel:
        kind = _KINDS.get(vessel.get("type"), str(vessel.get("type", "unknown")).lower())
        volume = vessel.get("volume", {}) or {}
        reported = volume["value"] * _UNITS[volume["units"]] if _positive(volume.get("value")) and volume.get("units") in _UNITS else None
        scope = "single_reaction_vessel"
        params = {"capacity_mL": reported}
        details = vessel.get("details", "")
        if kind == "well_plate":
            # ORD's volume alone does not say whole plate, well, insert or working volume.
            # Only an explicit '12.5 uL-wells' style description establishes this scope.
            per_well = re.search(r"(\d+(?:\.\d+)?)\s*([u\u00b5\u03bc]L|mL)\s*[- ]?wells?\b", details, re.I)
            params = {"capacity_mL": None, "reported_volume_mL": reported}
            scope = "reported_vessel_volume_scope_unresolved"
            if per_well and reported is not None:
                stated = float(per_well[1]) * _UNITS[per_well[2].lower()]
                if abs(stated - reported) < 1e-9:
                    params.update(capacity_mL=reported, well_capacity_mL=reported)
                    scope = "per_well"
        material_info = vessel.get("material", {}) or {}
        material = {"GLASS": ["glass_unspecified"], "PLASTIC": ["plastic_unspecified"], "PTFE": ["PTFE"]}.get(material_info.get("type"))
        if re.search(r"\bCOC\b|cyclic\s*olefin\s*copolymer", material_info.get("details", ""), re.I):
            material = ["cyclic_olefin_copolymer"]
        structured = _node(protocol, raw, kind, params, scope, material, "/setup/vessel", vessel,
                           details or vessel.get("type", "source vessel"))
        structured["source_setup_vessel"] = copy.deepcopy(vessel)
    issues = []
    if structured:
        for candidate in candidates:
            # Vials inside plates and generic 'flask' vs round-bottom are compatible descriptions.
            compatible = (candidate["apparatus_kind"] == structured["apparatus_kind"]
                or (structured["apparatus_kind"] == "well_plate" and candidate["apparatus_kind"] == "vial")
                or {candidate["apparatus_kind"], structured["apparatus_kind"]} == {"flask", "round_bottom_flask"})
            a, b = candidate["params"].get("capacity_mL"), structured["params"].get("capacity_mL")
            if not compatible or (a is not None and b is not None and abs(a - b) > 1e-9):
                issues.append({"reason": "source_apparatus_conflict", "structured": structured, "text": candidate})
        selected = structured
    elif len(candidates) == 1:
        selected = candidates[0]
    elif len(candidates) > 1:
        selected = None
        issues.append({"reason": "multiple_unmapped_source_vessels", "candidates": candidates})
    else:
        selected = None
        if any(re.search(r"micro[- ]?reactor", text, re.I) for _, text in snippets):
            locator, text = next((loc, txt) for loc, txt in snippets if re.search(r"micro[- ]?reactor", txt, re.I))
            selected = _node(protocol, raw, "microreactor", {"capacity_mL": None}, "unknown", None, locator, text, "microreactor; model unspecified")
    # A conflict keeps both source statements, but neither becomes a checker limit.
    if issues and selected:
        selected["source_parameters"] = []
        selected["source_fact_sha256"] = source_fact_hash(selected)
    return selected, issues


def source_heating_block(protocol, raw=None):
    for i, step in enumerate(protocol.get("steps", [])):
        text = step.get("meta", {}).get("evidence", "")
        if step["op"] == "HeatChill" and re.search(r"(?:alumin(?:um|ium)|heating|heated)\s+block", text, re.I):
            node = _node(protocol, raw, "heating_block", {}, "not_a_reaction_volume", [],
                         "/steps/" + str(i) + "/meta/evidence", text, "Source-reported heating block; controller model and limits unknown")
            node["category"] = "heater"
            node["stirring_capability"] = "unknown"
            return node
    return None
