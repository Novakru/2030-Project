import copy
import json
from pathlib import Path

import pytest

from mosaic.pg.compile import linear_text, mermaid, ord_like, task_view, to_xdl
from mosaic.pg.evaluate import score
from mosaic.pg.ir import coerce, precedence_closure, topological_order, validate
from mosaic.pg.perturb import order_pairs, reverse_roles, scale_quantity, swap_steps
from mosaic.pg.preprocess import prepare
from mosaic.pg.prompts import FEWSHOT, extractor_system

ROOT = Path(__file__).resolve().parents[1]
GOLD_DIR = ROOT / "evaluation" / "procgraph_gold"


def gold(name):
    return json.loads((GOLD_DIR / f"{name}.json").read_text(encoding="utf-8"))


def tags(text):
    return [(q.text, q.value, q.upper, q.unit, q.kind) for q in prepare("t", text).quantities]


# ----------------------------------------------------------------------------- tagger
@pytest.mark.parametrize("text,expected", [
    ("at 0°-5° C. to a mixture", [("0°-5° C.", 0.0, 5.0, "degC", "temperature")]),
    ("stirred for another 1/2 hour at", [("1/2 hour", 0.5, None, "h", "time")]),
    ("HCl in dioxan (4-M).", [("4-M", 4.0, None, "M", "concentration")]),
    ("purged for ten minutes", [("ten minutes", 10.0, None, "min", "time")]),
    ("cooled to -78 °C", [("-78 °C", -78.0, None, "degC", "temperature")]),
    ("283 g. (1.77 moles) of bromine", [("283 g.", 283.0, None, "g", "mass"), ("1.77 moles", 1.77, None, "mol", "amount")]),
    ("at 80C for 24 h", [("80C", 80.0, None, "degC", "temperature"), ("24 h", 24.0, None, "h", "time")]),
    ("at ~600 rpm", [("~600 rpm", 600.0, None, "rpm", "rotation_speed")]),
    ("(1.98 mg, 1.5 mol%)", [("1.98 mg", 1.98, None, "mg", "mass"), ("1.5 mol%", 1.5, None, "mol%", "relative_loading")]),
    ("B2pin2 (50.8 mg, 1.0 equiv.)", [("50.8 mg", 50.8, None, "mg", "mass"), ("1.0 equiv.", 1.0, None, "equiv", "equivalents")]),
    ("washed with EtOAc (3 x 20 mL)", [("3 x", 3.0, None, "times", "count"), ("20 mL", 20.0, None, "mL", "volume")]),
    ("washed twice", [("twice", 2.0, None, "times", "count")]),
    ("(hexane/ether = 1:2 to 1:4)", [("1:2 to 1:4", None, None, "ratio", "ratio")]),
    ("in positions C4-9 ,D4-9", []),
    ("CI MS (M+H)+ 750", []),
    ("pH 7 - 5 mL added", [("5 mL", 5.0, None, "mL", "volume")]),
])
def test_quantity_literals(text, expected):
    assert tags(text) == expected


def test_characterization_is_not_tagged_and_procedure_mention_is():
    p = prepare("t", "Filtered to afford 4.61 g (61%): 1H NMR (CDCl3, 250 MHz): δ1.14 (6H, t), 2.23 (6H, s).")
    assert [q.text for q in p.quantities] == ["4.61 g", "61%"]
    assert p.sentences[-1].kind == "characterization"
    p2 = prepare("t", "Yields were validated by quantification of the 1H NMR spectrum of the entries.")
    assert all(s.kind == "procedure" for s in p2.sentences)


def test_sentence_split_respects_abbreviations():
    p = prepare("t", "Stirred (3-Position Stirrer, U.S. Series, Inc.) for 18 hours. Then cooled. p-TsOH (65 mg) was added.")
    assert len(p.sentences) == 3


# ----------------------------------------------------------------------------- IR
def test_all_gold_and_fewshot_satisfy_contract():
    for f in GOLD_DIR.glob("*.json"):
        d = json.loads(f.read_text(encoding="utf-8"))
        p = prepare(d["source_id"], d["text"])
        assert [q.id for q in p.quantities] == [q["id"] for q in d["quantities"]], f.name
        errors, _ = validate(d["graph"], p)
        assert errors == [], (f.name, errors)
    for ex in FEWSHOT:
        p = prepare("fs", ex["text"])
        g, _ = coerce(ex["answer"], p)
        assert validate(g, p)[0] == []


