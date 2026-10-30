"""Batch vocabulary proposals bound to already extracted facts; never re-extract."""
import copy
import re

from .evidence import SourceSpan
from .fact_binding import bind_facts, key
from .facts import validate_facts
from .protocol.io import digest

CURATE = """Maintain a compact, general experimental vocabulary from unknown fact-graph mentions.
Return ONLY {"proposals":[...]} with at most one proposal per unknown expression.
Compare existing semantics first. Synonyms and parameter variants reuse an existing
ID; only genuinely different physical semantics justify a new professional concept.
Do not merge by spelling similarity. No model-specific or condition-specific IDs.
Each proposal has observation_id, target_id, considered (existing IDs), counterexample
(what could be lost by a careless merge), defaults (only qualitative method/mode),
and new_entry (null if reusing a concept).
For operation new_entry: {name:ProfessionalPascalCase,kind:action,domain:general,
description:...,parameters:{parameter:{type:quantity|string|reference,...}},
preconditions:[...],effects:[...],capabilities:[...]}.
For equipment new_entry: {name:ProfessionalPascalCase,category_id:category_id,
legacy_kind:snake_case,capabilities:[qualitative_capability],configuration_parameters:{}}.
If no existing category is semantically suitable, additionally supply new_category:
{id:equipment.stable_category,name:ProfessionalPascalCase,legacy_category:snake_case}.
Operation target_id must start op.; equipment target_id equipment. Existing equipment
means an alias, not a substitution. Do not propose a combination as an alias to Heat:
source concurrent operations must remain distinct and connected by source relations.
Do not supply any ratings, numerical defaults, model identities, reference fixes,
invented facts or executors. Unknown facts remain unknown. This is representation
admission only, not scientific or hardware approval. No need to cover every mention:
leave genuinely ambiguous expressions unresolved and explain under deferred:[...].
Optional substitution_proposals:[{observation_ids:[two observed equipment IDs],
rule:{id:equipment.rule_id,relation:conditional,subtypes:[two existing subtype IDs],
required_demands:[...],any_demands:[...],note:...},
witnesses:[{candidate_id:existing_cited_profile_id,requirement:{...},expected:compatible|incompatible|unknown}]}].
Normally leave this empty. Only propose a relation justified by the observed
equipment tasks, with both a non-unknown witness and a missing-demand/unknown
witness. Shared category or name similarity alone is never substitution.
"""


