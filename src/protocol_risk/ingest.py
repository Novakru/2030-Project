"""Read pinned ORD Parquet or legacy protobuf without losing source records."""
from __future__ import annotations

import gzip
import math
import re
from collections import Counter
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
import requests
from google.protobuf.json_format import MessageToDict
from ord_schema.proto import dataset_pb2, reaction_pb2

from .io import ROOT, canonical, digest, read_json, write_json, write_jsonl
from .yields import POLICY as YIELD_POLICY, target_yield

UNITS = {
    "MICROLITER": ("mL", 0.001), "MILLILITER": ("mL", 1), "LITER": ("mL", 1000),
    "MICROGRAM": ("mg", 0.001), "MILLIGRAM": ("mg", 1), "GRAM": ("mg", 1000),
    "MICROMOLE": ("mmol", 0.001), "MILLIMOLE": ("mmol", 1), "MOLE": ("mmol", 1000),
    "NANOMOLE": ("mmol", 0.000001),
    "SECOND": ("s", 1), "MINUTE": ("s", 60), "HOUR": ("s", 3600), "DAY": ("s", 86400),
    "CELSIUS": ("°C", 1), "RPM": ("RPM", 1),
}


def quantity(value):
    if not isinstance(value, dict) or "value" not in value:
        return None
    unit = value.get("units")
    try:
        numeric = float(value["value"])
    except (ValueError, TypeError):
        return None
    if not math.isfinite(numeric):
        return None
    if unit == "KELVIN":
        return {"value": round(numeric - 273.15, 8), "unit": "°C"}
    if unit == "FAHRENHEIT":
        return {"value": round((numeric - 32) * 5 / 9, 8), "unit": "°C"}
    if unit not in UNITS:
        return {"value": numeric, "unit": unit}
    normalized, factor = UNITS[unit]
    return {"value": round(numeric * factor, 10), "unit": normalized}


def identifier(component, kind):
    return next((x["value"] for x in component.get("identifiers", []) if x.get("type") == kind), None)


def iter_ord(path, ids=None):
    path = Path(path)
    if path.suffix == ".parquet":
        source = pq.ParquetFile(path)
        metadata = {k.decode(): v.decode() for k, v in (source.metadata.metadata or {}).items()
                    if k.startswith(b"ord.")}
        columns = ["reaction"] if ids is None else ["reaction_id", "reaction"]
        selected = pa.array(sorted(ids)) if ids is not None else None
        for batch in source.iter_batches(batch_size=256, columns=columns):
            blobs = batch.column("reaction")
            if selected is not None:
                blobs = blobs.filter(pc.is_in(batch.column("reaction_id"), value_set=selected))
            for blob in blobs.to_pylist():
                reaction = reaction_pb2.Reaction.FromString(blob)
                yield MessageToDict(reaction, preserving_proto_field_name=True), metadata
    else:
        blob = gzip.decompress(path.read_bytes()) if path.suffix == ".gz" else path.read_bytes()
        dataset = dataset_pb2.Dataset.FromString(blob)
        metadata = {"ord.dataset_id": dataset.dataset_id, "ord.name": dataset.name,
                    "ord.description": dataset.description}
        for reaction in dataset.reactions:
            if ids is None or reaction.reaction_id in ids:
                yield MessageToDict(reaction, preserving_proto_field_name=True), metadata


def normalize(raw, metadata, source):
    components = []
    for input_key, group in sorted(raw.get("inputs", {}).items()):
        for index, component in enumerate(group.get("components", [])):
            name = identifier(component, "NAME")
            smiles = identifier(component, "SMILES")
            amount = component.get("amount", {})
            measurement = next((quantity(amount[k]) for k in ("volume", "mass", "moles") if k in amount), None)
            components.append({"id": "r" + str(len(components) + 1),
                               "name": name or smiles or input_key, "smiles": smiles,
                               "role": component.get("reaction_role", "UNSPECIFIED"),
                               "amount": measurement, "input_key": input_key,
                               "addition_order": group.get("addition_order"),
                               "addition_time": quantity(group.get("addition_time", {})),
                               "source_path": f"/inputs/{input_key}/components/{index}"})
    conditions = raw.get("conditions", {})
    outcomes = raw.get("outcomes", [])
    yield_percent, yield_evidence = target_yield(raw)
    reaction_smiles = identifier(raw, "REACTION_SMILES")
    reactants = sorted(x["smiles"] for x in components if x["role"] == "REACTANT" and x["smiles"])
    products = sorted({identifier(p, "SMILES") for o in outcomes for p in o.get("products", [])
                       if identifier(p, "SMILES") and p.get("reaction_role") in ("PRODUCT", None)})
    if not reaction_smiles and reactants and products:
        reaction_smiles = ".".join(reactants) + ">>" + ".".join(products)
    setup = raw.get("setup", {})
    atmosphere = conditions.get("pressure", {}).get("atmosphere", {})
    if not atmosphere.get("type"):
        atmosphere = environment_atmosphere(setup) or atmosphere
    return {
        "id": raw.get("reaction_id"), "source": {"db": "ORD", "dataset_id": metadata.get("ord.dataset_id"),
        "dataset_name": metadata.get("ord.name"), "reaction_id": raw.get("reaction_id"),
        "url": source["url"], "file": source["path"], "file_sha256": source["sha256"],
        "publication_url": raw.get("provenance", {}).get("publication_url"),
        "license": "CC-BY-SA-4.0"}, "raw_sha256": digest(raw),
        "reaction_smiles": reaction_smiles,
        "reaction_class": identifier(raw, "REACTION_TYPE") or metadata.get("ord.name"),
        "procedure": raw.get("notes", {}).get("procedure_details", ""),
        "components": components,
        "temperature": quantity(conditions.get("temperature", {}).get("setpoint", {})),
        "duration": next((quantity(o["reaction_time"]) for o in outcomes if "reaction_time" in o), None),
        "atmosphere": atmosphere,
        "setup": setup, "conditions": conditions, "yield_percent": yield_percent,
        "yield_evidence": yield_evidence,
        "raw": raw,
    }