def test_coercion_absorbs_format_drift():
    p = prepare("t", "Water (1 mL) was added to a 5 mL vial. The mixture was stirred for 30 seconds.")
    raw = {"graph": {
        "materials": [{"id": "m1", "name": "Water"}],
        "equipment": [{"id": "e1", "name": "vial", "type": "vessel", "props": [{"attr": "capacity", "q": "5 mL"}]}],
        "steps": [
            {"id": "t1", "op": "Charge", "sentence": "S1", "inputs": [{"material": "Water", "amount": "1 mL"}],
             "vessel": "vial", "output": "x1"},
            {"id": "t1", "op": "stirring", "sentence": "S2", "target": {"state": "x1"},
             "params": {"duration": "30 seconds"}, "outputs": ["x2"]}]}}
    g, log = coerce(raw, p)
    errors, _ = validate(g, p)
    assert errors == []
    assert g["steps"][0]["op"] == "add" and g["steps"][0]["inputs"][0] == {"ref": "m1", "amounts": ["Q1"], "role": "", "note": ""}
    assert g["steps"][1]["id"] == "t1_2" and g["steps"][1]["op"] == "stir"
    codes = {x["code"] for x in log}
    assert {"C_UNWRAP", "C_Q_LITERAL", "C_REF_BY_NAME"} <= codes


def test_validator_reports_located_errors():
    p = prepare("t", "A (1.0 g) was added to a solution of B (2.0 g) in THF (10 mL) at 0 °C for 2 h.")
    raw = {"materials": [{"id": "a", "name": "A"}, {"id": "b", "name": "B"}, {"id": "thf", "name": "THF"}],
           "steps": [
               {"id": "t1", "op": "add", "sentences": ["S1"], "target": "x0", "inputs": [{"ref": "a", "amounts": ["Q1"]}],
                "params": {"temperature": {"q": ["Q5"]}}, "outputs": [{"id": "x1"}]},
               {"id": "t2", "op": "prepare", "sentences": ["S1"], "inputs": [{"ref": "b", "amounts": ["Q2"]}, {"ref": "thf"}],
                "outputs": [{"id": "x0"}]}]}
    g, log = coerce(raw, p)
    codes = {e["code"] for e in validate(g, p)[0]}
    fixes = {x["code"] for x in log}
    # Deterministic fixes: the solution is now prepared before use, "2 h" moved from temperature to duration.
    assert {"C_REORDER", "C_PARAM_RENAMED"} <= fixes
    assert [s["id"] for s in g["steps"]] == ["t2", "t1"] and "duration" in g["steps"][1]["params"]
    assert codes == {"E_Q_UNBOUND"}      # 10 mL and 0 °C are still not placed: that needs the model


def test_role_contract():
    p = prepare("t", "The mixture was stirred.")
    raw = {"materials": [{"id": "m", "name": "mixture"}],
           "steps": [{"id": "t1", "op": "stir", "sentences": ["S1"], "inputs": [{"ref": "m"}], "outputs": [{"id": "x"}]}]}
    g, log = coerce(raw, p)
    assert [s["op"] for s in g["steps"]] == ["add", "stir"]  # "stirred with X" split into add + stir
    assert g["steps"][1]["target"] == g["steps"][0]["outputs"][0]["id"]
    raw2 = {"steps": [{"id": "t1", "op": "filter", "sentences": ["S1"], "outputs": [{"id": "x"}]}]}
    g2, _ = coerce(raw2, p)
    assert "E_ROLE_TARGET" in {e["code"] for e in validate(g2, p)[0]}


# ----------------------------------------------------------------------------- order semantics
def test_suspension_is_prepared_before_addition():
    d = gold("syn-into-suspension")
    g = d["graph"]
    closure = precedence_closure(g)
    assert ("t1", "t3") in closure and ("t2", "t3") in closure   # both composites before the addition
    assert ("t1", "t2") not in closure and ("t2", "t1") not in closure  # but independent of each other
    add = next(s for s in g["steps"] if s["op"] == "add")
    assert add["target"] == "x2" and add["inputs"][0]["ref"] == "x1"


def test_reversed_minimal_pair_differs_only_in_roles():
    a, b = gold("syn-into-suspension")["graph"], gold("syn-reversed-roles")["graph"]
    lab = lambda g, ref: next(o["label"] for s in g["steps"] for o in s["outputs"] if o["id"] == ref)
    add_a = next(s for s in a["steps"] if s["op"] == "add")
    add_b = next(s for s in b["steps"] if s["op"] == "add")
    assert "suspension" in lab(a, add_a["target"]) and "solution" in lab(a, add_a["inputs"][0]["ref"])
    assert "solution" in lab(b, add_b["target"]) and "suspension" in lab(b, add_b["inputs"][0]["ref"])