def admit_expression(snapshot, change):
    """Registry transaction callback: one exact, source-bearing Facts witness."""
    operation_id, expression = change["operation_id"], change["expression"]
    operations = snapshot["canonical_operations"]
    contract = copy.deepcopy(change.get("contract"))
    considered = change.get("considered")
    if not isinstance(considered, list) or not considered or any(i not in operations for i in considered) or not change.get("counterexample"):
        raise ValueError("Operation mapping requires a comparison and semantic counterexample")
    if not re.fullmatch(r"op\.[a-z][a-z0-9_]*", operation_id):
        raise ValueError("Invalid stable operation ID")
    if contract is not None:
        allowed = {"name", "kind", "domain", "description", "parameters", "preconditions", "effects", "capabilities"}
        if set(contract) != allowed or contract["kind"] not in {"action", "condition"}:
            raise ValueError("New operation requires a semantic contract, never an executor or defaults")
        if not re.fullmatch(r"[A-Z][A-Za-z0-9]+", contract["name"]):
            raise ValueError("New operation needs a professional concrete name")
        if operation_id in operations or any(key(entry["name"]) == key(contract["name"]) for entry in operations.values()):
            raise ValueError("Reuse the existing canonical operation")
        if not isinstance(contract["parameters"], dict) or any(not isinstance(contract[k], list) or not contract[k] for k in ("preconditions", "effects")):
            raise ValueError("New operation needs parameters, preconditions and effects")
        for parameter, definition in contract["parameters"].items():
            if not re.fullmatch(r"[a-z][a-z0-9_]*", parameter) or not isinstance(definition, dict) or set(definition) - {"type", "required", "dimension", "description", "unit"}:
                raise ValueError("Parameter declarations cannot contain invented values")
            if definition.get("type") not in {"quantity", "string", "reference", "number", "integer", "boolean", "object", "array"}:
                raise ValueError("Unknown operation parameter type")
        contract.update(semantic_sha256=digest(contract), execution_supported=False, admission_scope="representation_only")
        operations[operation_id] = contract
    if operation_id not in operations:
        raise ValueError("Mapping target does not exist")
    defaults = change.get("defaults", {})
    if not isinstance(defaults, dict) or set(defaults) - {"method", "mode"} or any(not isinstance(v, str) for v in defaults.values()):
        raise ValueError("Only semantic method/mode constants may be supplied by an alias")
    mapping = {"id": "facts.alias." + digest([expression, operation_id, defaults])[:16], "expressions": [expression],
               "operation_id": operation_id, "classification": "synonym" if not defaults else "parameter_variant",
               "defaults": defaults, "parameter_map": {}}
    witness = change["witness"]
    graph = validate_facts(witness["facts"], witness["text"])
    event = next((e for e in graph["events"] if e["event_id"] == witness["event_id"]), None)
    if event is None or event["expression"] != expression:
        raise ValueError("Mapping must exercise the actual frozen source expression")
    if operations[operation_id].get("kind") in {"observation", "provenance"}:
        raise ValueError("An observation cannot replace a source physical action")
    aliases = snapshot["operation_mappings"]["aliases"]
    for alias in aliases:
        if key(expression) in {key(e) for e in alias.get("expressions", [])} and alias.get("operation_id") != operation_id:
            raise ValueError("Expression collides with an existing semantic mapping")
    if mapping not in aliases:
        aliases.append(mapping)
    after = bind_facts(graph, snapshot)["events"].get(event["event_id"])
    if after is None or after["operation_id"] != operation_id:
        raise ValueError("Facts mapping witness remains ambiguous")
    snapshot["canonical_mapping_revision"] = digest(snapshot["operation_mappings"])