def environment_atmosphere(setup):
    environment = setup.get("environment", {})
    details = environment.get("details", "")
    if environment.get("type") != "GLOVE_BOX":
        return None
    if re.search(r"\bnitrogen\b|\bN2\b", details, re.I):
        return {"type": "NITROGEN", "derived_from": "/setup/environment/details"}
    if re.search(r"\bargon\b", details, re.I):
        return {"type": "ARGON", "derived_from": "/setup/environment/details"}
    return None


def fetch_locked():
    manifest = read_json(ROOT / "data/sources.lock.json")
    for item in manifest["files"]:
        path = ROOT / item["path"]
        if path.exists() and digest(path.read_bytes()) == item["sha256"]:
            continue
        response = requests.get(item["url"], timeout=120)
        response.raise_for_status()
        if digest(response.content) != item["sha256"]:
            raise ValueError(f"Source checksum mismatch: {path.name}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(response.content)


def ingest():
    manifest = read_json(ROOT / "data/sources.lock.json")
    records, stats = [], []
    for item in manifest["files"]:
        path = ROOT / item["path"]
        if digest(path.read_bytes()) != item["sha256"]:
            raise ValueError(f"Source checksum mismatch: {path.name}")
        count = Counter()
        for raw, metadata in iter_ord(path):
            record = normalize(raw, metadata, item)
            records.append(record)
            count["reactions"] += 1
            count["with_procedure"] += bool(record["procedure"])
            count["yield_above_30"] += record["yield_percent"] is not None and record["yield_percent"] > 30
            count["yield_status_" + record["yield_evidence"]["status"]] += 1
            count["temperature_and_duration"] += bool(record["temperature"] and record["duration"])
        stats.append({"file": path.name, "name": metadata.get("ord.name"), **count})
    records.sort(key=lambda x: x["id"])
    # A JSON string preserves each complete normalized record in Parquet as well.
    table = pa.Table.from_pylist([{"id": x["id"], "dataset_id": x["source"]["dataset_id"],
                                  "procedure": x["procedure"], "yield_percent": x["yield_percent"],
                                  "record_json": canonical(x)} for x in records])
    pq.write_table(table, ROOT / "data/raw/reactions.parquet", compression="zstd")
    write_json(ROOT / "reports/ingest.json", {"total": len(records), "datasets": stats})
    return stats


def read_raw(ids=None):
    """Stream normalized records from the compact Parquet archive."""
    import json
    source = pq.ParquetFile(ROOT / "data/raw/reactions.parquet")
    columns = ["record_json"] if ids is None else ["id", "record_json"]
    selected = pa.array(sorted(ids)) if ids is not None else None
    for batch in source.iter_batches(batch_size=128, columns=columns):
        values = batch.column("record_json")
        if selected is not None:
            values = values.filter(pc.is_in(batch.column("id"), value_set=selected))
        for value in values.to_pylist():
            record = json.loads(value)
            if record.get("yield_evidence", {}).get("policy") != YIELD_POLICY:
                record["yield_percent"], record["yield_evidence"] = target_yield(record["raw"])
            if not record["atmosphere"].get("type"):
                record["atmosphere"] = environment_atmosphere(record["setup"]) or record["atmosphere"]
            # Compatibility with initial snapshots written before nanomole normalization.
            for component in record["components"]:
                if (component.get("amount") or {}).get("unit") == "NANOMOLE":
                    component["amount"] = {"unit": "mmol", "value": component["amount"]["value"] * 0.000001}
            yield record