def test_xdl_builds_composites_first_and_transfers_into_receiver():
    d = gold("ord-8841b6b409c7485da9c83fc3053ea8a7")
    p = prepare(d["source_id"], d["text"])
    xml, mapping = to_xdl(d["graph"], p)
    prep, reaction = xml.index("<Prep>"), xml.index("<Reaction>")
    assert prep < xml.index('reagent="3,7-dichloro-8-formylquinoline" mass="11.3 g"') < reaction
    assert '<Transfer from_vessel="prep_vessel_1" to_vessel="prep_vessel_2" volume="18 mL" dropwise="true"/>' in xml
    assert xml.count('reagent="ethanol"') == 1  # the receiver is not added a second time
    from lxml import etree
    etree.fromstring(xml.encode("utf-8"))
    assert [m["section"] for m in mapping][:2] == ["Prep", "Prep"]


def test_all_gold_compile_and_render():
    for f in GOLD_DIR.glob("*.json"):
        d = json.loads(f.read_text(encoding="utf-8"))
        p = prepare(d["source_id"], d["text"])
        xml, _ = to_xdl(d["graph"], p)
        from lxml import etree
        etree.fromstring(xml.encode("utf-8"))
        assert linear_text(d["graph"], p) and mermaid(d["graph"], p).startswith("flowchart")
        tv = task_view(d["graph"], p)
        assert len(tv["execution_order"]) == len(d["graph"]["steps"])
        ord_like(d["graph"], p)


def test_perturbations_carry_correct_labels():
    g = gold("syn-into-suspension")["graph"]
    pairs = {(x["a"], x["b"]): x["label"] for x in order_pairs(g)}
    assert pairs[("t1", "t2")] == "independent" and pairs[("t2", "t3")] == "must_precede"
    assert swap_steps(g, "t1", "t2")[1] is True
    assert swap_steps(g, "t2", "t3")[1] is False
    with pytest.raises(ValueError):
        topological_order({**g, "steps": [{**s, "after": ["t4"]} if s["id"] == "t1" else s for s in g["steps"]]})
    rev = reverse_roles(g, "t3")
    assert next(s for s in rev["steps"] if s["id"] == "t3")["target"] == "x1"
    d = gold("syn-into-suspension")
    p = prepare(d["source_id"], d["text"])
    text, change = scale_quantity(d["text"], p, "Q4", 2)
    assert change["to"] == "4.00 g" and "(4.00 g)" in text  # printed precision is preserved


# ----------------------------------------------------------------------------- evaluator
def test_evaluator_self_score_is_perfect():
    for f in GOLD_DIR.glob("*.json"):
        d = json.loads(f.read_text(encoding="utf-8"))
        r = score(d, d["graph"], d["quantities"])
        assert r["overall"] == 1.0, f.name


def test_evaluator_detects_role_reversal_and_missing_prep():
    d = gold("syn-into-suspension")
    rev = reverse_roles(d["graph"], "t3")
    r = score(d, rev, d["quantities"])
    assert r["role_acc"] < 1.0 and r["flow_f1"] == 1.0  # same edges, wrong roles
    flat = copy.deepcopy(d["graph"])
    flat["steps"] = [s for s in flat["steps"] if s["op"] != "prepare"]
    add = next(s for s in flat["steps"] if s["op"] == "add")
    add["target"] = None
    add["inputs"] = [{"ref": m, "amounts": [], "role": "", "note": ""} for m in ("mA", "mT", "mB", "mC", "mTol")]
    r2 = score(d, flat, d["quantities"])
    assert r2["order_f1"] < 0.5 and r2["qty_binding"] < 0.5 and r2["material_f1"] == 1.0


def test_extractor_prompt_is_self_consistent():
    s = extractor_system(prepare)
    assert "«Q1|" in s and "prepare [" in s and "RULES" in s


def test_undeclared_material_names_are_registered_but_ids_are_not():
    p = prepare("t", "The residue was dissolved in methanol.")
    raw = {"materials": [], "steps": [
        {"id": "t1", "op": "dissolve", "sentences": ["S1"], "target": "x9", "inputs": [{"ref": "methanol"}],
         "outputs": [{"id": "x1"}]}]}
    g, log = coerce(raw, p)
    assert g["materials"][0]["name"] == "methanol" and g["steps"][0]["inputs"][0]["ref"] == g["materials"][0]["id"]
    assert {e["code"] for e in validate(g, p)[0]} == {"E_REF"}  # the dangling state id x9 is still reported
