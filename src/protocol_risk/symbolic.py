"""Pure symbolic checks. Unknown facts produce abstentions, never a safe verdict."""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
import math

from .io import load_library
from .reactivity import groups as reactive_groups, group_evidence


@dataclass
class Result:
    violations: list = field(default_factory=list)
    unknowns: list = field(default_factory=list)

    def add(self, risk, rule, values, source=None):
        self.violations.append({"risk": risk, "rule_id": rule, "values": values, "source_url": source})

    @property
    def risks(self):
        return sorted({v["risk"] for v in self.violations})


def hardware_evidence(node):
    if node.get("verified") is True:
        return "human_verified"
    verification = node.get("verification", {})
    if isinstance(verification, dict) and verification.get("status") == "source_reviewed" and node.get("source_url"):
        return "source_reviewed_provisional"
    if isinstance(verification, dict) and verification.get("status") == "source_reported":
        from .apparatus import source_fact_hash
        citations = node.get("source_evidence", [])
        if (node.get("source_fact_sha256") == source_fact_hash(node) and citations
                and all(c.get("source_url") and c.get("raw_sha256") and c.get("locator") and c.get("value") for c in citations)):
            return "source_reported_provisional"
    return None


def _known(node, parameter):
    level = hardware_evidence(node)
    if level and (level != "source_reported_provisional" or parameter in node.get("source_parameters", [])):
        value = node.get("params", {}).get(parameter)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
            return value
    return None


def _path(edges, start, finish):
    if start == finish:
        return True
    graph = defaultdict(set)
    for left, right in edges:
        graph[left].add(right)
        graph[right].add(left)
    seen, queue = {start}, deque([start])
    while queue:
        node = queue.popleft()
        for other in graph[node] - seen:
            if other == finish:
                return True
            seen.add(other)
            queue.append(other)
    return False


def identify_solvent(reagent, properties):
    for name, prop in properties["solvents"].items():
        aliases = {str(x).lower() for x in prop["aliases"]}
        if any(str(reagent.get(k, "")).lower() in aliases for k in ("name", "smiles", "chemical")):
            return name
    return None


def concentrated_sulfuric(reagent):
    """Keep a sourced qualitative concentration; never invent an exact percentage."""
    if reagent.get("chemical") != "sulfuric_acid_concentrated":
        return False
    fraction = reagent.get("mass_fraction")
    if isinstance(fraction, (int, float)) and not isinstance(fraction, bool):
        return math.isfinite(fraction) and 0.8 <= fraction <= 1
    evidence = reagent.get("concentration_evidence", {})
    return (evidence.get("qualifier") in ("concentrated", "specific_gravity_1.84") and bool(evidence.get("source_url"))
            and bool(evidence.get("source_sha256")))


