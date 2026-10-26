import pytest

from protocol_risk.native import material_contracts, missing_input, remove_statement

XML = '''<Synthesis><Procedure>
<Add vessel="reactor" reagent="solvent" volume="10 mL"/>
<Transfer from_vessel="reactor" to_vessel="rotavap" volume="all"/>
<Evaporate vessel="rotavap" temp="30 C"/>
</Procedure></Synthesis>'''
GRAPH = {"nodes": [{"id": "rotavap", "current_volume": 0}]}


def test_one_removed_material_input_leaves_the_consumer_without_feed():
    contract, = material_contracts(XML, GRAPH)
    assert not missing_input(XML, contract)
    child = remove_statement(XML, contract["producer_xpath"])
    assert missing_input(child, contract)
    assert "<Evaporate" in child and "<Transfer" not in child


def test_preloaded_or_unknown_destination_cannot_prove_a_required_input():
    assert material_contracts(XML, {"nodes": []}) == []
    assert material_contracts(XML, {"nodes": [{"id": "rotavap", "current_volume": 10}]}) == []


def test_alternative_liquid_input_disqualifies_the_sole_input_contract():
    xml = XML.replace('<Evaporate', '<Add vessel="rotavap" reagent="water" volume="1 mL"/><Evaporate')
    assert material_contracts(xml, GRAPH) == []


def test_filter_to_washsolid_alone_is_not_a_required_step_contract():
    # WashSolid includes filtration itself in the official XDL definition.
    xml = '<Synthesis><Procedure><Filter vessel="filter"/><WashSolid vessel="filter" solvent="water" volume="5 mL"/></Procedure></Synthesis>'
    assert material_contracts(xml, {"nodes": [{"id": "filter", "current_volume": 0}]}) == []


def test_asynchronous_order_is_not_inferred_by_document_order():
    assert material_contracts(XML.replace('<Transfer', '<Async><Transfer').replace('<Evaporate', '</Async><Evaporate'), GRAPH) == []


def test_doctype_is_refused():
    with pytest.raises(ValueError, match="DOCTYPE"):
        material_contracts('<!DOCTYPE Synthesis []>' + XML, GRAPH)
