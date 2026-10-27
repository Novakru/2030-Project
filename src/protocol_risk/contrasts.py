"""Conservative single-factor contrasts between independently recorded HTE runs."""
from __future__ import annotations

import copy
from collections import Counter, defaultdict

from .conditions import chemical_key
from .ingest import identifier, iter_ord, quantity, read_raw
from .io import ROOT, canonical, digest, load_library, read_json, read_jsonl, write_json, write_jsonl
from .validation import split_group


def contrast_views(record):
    """Mask one recorded factor; preserve all other experimental/assay metadata."""
    evidence = record.get("yield_evidence", {})
    if record.get("yield_percent") is None or evidence.get("status") != "selected":
        return
    raw = record["raw"]
    _, _, outcome_index, _, product_index = evidence["target_source_path"].split("/")
    outcome = raw["outcomes"][int(outcome_index)]
    product = outcome["products"][int(product_index)]
    target = identifier(product, "SMILES")
    if not target:
        return
    target = chemical_key(target, target)
    context = {k: v for k, v in raw.items() if k not in ("inputs", "outcomes", "provenance", "reaction_id")}
    context["target_product"] = target
    context["analyses"] = outcome.get("analyses", {})
    context["reaction_time"] = outcome.get("reaction_time")
    context["dataset_id"] = record["source"]["dataset_id"]
    provenance = raw.get("provenance", {})
    context["publication"] = {k: provenance[k] for k in ("doi", "publication_url") if k in provenance}
    inputs = copy.deepcopy(raw.get("inputs", {}))
    entries = []
    for key, group in sorted(inputs.items()):
        for index, component in enumerate(group.get("components", [])):
            smiles = identifier(component, "SMILES")
            # A missing chemical identity would make 'all other conditions equal' unverifiable.
            if not smiles:
                return
            component.pop("identifiers", None)
            component["chemical_identity"] = chemical_key(smiles, smiles)
            entries.append((key, index, component))
    baseline = {"context": context, "inputs": inputs}
    context_hash = digest(context)
    solvent_groups = defaultdict(list)
    for key, index, component in entries:
        role = component.get("reaction_role")
        amount = component.get("amount", {})
        dimensions = [k for k in ("moles", "mass", "volume") if "value" in amount.get(k, {})]
        normalized = quantity(amount[dimensions[0]]) if len(dimensions) == 1 else None
        active = normalized is not None and normalized["value"] > 0 and normalized["unit"] in ("mmol", "mg", "mL")
        if not active:
            continue
        identity = component["chemical_identity"]
        if role == "SOLVENT":
            solvent_groups[identity].append((key, index))
        if role in ("CATALYST", "REAGENT"):
            masked = copy.deepcopy(inputs)
            masked[key]["components"][index]["chemical_identity"] = "__changed_identity__"
            yield "C3", digest({"context": context_hash, "inputs": masked}), identity, target
        if role in ("CATALYST", "REAGENT", "REACTANT"):
            dimension = dimensions[0]
            masked = copy.deepcopy(inputs)
            masked[key]["components"][index]["amount"][dimension]["value"] = "__changed_quantity__"
            yield "C4", digest({"context": context_hash, "inputs": masked}), canonical(amount[dimension]), target
    for identity, positions in solvent_groups.items():
        masked = copy.deepcopy(inputs)
        for key, index in positions:
            masked[key]["components"][index]["chemical_identity"] = "__changed_solvent__"
        yield "C1", digest({"context": context_hash, "inputs": masked}), identity, target
    for risk, path in (("C2", ("conditions", "temperature", "setpoint")), ("C6", ("reaction_time",))):
        changed = copy.deepcopy(context)
        changed_quantity = changed
        for key in path:
            changed_quantity = changed_quantity.get(key, {}) if isinstance(changed_quantity, dict) else {}
        normalized = quantity(changed_quantity)
        if normalized and normalized["unit"] == ("s" if risk == "C6" else "°C") and (risk != "C6" or normalized["value"] > 0):
            original = canonical(changed_quantity)
            changed_quantity["value"] = "__changed_value__"
            yield risk, digest({"context": changed, "inputs": baseline["inputs"]}), original, target


