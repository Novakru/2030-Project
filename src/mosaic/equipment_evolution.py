"""Evidence-backed equipment vocabulary admission; never admits physical ratings."""
import copy
import re

from .protocol.equipment_normalization import _key, analysis_equipment, normalize_equipment, conditional_substitutes
from .protocol.io import digest


def _identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"equipment\.[a-z][a-z0-9_]+", value):
        raise ValueError("Equipment needs a stable equipment.* identifier")
    return value


def _aliases(change, snapshot):
    identifier = change["subtype_id"]
    aliases = change.get("aliases")
    if not isinstance(aliases, list) or not aliases or any(not isinstance(a, str) or not a.strip() for a in aliases):
        raise ValueError("Equipment admission needs explicit source aliases")
    evidence = [_key(item["quote"]) for item in change["evidence"]]
    for alias in aliases:
        if _key(alias) in {"vessel", "tube", "container", "plate", "block", "device", "reactor"}:
            raise ValueError("Generic equipment words need context, not a global subtype alias")
        if not any(_key(alias) in quote for quote in evidence):
            raise ValueError("Equipment alias is not present in its cited source")
        for other, entry in snapshot["equipment_catalog"]["subtypes"].items():
            names = [other, entry["name"], *snapshot["equipment_mappings"]["aliases"].get(other, [])]
            if other != identifier and any(_key(alias) == _key(name) for name in names):
                raise ValueError("Equipment alias conflicts with another subtype")
    target = snapshot["equipment_mappings"]["aliases"].setdefault(identifier, [])
    target.extend(alias for alias in aliases if alias not in target)
    witnesses = change.get("witnesses")
    if not isinstance(witnesses, list) or not witnesses:
        raise ValueError("Equipment alias needs source-bearing roundtrip witnesses")
    exercised = set()
    for witness in witnesses:
        node = witness.get("node")
        if not isinstance(node, dict) or set(node) - {"category", "apparatus_kind", "params"} or node.get("params", {}):
            raise ValueError("Identity witnesses cannot invent model facts or numeric ratings")
        if not any(_key(node.get("apparatus_kind")) == _key(a) for a in aliases):
            raise ValueError("Equipment witness does not exercise its proposed alias")
        hardware = {"nodes": {"sample": node}, "edges": [], "bindings": {}}
        normalized = normalize_equipment(hardware, catalog=snapshot["equipment_catalog"], mappings=snapshot["equipment_mappings"])
        actual = normalized["nodes"]["sample"]
        if actual["subtype_id"] != identifier or actual["normalization"]["status"] != "resolved":
            raise ValueError("Equipment alias witness remains ambiguous or unresolved")
        if analysis_equipment(normalized, catalog=snapshot["equipment_catalog"]) != hardware:
            raise ValueError("Equipment alias loses current source information")
        exercised.add(_key(node["apparatus_kind"]))
    if any(_key(alias) not in exercised for alias in aliases):
        raise ValueError("Every admitted equipment alias needs its own witness")


