"""Conservative, provenance-bearing structural group recognition."""
from __future__ import annotations

from functools import lru_cache

from .io import load_library


@lru_cache(maxsize=10000)
def _groups(smiles, role):
    from rdkit import Chem
    if not smiles:
        return ()
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return ()
    normalized = Chem.MolToSmiles(mol)
    found = []
    for group, rule in load_library("reactivity.yaml")["groups"].items():
        if rule.get("exact_smiles"):
            if normalized in rule["exact_smiles"]:
                found.append(group)
            continue
        if role not in rule["roles"] or len(Chem.GetMolFrags(mol)) != 1 or Chem.GetFormalCharge(mol) != 0:
            continue
        if any(atom.GetNumRadicalElectrons() for atom in mol.GetAtoms()):
            continue
        if mol.HasSubstructMatch(Chem.MolFromSmarts(rule["smarts"])):
            found.append(group)
    return tuple(found)


def groups(reagent):
    return set(_groups(reagent.get("smiles"), reagent.get("role")))


def group_evidence(reagent):
    definitions = load_library("reactivity.yaml")["groups"]
    return [{"reagent": reagent["id"], "smiles": reagent.get("smiles"), "group": group,
             "basis": "conservative_structure_inference", "source_url": definitions[group]["source_url"]}
            for group in sorted(groups(reagent))]