def evaluate(protocol, properties=None):
    properties = properties or load_library("properties.yaml")
    result = Result()
    reagents = {r["id"]: r for r in protocol.get("reagents", [])}
    hardware = protocol.get("hardware", {})
    nodes, edges = hardware.get("nodes", {}), hardware.get("edges", [])
    result.unknowns.extend({"rule": "hardware_binding", **issue} for issue in hardware.get("source_issues", []))
    context = protocol.get("context", {})
    seen_steps, contents, volumes, inventory_known = set(), defaultdict(set), defaultdict(float), defaultdict(lambda: True)
    chronology, drying_present, drying_removed = defaultdict(list), set(), set()
    for vessel, items in protocol.get("initial_contents", {}).items():
        for item in items:
            reagent_id = item.get("reagent")
            if vessel not in nodes or reagent_id not in reagents:
                result.add("D3", "D3.initial_contents_reference", {"vessel": vessel, "reagent": reagent_id})
                continue
            contents[vessel].add(reagent_id)
            chronology[vessel].append(reagents[reagent_id].get("chemical"))
            amount = item.get("amount")
            if amount and amount.get("unit") == "mL" and isinstance(amount.get("value"), (int, float)) and not isinstance(amount["value"], bool) and math.isfinite(amount["value"]) and amount["value"] > 0:
                volumes[vessel] += amount["value"]
            else:
                inventory_known[vessel] = False
                result.unknowns.append({"rule": "A1", "vessel": vessel, "reason": "initial_quantity_not_specified"})
    inert = set()
    step_ids = {s["id"] for s in protocol["steps"]}
    required_steps = protocol.get("constraints", {}).get("required_steps", [])
    for requirement in required_steps:
        if requirement["id"] not in step_ids:
            result.add("D2", "D2.required_step", requirement, requirement.get("source_url"))
    for index, step in enumerate(protocol["steps"]):
        op, vessel = step["op"], step.get("vessel", "reactor")
        node = nodes.get(vessel, {})
        values = {"step": index, "step_id": step["id"]}
        references = [step[k] for k in ("vessel", "from_vessel", "to_vessel") if step.get(k)]
        missing_references = [ref for ref in references if ref not in nodes]
        if op == "Add" and step.get("reagent") not in reagents:
            missing_references.append(step.get("reagent"))
        if missing_references:
            result.add("D3", "D3.undeclared_reference", {**values, "references": missing_references})
            seen_steps.add(step["id"])
            continue
        amount = step.get("amount")
        invalid_dimension = False
        if amount:
            permitted = {"mL", "mg", "mmol", "eq"} if op == "Add" else {"mL"}
            if amount.get("unit") not in permitted:
                result.add("D4", "D4.quantity_dimension", {**values, "amount": amount, "permitted": sorted(permitted)})
                invalid_dimension = True
            elif not isinstance(amount.get("value"), (float, int)) or amount["value"] <= 0:
                result.add("D4", "D4.nonpositive_quantity", {**values, "amount": amount})
                invalid_dimension = True
        for dependency in step.get("requires", []):
            if dependency in step_ids and dependency not in seen_steps:
                result.add("D1", "D1.order_dependency", {**values, "dependency": dependency})
        if op == "Atmosphere":
            if step.get("gas", "").lower() in ("argon", "nitrogen", "ar", "n2"):
                inert.add(vessel)
        if op == "Add":
            reagent = reagents[step["reagent"]]
            if context.get("inert_required") and vessel not in inert:
                result.add("C5", "C5.source_declared_oxygen_sensitive", values, context["inert_required"].get("source_url"))
            chemical = reagent.get("chemical")
            contents[vessel].add(step["reagent"])
            chronology[vessel].append(chemical)
            if amount and not invalid_dimension and amount["unit"] == "mL":
                volumes[vessel] += amount["value"]
            elif not amount:
                inventory_known[vessel] = False
            materials = node.get("wetted_materials") if hardware_evidence(node) else None
            if materials:
                for pair in properties.get("compatibility", []):
                    if pair["chemical"] == chemical and pair["material"] in materials:
                        result.add("A4", "A4.material_incompatible", {**values, "chemical": chemical, "material": pair["material"]}, pair["source_url"])
            if reagent.get("air_sensitive") and vessel not in inert:
                result.add("C5", "C5.inert_context_missing", {**values, "reagent": step["reagent"]}, reagent.get("sensitivity_source_url"))
            if reagent.get("purpose") == "drying_agent":
                drying_present.add(vessel)
            chemicals = {reagents[x].get("chemical") for x in contents[vessel]}
            for pair in properties.get("incompatible_pairs", []):
                if set(pair["chemicals"]).issubset(chemicals):
                    result.add("B4", "B4.incompatible_contact", {**values, "pair": pair["chemicals"]}, pair["source_url"])
            active_groups = set().union(*(reactive_groups(reagents[r]) for r in contents[vessel]))
            for pair in load_library("reactivity.yaml")["pairs"]:
                if set(pair["groups"]).issubset(active_groups) and (not pair.get("require_liquid_inventory") or volumes[vessel] > 0):
                    evidence = [e for r in sorted(contents[vessel]) for e in group_evidence(reagents[r])]
                    result.add("B4", "B4." + pair["id"], {**values, "pair": pair["groups"], "group_evidence": evidence}, pair["source_url"])
            # Concentration and dilution context are mandatory, not acid/water anywhere.
            if context.get("purpose") == "acid_dilution" and chemical == "water":
                earlier = chronology[vessel][:-1]
                concentrated = any(concentrated_sulfuric(reagents[r]) for r in contents[vessel])
                if "sulfuric_acid_concentrated" in earlier and "water" not in earlier and concentrated:
                    result.add("B5", "B5.water_into_concentrated_acid", values, "https://cameochemicals.noaa.gov/chemical/5193")
        capacity = _known(node, "capacity_mL")
        if capacity is not None:
            if volumes[vessel] > capacity + 1e-9:
                result.add("A1", "A1.capacity", {**values, "volume_mL": volumes[vessel], "capacity_mL": capacity}, node.get("source_url"))
            elif op in ("HeatChill", "Stir") and volumes[vessel] > capacity * 2 / 3 + 1e-9:
                result.add("A1", "A1.fill_fraction", {**values, "volume_mL": volumes[vessel], "capacity_mL": capacity}, node.get("source_url"))
        else:
            result.unknowns.append({"rule": "A1", "step": index, "reason": "unverified_or_missing_capacity"})
        if op == "Transfer":
            left, right = step["from_vessel"], step["to_vessel"]
            if not _path(edges, left, right):
                result.add("A5", "A5.disconnected_path", {**values, "from": left, "to": right})
            if not contents[left]:
                result.add("D1", "D1.transfer_from_empty_vessel", {**values, "from": left})
            if amount and not invalid_dimension:
                moved = amount["value"]
                if inventory_known[left] and moved > volumes[left] + 1e-9:
                    result.add("D1", "D1.insufficient_transfer_inventory", {**values, "available_mL": volumes[left], "requested_mL": moved})
                volumes[left] = max(0, volumes[left] - moved)
                volumes[right] += moved
            contents[right].update(contents[left])
            # Check receiving capacity after transfer, not just before mutation.
            destination_capacity = _known(nodes[right], "capacity_mL")
            if destination_capacity is not None and volumes[right] > destination_capacity + 1e-9:
                result.add("A1", "A1.destination_capacity", {**values, "volume_mL": volumes[right], "capacity_mL": destination_capacity})
            pump_id = hardware.get("bindings", {}).get("pump")
            pump = nodes.get(pump_id, {})
            syringe = _known(pump, "syringe_capacity_mL")
            if syringe is not None and amount and not invalid_dimension and amount["value"] > syringe and not step.get("aliquot"):
                result.add("A1", "A1.syringe_capacity", {**values, "amount": amount, "syringe_capacity_mL": syringe})
        if op in ("HeatChill", "Stir") or "rpm" in step:
            controller_id = hardware.get("bindings", {}).get("heater", "heater")
            controller = nodes.get(controller_id)
            if controller is None:
                result.add("A5", "A5.required_controller_missing", {**values, "controller": controller_id})
            elif "temp_C" in step:
                # Real hotplate limits apply to the plate, not directly to liquid temperature.
                parameter = step.get("controller_setpoint_C", step["temp_C"]) if controller.get("sample_temperature_validated") else step.get("controller_setpoint_C")
                if parameter is None:
                    result.unknowns.append({"rule": "A2", "step": index, "reason": "sample_to_controller_temperature_mapping_unknown"})
                else:
                    low, high = _known(controller, "T_min_C"), _known(controller, "T_max_C")
                    if low is not None and parameter < low or high is not None and parameter > high:
                        result.add("A2", "A2.temperature_range", {**values, "setpoint_C": parameter, "min_C": low, "max_C": high}, controller.get("source_url"))
                    if low is None or high is None:
                        result.unknowns.append({"rule": "A2", "step": index, "reason": "temperature_range_not_fully_verified"})
            if controller and "rpm" in step:
                low, high = _known(controller, "rpm_min"), _known(controller, "rpm_max")
                if low is not None and step["rpm"] < low or high is not None and step["rpm"] > high:
                    result.add("A3", "A3.stirring_range", {**values, "rpm": step["rpm"], "min": low, "max": high}, controller.get("source_url"))
                if low is None or high is None:
                    result.unknowns.append({"rule": "A3", "step": index, "reason": "speed_range_unverified"})
        if op == "HeatChill":
            temperature = step.get("temp_C")
            solvents = {identify_solvent(reagents[r], properties) for r in contents[vessel]
                        if reagents[r].get("role") == "SOLVENT"}
            solvents.discard(None)
            # Only exact single-solvent data supports this v0 check.
            if len(solvents) == 1 and temperature is not None:
                solvent = next(iter(solvents))
                prop = properties["solvents"][solvent]
                mode = context.get("pressure_control", "UNKNOWN")
                if mode in ("AMBIENT", "OPEN") and not context.get("reflux") and prop.get("bp_C") is not None and temperature > prop["bp_C"]:
                    result.add("B1", "B1.open_above_bp", {**values, "temp_C": temperature, "bp_C": prop["bp_C"], "solvent": solvent}, prop["source_url"])
                if context.get("pure_solvent") and prop.get("mp_C") is not None and temperature < prop["mp_C"]:
                    result.add("B2", "B2.pure_solvent_below_mp", {**values, "temp_C": temperature, "mp_C": prop["mp_C"], "solvent": solvent}, prop["source_url"])
                if (context.get("ignition_source") and context.get("vapor_exposed") and prop.get("flash_C") is not None and temperature > prop["flash_C"]):
                    result.add("B3", "B3.ignition_exposure", {**values, "temp_C": temperature, "flash_C": prop["flash_C"], "solvent": solvent}, prop["source_url"])
                if context.get("oxygen_present") and prop.get("ait_C") is not None and temperature >= prop["ait_C"]:
                    result.add("B3", "B3.autoignition_boundary", {**values, "temp_C": temperature, "ait_C": prop["ait_C"], "solvent": solvent}, prop["source_url"])
            else:
                result.unknowns.append({"rule": "B1/B2/B3", "step": index, "reason": "unknown_or_mixed_solvent_properties"})
            if not context.get("pure_solvent"):
                result.unknowns.append({"rule": "B2", "step": index, "reason": "solution_freezing_point_not_established"})
        if op in ("Filter", "Separate"):
            needed = "filter" if op == "Filter" else "separator"
            if needed not in nodes:
                result.add("A5", "A5.required_component_missing", {**values, "component": needed})
        if op == "Filter" and step.get("keep") == "filtrate":
            drying_removed.add(vessel)
        if op == "Evaporate":
            if vessel in drying_present and vessel not in drying_removed and protocol.get("constraints", {}).get("drying_rule_source"):
                result.add("D2", "D2.drying_agent_not_removed", values, protocol.get("constraints", {}).get("drying_rule_source"))
            contents[vessel] = {r for r in contents[vessel] if reagents[r].get("role") != "SOLVENT"}
            volumes[vessel] = 0
        seen_steps.add(step["id"])
    return result
