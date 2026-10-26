from protocol_risk.publications import inspect_xdl, repair_representation
from protocol_risk.io import ROOT
import pytest


def test_publication_success_partition_is_not_a_feasibility_certificate():
    result = inspect_xdl(b'<Synthesis><Hardware><Component id="v" type="reactor"/></Hardware><Reagents><Reagent name="water"/></Reagents><Procedure><Add vessel="v" reagent="water" volume="1 mL"/></Procedure></Synthesis>')
    assert result["xml_parse_valid"]
    assert result["unresolved_references"] == []
    assert not result["full_feasibility_certified"]
    assert result["platform_compilation"] == "not_checked_by_static_inspector"


def test_mechanical_repair_changes_only_tag_case_and_a_declared_symbol_space():
    source = b'<Synthesis><Hardware><Component id="v"/></Hardware><Reagents><Reagent name="water"/></Reagents><Procedure><ASync><Add vessel="v" reagent="water " volume="1 mL"/></Async></Procedure></Synthesis>'
    repaired, edits = repair_representation(source)
    assert {e["kind"] for e in edits} == {"tag_case", "symbol_whitespace"}
    assert inspect_xdl(repaired)["unresolved_references"] == []
    assert b'volume="1 mL"' in repaired


def test_missing_chemical_is_not_filled_by_representation_repair():
    source = b'<Synthesis><Hardware><Component id="v"/></Hardware><Reagents/><Procedure><Add vessel="v" reagent="imagined" volume="1 mL"/></Procedure></Synthesis>'
    repaired, edits = repair_representation(source)
    assert edits == []
    assert inspect_xdl(repaired)["unresolved_references"]


def test_missing_references_and_placeholders_stay_visible():
    result = inspect_xdl(b'<Synthesis><Hardware/><Reagents/><Procedure><Add vessel="missing" reagent="undefined" volume="1 mL"/></Procedure></Synthesis>')
    assert len(result["unresolved_references"]) == 1
    assert len(result["placeholder_references"]) == 1


def test_graph_bound_components_are_distinct_from_missing_references():
    result = inspect_xdl(b'<Synthesis><Hardware/><Reagents/><Procedure><Add vessel="r" reagent="water" volume="1 mL"/></Procedure></Synthesis>',
                         {"nodes": [{"id": "r"}, {"id": "flask_water", "chemical": "water"}]})
    assert result["unresolved_references"] == []
    assert result["graph_present"]


def test_filter_cartridge_can_be_referenced_by_its_declared_chemical():
    result = inspect_xdl(b'<Synthesis><Hardware><Component id="r"/><Component id="cartridge" chemical="magnesium sulfate"/></Hardware><Reagents/><Procedure><FilterThrough from_vessel="r" to_vessel="r" through="magnesium sulfate"/></Procedure></Synthesis>')
    assert result["unresolved_references"] == []


def test_collected_members_and_repaired_copies_have_valid_hashes_and_replay():
    if not (ROOT / "data/publications/candidates.jsonl").exists():
        pytest.skip("Publication corpus has not been collected")
    from protocol_risk.publications import audit_publications
    result = audit_publications()
    assert result["passed"], result["failures"]
    assert result["counts"]["prepared_candidates_checked"] >= 100
