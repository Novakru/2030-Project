"""Public XDL keeps its element/attribute grammar, with sidecars for analysis."""
import copy
import json

import pytest
from lxml import etree

from mosaic.canonical import finalize_protocol
from mosaic.protocol.xdl import export_xdl, validate_xdl
from mosaic.protocol.xdl_document import read_document
from tests.test_canonical_pipeline import example


def test_native_reagents_units_missing_parameters_and_concurrent_stirring():
    raw = example()
    raw["steps"] += [{"id": "heat", "op": "HeatChill", "vessel": "v1", "temp_C": 50,
                       "duration_s": 60, "stir": True},
                      {"id": "mix", "op": "Stir", "vessel": "v1", "missing_parameters": {
                          "duration_s": {"marker": "__NOT_REPORTED__", "status": "not_reported", "raw": None, "evidence": "stir"}}}]
    record = finalize_protocol(raw)
    doc = read_document(record["xdl"], extensions=record["xdl_extensions"])
    assert doc["steps"][0] == {"op": "Add", "reagent": "water", "vessel": "v1", "volume": "1 mL"}
    assert [s["op"] for s in doc["steps"]] == ["Add", "HeatChill", "Stir"]
    assert doc["steps"][1]["stir"] == "true" and doc["steps"][1]["time"] == "60 s"
    assert doc["steps"][2]["time"] == doc["parameters"][0]["id"]
    assert "value" not in doc["parameters"][0]
    for private in ("mx:", "OperationDefinitions", "operation_id", "op.mix", "composition:"):
        assert private not in record["xdl"]
    assert export_xdl(json.loads(json.dumps(record, sort_keys=True))) == record["xdl"]


def test_export_never_repairs_an_intentionally_wrong_hardware_reference():
    raw = example()
    raw["steps"][0]["vessel"] = "missing_device"
    with pytest.raises(ValueError, match="cannot repair"):
        finalize_protocol(raw)


@pytest.mark.parametrize("alter", [
    lambda root: root.set("profile", "private-grammar"),
    lambda root: root.remove(root.find("Hardware")),
    lambda root: etree.SubElement(root.find("Procedure"), "UnregisteredOperation"),
    lambda root: root.find("Procedure")[0].set("cluster", "op.add"),
    lambda root: root.find("Procedure")[0].append(etree.Element("Object")),
    lambda root: root.find("Hardware").append(copy.deepcopy(root.find("Hardware")[0])),
])
def test_native_validator_rejects_unknown_grammar_and_duplicate_declarations(alter):
    record = finalize_protocol(example())
    root = etree.fromstring(record["xdl"].encode())
    alter(root)
    with pytest.raises(ValueError):
        validate_xdl(etree.tostring(root, encoding="unicode"), extensions=record["xdl_extensions"])