def pair_groups(records):
    """Replicate disagreement disqualifies a setting, rather than cherry-picking runs."""
    groups = defaultdict(lambda: defaultdict(list))
    for record in records:
        for risk, key, variant, target in contrast_views(record):
            groups[(risk, key)][variant].append({"id": record["id"], "yield_percent": record["yield_percent"],
                                                "raw_sha256": record["raw_sha256"], "source": record["source"],
                                                "target": target})
    for (risk, key), variants in sorted(groups.items()):
        successes = [(v, sorted(rows, key=lambda r: r["id"])) for v, rows in sorted(variants.items())
                     if min(r["yield_percent"] for r in rows) > 30]
        failures = [(v, sorted(rows, key=lambda r: r["id"])) for v, rows in sorted(variants.items())
                    if max(r["yield_percent"] for r in rows) < 5]
        if not successes:
            continue
        success_variant, good = successes[0]
        for failure_variant, bad in failures:
            if success_variant == failure_variant:
                continue
            group = split_group({"reaction_smiles": ">>" + bad[0]["target"]})
            fraction = int(digest(group)[:8], 16) % 100
            yield {"id": "contrast_" + risk + "_" + digest({"key": key, "variant": failure_variant})[:16],
                   "risk_hypothesis": risk, "condition_context_sha256": key,
                   "success_setting": success_variant, "failure_setting": failure_variant,
                   "success_observations": good, "failure_observations": bad,
                   "split_group": group, "split": "train" if fraction < 70 else "val" if fraction < 85 else "test",
                   "label_type": "real_matched_observations", "benchmark_eligible": False,
                   "causal_attribution": "not_established; exact equality covers recorded variables only",
                   "not_a_synthetic_mutation": True}


def build_contrasts():
    studies = load_library("studies.yaml")["studies"]
    records = (r for r in read_raw() if r["source"]["dataset_id"] in studies)
    contrasts = list(pair_groups(records))
    write_jsonl(ROOT / "data/hte/contrasts.jsonl", contrasts)
    report = {"contrasts": len(contrasts), "per_risk": dict(Counter(c["risk_hypothesis"] for c in contrasts)),
              "experimental_runs": len({r["id"] for c in contrasts for side in ("success_observations", "failure_observations") for r in c[side]}),
              "scaffold_groups": len({c["split_group"] for c in contrasts}),
              "success_threshold": ">30% in every matched replicate", "failure_threshold": "<5% in every matched replicate",
              "judge_admitted": False, "claim": "Single recorded factor contrasts; no causal certificate, no gold parent promotion."}
    write_json(ROOT / "reports/hte_contrasts.json", report)
    return report


def audit_contrasts():
    """Verify source records, equality masks, labels, splits and complete replicate sets."""
    from .yields import target_yield
    contrasts = list(read_jsonl(ROOT / "data/hte/contrasts.jsonl"))
    observations = {r["id"]: r for c in contrasts for side in ("success_observations", "failure_observations") for r in c[side]}
    originals, failures = {}, []
    for source in read_json(ROOT / "data/sources.lock.json")["files"]:
        if not any(r["source"]["file"] == source["path"] for r in observations.values()):
            continue
        path = ROOT / source["path"]
        if digest(path.read_bytes()) != source["sha256"]:
            failures.append("source_checksum:" + source["path"])
        for raw, _ in iter_ord(path, ids=set(observations)):
            originals[raw["reaction_id"]] = raw
    for identifier_, row in observations.items():
        raw = originals.get(identifier_)
        if raw is None or digest(raw) != row["raw_sha256"]:
            failures.append("upstream_observation:" + identifier_)
        elif target_yield(raw)[0] != row["yield_percent"]:
            failures.append("target_yield:" + identifier_)
    # Reconstruct against every run, including intermediate yields and discordant replicates.
    studies = load_library("studies.yaml")["studies"]
    expected = list(pair_groups(r for r in read_raw() if r["source"]["dataset_id"] in studies))
    if contrasts != expected:
        failures.append("full_corpus_contrast_or_replicate_mismatch")
    result = {"passed": not failures, "contrasts_checked": len(contrasts),
              "upstream_runs_checked": len(originals), "full_corpus_replicates_rechecked": True,
              "failures": failures}
    write_json(ROOT / "reports/hte_contrasts_audit.json", result)
    return result
