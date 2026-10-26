import copy

import pytest

from protocol_risk.controls import reference
from protocol_risk.reactivity import groups
from protocol_risk.symbolic import evaluate


@pytest.mark.parametrize("smiles", ["CC(=O)O", "O=C(O)c1ccccc1", "CCC(=O)O"])
def test_free_organic_carboxylic_acids_are_recognized(smiles):
    assert groups({"smiles": smiles, "role": "REACTANT"}) == {"carboxylic_acid"}


@pytest.mark.parametrize("smiles", ["O=C([O-])C.[Na+]", "O=C(O)[O-].[Na+]", "CC(=O)O.CC(=O)O.[Pd]", "CC#N", "CC(=O)OC"])
def test_salts_bicarbonate_disconnected_complexes_nitriles_and_esters_are_excluded(smiles):
    assert not groups({"smiles": smiles, "role": "REACTANT"})


def test_only_specific_cyanide_salt_is_classified():
    assert groups({"smiles": "[Na+].[C-]#N", "role": "REAGENT"}) == {"cyanide"}
    assert not groups({"smiles": "CC#N", "role": "SOLVENT"})


def test_contact_requires_the_two_groups_and_liquid_inventory():
    parent = reference("B4", 0)
    parent["reagents"][1].update(name="acetic acid", chemical=None, smiles="CC(=O)O", role="REACTANT")
    assert evaluate(parent).risks == []
    child = copy.deepcopy(parent)
    child["reagents"][2].update(name="sodium cyanide", chemical=None, smiles="[C-]#N.[Na+]")
    assert evaluate(child).risks == ["B4"]
    child["reagents"][1]["smiles"] = "CC(=O)[O-].[Na+]"
    assert evaluate(child).risks == []