def maintain_facts_library(registry, bundles, sources, runner=None):
    """At most two calls per batch; all accepted changes are transactional."""
    observations, actions, rejected = [], [], []
    for source_id, bundle in bundles.items():
        graph = bundle["facts"]
        objects = {e["entity_id"]: e for e in graph["entities"]}
        objects.update({e["event_id"]: e for e in graph["events"]})
        evidence = {e["evidence_id"]: e for e in graph["evidence"]}
        for unknown in bind_facts(graph, registry.snapshot)["unresolved"]:
            obj = objects[unknown["object_id"]]
            citations = [SourceSpan.locate(source_id, sources[source_id], evidence[i]["quote"], start=evidence[i]["start"]).to_dict()
                         for i in obj["evidence_ids"]]
            observations.append({**unknown, "observation_id": "mention_" + digest([source_id, unknown])[:16],
                                 "source_id": source_id, "evidence": citations, "object": obj})
    evolved = registry
    if observations and runner is not None:
        snapshot = registry.snapshot
        payload = {"unknown_mentions": observations, "operations": snapshot["canonical_operations"],
                   "operation_aliases": [{k: a[k] for k in ("expressions", "operation_id", "defaults") if k in a} for a in snapshot["operation_mappings"]["aliases"]],
                   "equipment": snapshot["equipment_catalog"], "equipment_aliases": snapshot["equipment_mappings"]["aliases"],
                   "substitution_rules": snapshot["equipment_mappings"]["substitution_rules"],
                   "cited_device_profiles": snapshot["devices"]}
        by_id = {o["observation_id"]: o for o in observations}
        for attempt in range(2):
            failed = []
            try:
                reply = runner.model_call("library_curator", CURATE, payload)["data"]
                if not isinstance(reply, dict) or not isinstance(reply.get("proposals"), list):
                    raise ValueError("Curator must return a proposal list")
                for proposal in reply["proposals"]:
                    try:
                        observation = by_id[proposal["observation_id"]]
                        if any(a.get("observation_id") == proposal["observation_id"] for a in actions):
                            continue
                        evidence = observation["evidence"]
                        entry, target = proposal.get("new_entry"), proposal["target_id"]
                        known = (evolved.snapshot["canonical_operations"] if observation["kind"] == "operation" else evolved.snapshot["equipment_catalog"]["subtypes"]).get(target)
                        if entry and known and all(known.get(k) == v for k, v in entry.items()):
                            entry = None  # Identical concurrent proposals share one concept.
                        if observation["kind"] == "operation":
                            change = {"action": "admit_fact_expression", "operation_id": target, "contract": entry,
                                "expression": observation["expression"], "considered": proposal.get("considered"),
                                "counterexample": proposal.get("counterexample"), "defaults": proposal.get("defaults", {}),
                                "evidence": evidence, "witness": {"facts": bundles[observation["source_id"]]["facts"],
                                    "event_id": observation["object_id"], "text": sources[observation["source_id"]]}}
                        else:
                            alias = observation["expression"]
                            change = {"action": "admit_equipment_subtype" if entry else "map_equipment_alias",
                                "subtype_id": target, "aliases": [alias], "evidence": evidence,
                                "witnesses": [{"node": {"apparatus_kind": alias, "params": {}}}],
                                "considered_subtypes": proposal.get("considered"), "counterexample": proposal.get("counterexample")}
                            if entry:
                                change["equipment"] = entry
                            if proposal.get("new_category"):
                                change["category"] = proposal["new_category"]
                        candidate = evolved.evolve([change], expected_revision=evolved.revision, sources=sources)
                        # Facts are immutable: only the vocabulary snapshot changes.
                        evolved = candidate
                        actions.append({"observation_id": observation["observation_id"], "action": change["action"],
                                        "expression": observation["expression"], "target_id": target,
                                        "change_sha256": digest(change), "scientific_status": "silver"})
                    except (ValueError, KeyError, TypeError) as error:
                        failed.append({"proposal": proposal, "reason": str(error)[:1500]})
                for proposal in reply.get("substitution_proposals", []):
                    try:
                        origins = [by_id[i] for i in proposal["observation_ids"]]
                        if len({o["object_id"] for o in origins if o["kind"] == "equipment"}) < 2:
                            raise ValueError("A substitution needs two source equipment observations")
                        if any(a.get("rule_id") == proposal["rule"]["id"] for a in actions):
                            continue
                        expectations = {w["expected"] for w in proposal["witnesses"]}
                        if "unknown" not in expectations or not expectations & {"compatible", "incompatible"}:
                            raise ValueError("Substitution requires an informative witness and an unknown boundary witness")
                        change = {"action": "admit_equipment_substitution", "rule": proposal["rule"],
                                  "witnesses": proposal["witnesses"], "evidence": [e for o in origins for e in o["evidence"]]}
                        evolved = evolved.evolve([change], expected_revision=evolved.revision, sources=sources)
                        actions.append({"action": change["action"], "rule_id": proposal["rule"]["id"],
                                        "change_sha256": digest(change), "scientific_status": "silver"})
                    except (ValueError, KeyError, TypeError) as error:
                        failed.append({"substitution_proposal": proposal, "reason": str(error)[:1500]})
                rejected.extend(failed)
                if not failed:
                    break
                payload["repair"] = {"errors": failed, "already_admitted": actions, "remaining_attempts": 1 - attempt}
                payload["operations"] = evolved.snapshot["canonical_operations"]
                payload["equipment"] = evolved.snapshot["equipment_catalog"]
            except (ValueError, RuntimeError, TypeError, KeyError) as error:
                rejected.append({"kind": "curator_failure", "reason": str(error)[:1500]})
                break
    return evolved, {"schema": "mosaic.fact-library-evolution/1", "before_revision": registry.revision,
        "after_revision": evolved.revision, "observations": observations, "actions": actions, "rejected": rejected,
        "policy": "Rebind frozen facts only; admitted semantics remain silver and are not instrument executors.",
        "completion_limit": 2, "facts_reextracted": 0}