def evolve_equipment(snapshot, change):
    """Apply one checked change inside Registry's transactional private snapshot."""
    catalog = snapshot["equipment_catalog"]
    mappings = snapshot["equipment_mappings"]
    action = change["action"]
    if action == "admit_equipment_subtype":
        identifier = _identifier(change.get("subtype_id"))
        entry = copy.deepcopy(change.get("equipment"))
        if not isinstance(entry, dict) or set(entry) - {"name", "category_id", "legacy_kind", "capabilities", "configuration_parameters"}:
            raise ValueError("Equipment subtype is a semantic contract, not model/rating data")
        if not re.fullmatch(r"[A-Z][A-Za-z]+", entry.get("name", "")):
            raise ValueError("Equipment needs a professional subtype name")
        if not re.fullmatch(r"[a-z][a-z_]+", entry.get("legacy_kind", "")):
            raise ValueError("Equipment needs a stable concrete type name")
        if identifier in catalog["subtypes"] or any(e["name"] == entry["name"] for e in catalog["subtypes"].values()):
            raise ValueError("Reuse an existing equipment subtype")
        considered = change.get("considered_subtypes")
        if not change.get("counterexample") or not isinstance(considered, list) or not considered or any(i not in catalog["subtypes"] for i in considered):
            raise ValueError("New equipment semantics need comparison with known subtypes")
        category = change.get("category")
        if category is not None:
            if not isinstance(category, dict) or set(category) != {"id", "name", "legacy_category"}:
                raise ValueError("New equipment category needs a semantic identity only")
            category_id = _identifier(category["id"])
            if category_id in catalog["categories"] or not re.fullmatch(r"[A-Z][A-Za-z]+", category["name"]):
                raise ValueError("Reuse an existing category; do not rename it")
            catalog["categories"][category_id] = {k: v for k, v in category.items() if k != "id"}
            mappings.setdefault("category_aliases", {})[category_id] = [category["legacy_category"]]
        if entry.get("category_id") not in catalog["categories"]:
            raise ValueError("Equipment subtype points to an unknown category")
        capabilities = entry.get("capabilities")
        if not isinstance(capabilities, list) or not capabilities or any(not isinstance(c, str) or not re.fullmatch(r"[a-z][a-z_.]+", c) for c in capabilities):
            raise ValueError("Equipment needs qualitative capabilities, never inferred numeric ratings")
        fields = entry.get("configuration_parameters", {})
        if not isinstance(fields, dict):
            raise ValueError("Configuration parameter schema must be an object")
        for name, definition in fields.items():
            if not re.fullmatch(r"[a-z][a-z_]*", name) or not isinstance(definition, dict) or set(definition) - {"type", "unit", "dimension", "description", "required"}:
                raise ValueError("Configuration declarations cannot contain default values or ratings")
            if definition.get("type") not in {"string", "number", "integer", "boolean", "quantity", "object", "array"}:
                raise ValueError("Unknown equipment configuration type")
        entry.update(semantic_sha256=digest(entry), admission_scope="representation_only")
        catalog["subtypes"][identifier] = entry
        _aliases(change, snapshot)
    elif action == "map_equipment_alias":
        if change.get("subtype_id") not in catalog["subtypes"]:
            raise ValueError("Equipment alias points to an unknown subtype")
        _aliases(change, snapshot)
    elif action == "admit_equipment_substitution":
        rule = copy.deepcopy(change.get("rule"))
        allowed = {"id", "relation", "subtypes", "required_demands", "any_demands", "note"}
        if not isinstance(rule, dict) or set(rule) - allowed or rule.get("relation") != "conditional":
            raise ValueError("Only explicit conditional substitution rules can be proposed")
        if not isinstance(rule.get("id"), str) or not rule["id"].startswith("equipment."):
            raise ValueError("Substitution rules need a stable ID")
        if len(set(rule.get("subtypes", []))) != 2 or any(i not in catalog["subtypes"] for i in rule["subtypes"]):
            raise ValueError("A conditional rule needs two existing concrete subtypes")
        required = set(rule.get("required_demands", []))
        if not required or not required <= {"capabilities", "capacity_scope", "wetted_materials", "temperature_scope", "mixing_mode", "flow_scope", "pressure_scope", "ports", "geometry"}:
            raise ValueError("Substitution needs implemented explicit functional demands")
        if not set(rule.get("any_demands", [])) <= {"capacity_mL", "working_volume_mL", "temperature_C", "pressure_bar", "rpm", "flow_mL_min"}:
            raise ValueError("Substitution alternatives need implemented quantitative demands")
        category_ids = {catalog["subtypes"][i]["category_id"] for i in rule["subtypes"]}
        if len(category_ids) != 1:
            raise ValueError("Cross-category substitution requires an explicit domain adapter")
        if "equipment.reaction_container" in category_ids:
            if not {"capacity_scope", "wetted_materials"} <= required or not set(rule.get("any_demands", [])) & {"capacity_mL", "working_volume_mL"}:
                raise ValueError("Container alternatives must check material, scope and volume")
            if "equipment.microreactor" in rule["subtypes"] and not {"geometry", "flow_scope", "ports"} <= required:
                raise ValueError("Microreactor substitution must retain geometry, mode and interfaces")
        if any(existing["id"] == rule["id"] for existing in mappings["substitution_rules"]):
            raise ValueError("Existing substitution rules cannot be silently overwritten")
        witnesses = change.get("witnesses")
        if not isinstance(witnesses, list) or not witnesses:
            raise ValueError("A substitution rule needs runtime checker witnesses")
        mappings["substitution_rules"].insert(0, rule)
        profiles = {p["id"]: p for p in snapshot["devices"]} if isinstance(snapshot["devices"], list) else snapshot["devices"]
        for witness in witnesses:
            profile = profiles.get(witness.get("candidate_id"))
            if profile is None or witness.get("expected") not in {"compatible", "incompatible", "unknown"}:
                raise ValueError("Substitution witnesses must reference existing cited profiles")
            result = conditional_substitutes(witness["requirement"], [profile], catalog=catalog, mappings=mappings)[0]
            if result["rule_id"] != rule["id"] or result["status"] != witness["expected"]:
                raise ValueError("Substitution witness disagrees with the independent physical checker")
            if "compatible" == result["status"] and not result["checks"]:
                raise ValueError("An empty demand cannot establish compatibility")
            # A missing demand can never become approval because a rule exists.
            incomplete = {k: v for k, v in witness["requirement"].items() if k not in required}
            boundary = conditional_substitutes(incomplete, [profile], catalog=catalog, mappings=mappings)[0]
            if boundary["status"] == "compatible":
                raise ValueError("Substitution rule bypasses missing functional requirements")
        rule["admission_scope"] = "candidate_selection_only"
    else:
        raise ValueError("Unknown equipment evolution action")
    snapshot["equipment_mapping_revision"] = digest(mappings)
