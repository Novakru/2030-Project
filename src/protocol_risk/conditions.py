"""Full pinned-corpus success index used to discard known false negatives."""
from __future__ import annotations

import sqlite3
from collections import defaultdict
from functools import lru_cache

from .io import ROOT, canonical, digest


@lru_cache(maxsize=20000)
def chemical_key(smiles, name):
    if smiles:
        try:
            from rdkit import Chem, RDLogger
            RDLogger.DisableLog("rdApp.error")
            mol = Chem.MolFromSmiles(smiles)
            if mol:
                return Chem.MolToSmiles(mol)
        except ImportError:
            pass
    return smiles or name.strip().lower()


def fingerprint(reaction_smiles, components, temperature, duration, gas):
    amounts = defaultdict(float)
    unquantified = []
    for reagent, amount in components:
        if amount and amount["value"] == 0:
            continue  # Explicitly zero-dose components represent absence.
        key = chemical_key(reagent.get("smiles"), reagent["name"])
        if amount:
            amounts[(key, reagent.get("role"), amount["unit"])] += amount["value"]
        else:
            unquantified.append((key, reagent.get("role")))
    if reaction_smiles and ">" in reaction_smiles:
        sides = reaction_smiles.split(">")
        reaction_smiles = chemical_key(sides[0], sides[0]) + ">>" + chemical_key(sides[-1], sides[-1])
    return digest({"reaction": reaction_smiles, "components": sorted((key, round(value, 8)) for key, value in amounts.items()),
                   "unquantified": sorted(unquantified),
                   "temp_C": round(temperature, 4) if temperature is not None else None,
                   "duration_s": round(duration, 4) if duration is not None else None,
                   "gas": (gas or "UNKNOWN").upper()})


def raw_key(raw):
    return fingerprint(raw.get("reaction_smiles"), [(c, c.get("amount")) for c in raw["components"]],
                       raw["temperature"]["value"] if raw.get("temperature") else None,
                       raw["duration"]["value"] if raw.get("duration") else None,
                       raw.get("atmosphere", {}).get("type"))


def protocol_key(protocol):
    reagents = {r["id"]: r for r in protocol["reagents"]}
    reaction_steps = [s for s in protocol["steps"] if s.get("meta", {}).get("stage", "reaction") == "reaction"]
    components = [(reagents[s["reagent"]], s.get("amount")) for s in reaction_steps
                  if s["op"] == "Add" and reagents.get(s["reagent"], {}).get("role") != "WORKUP"]
    temperatures = [s["temp_C"] for s in reaction_steps if s.get("temp_C") is not None]
    durations = [s["duration_s"] for s in reaction_steps if s.get("duration_s") is not None]
    gases = [s.get("gas") for s in reaction_steps if s["op"] == "Atmosphere"]
    gas = gases[-1] if gases else protocol.get("context", {}).get("atmosphere", {}).get("type")
    return fingerprint(protocol.get("reaction_smiles"), components, temperatures[-1] if temperatures else None,
                       max(durations) if durations else None, gas)


class SuccessIndex:
    def __init__(self, path=None):
        path = path or ROOT / "data/intermediate/success_conditions.sqlite"
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.execute("CREATE TABLE IF NOT EXISTS success (signature TEXT PRIMARY KEY, reaction_id TEXT NOT NULL)")

    def build(self, records):
        self.db.execute("DELETE FROM success")
        count = 0
        for record in records:
            if record.get("yield_percent") is not None and record["yield_percent"] >= 30:
                self.db.execute("INSERT OR IGNORE INTO success VALUES (?, ?)", (raw_key(record), record["id"]))
                count += 1
        self.db.commit()
        return count

    def match(self, protocol):
        return self.db.execute("SELECT reaction_id FROM success WHERE signature = ?", (protocol_key(protocol),)).fetchone()

    def close(self):
        self.db.close()
