"""Metamorphic checks at the text/reference boundary; no remote API is used."""
import copy
import json

import pytest

from mosaic.chemistry import ChemistryDomain
from protocol_risk.extract import build_ir, text_plan, text_source, validate_evidence, uncovered_actions
from protocol_risk.crosscheck import quantities_in_text
from protocol_risk.amounts import local_measurements
from protocol_risk.validation import prepare_protocol


TEXT = "A 5 mL microreactor was charged with water (1 mL). Heat at 20 C for 1 hour."
PLAN = {"steps": [
    {"op": "Add", "reagent": "water", "alias": "water", "role": "SOLVENT", "amount": {"value": 1, "unit": "mL"},
     "evidence": "A 5 mL microreactor was charged with water (1 mL)."},
    {"op": "HeatChill", "temp_C": 20, "duration_s": 3600, "evidence": "Heat at 20 C for 1 hour."}],
    "uncertainties": [], "unmapped_actions": []}


def record():
    return {"id": "text_fixture", "procedure": TEXT, "raw_sha256": "source-proof",
            "source": {"db": "ORD", "url": "https://example.test/source"},
            "components": [{"id": "ord_component", "name": "water", "smiles": "O", "role": "SOLVENT",
                            "amount": {"value": 99, "unit": "mL"}}],
            "conditions": {"pressure": {"control": {"type": "AMBIENT"}}},
            "atmosphere": {"type": "ARGON"}, "temperature": {"value": 95},
            "duration": {"value": 7}, "yield_percent": 90, "reaction_smiles": "C>>CO",
            "setup": {"vessel": {"type": "VIAL", "volume": {"value": 100, "units": "MILLILITER"}}},
            "raw": {"notes": {"is_sensitive_to_oxygen": True}}}


class Client:
    def __init__(self):
        self.prompts = []

    def complete(self, system, prompt):
        self.prompts.append(json.loads(prompt))
        return {"data": copy.deepcopy(PLAN), "model": "fixture-model"}


class Runner:
    def __init__(self):
        self.client, self.roles = Client(), []

    def extraction_client(self):
        return self.client

    def model_call(self, role, system, payload):
        self.roles.append((role, payload))
        data = {"findings": [], "patch": []} if role == "critic" else {"mentions": [], "unknowns": []}
        return {"data": data}


def test_admitted_library_composition_is_used_by_real_domain_interface():
    from tests.test_mosaic_representation import SOURCE, admitted_registry, plan

    runner = Runner()
    class MacroClient:
        def complete(self, system, prompt):
            runner.client_prompt = json.loads(prompt)
            return {"data": plan(), "model": "explicit-test-double"}
    runner.client = MacroClient()
    domain = ChemistryDomain().with_registry(admitted_registry())
    raw = {"id": "literal_composition", "procedure": SOURCE, "raw_sha256": "test-source",
           "source": {"db": "TEXT", "url": "https://example.invalid/literal"}}
    extracted = domain.extract(raw, runner)
    prepared = domain.validate(extracted, raw, "test-run")
    assert "DoseThenStir" in runner.client_prompt["representations"]["macros"]
    assert [step["op"] for step in prepared["steps"]] == ["Add", "Stir"]
    assert 'time="60 s"' in prepared["xdl"] and "DoseThenStir" not in prepared["xdl"]


def test_every_extraction_role_sees_only_literal_text_and_proposed_plan():
    runner = Runner()
    result = ChemistryDomain().extract(record(), runner)
    assert runner.client.prompts == [{"procedure": TEXT}]
    assert set(runner.roles[0][1]) == {"source", "plan"}
    assert runner.roles[1][1] == {"source": TEXT}
    serialized = json.dumps([runner.client.prompts, runner.roles])
    assert "ord_component" not in serialized and "ARGON" not in serialized
    assert result["protocol"]["reagents"][0]["smiles"] is None


def test_removing_or_poisoning_ord_fields_cannot_change_operations_hardware_or_xdl():
    raw = record()
    variants = [raw, text_source(raw), {**raw, "components": [], "setup": {"vessel": {"type": "WELL_PLATE"}},
                "conditions": {"flow": {"details": "poison"}}, "atmosphere": {"type": "NITROGEN"},
                "temperature": {"value": -100}, "duration": {"value": 100000},
                "yield_percent": None, "reaction_smiles": "poison"}]
    prepared = [prepare_protocol(build_ir(row, copy.deepcopy(PLAN), {}), row) for row in variants]
    for field in ("steps", "reagents", "context", "hardware", "xdl", "canonical_sha1"):
        assert prepared[0][field] == prepared[1][field] == prepared[2][field]
    assert prepared[0]["hardware"]["nodes"]["reactor"]["params"]["capacity_mL"] == 5
    assert prepared[0]["crosscheck"]["reference_comparison"]["conflicts"]
    assert not prepared[0]["crosscheck"]["conflicts"]
    assert "source_reference_disagreement_requires_review" in prepared[0]["crosscheck"]["gold_blockers"]
    assert "inert_required" not in prepared[0]["context"]


def test_plain_text_needs_no_ord_metadata_or_outcome_to_produce_xdl():
    raw = {"id": "plain", "procedure": TEXT, "source": {"db": "TEXT", "url": "file:///experiment.txt"}}
    plan, _ = text_plan(raw, Client())
    prepared = prepare_protocol(build_ir(raw, plan, {}), raw)
    assert "<Add" in prepared["xdl"] and "<HeatChill" in prepared["xdl"]
    assert prepared["quality"]["source_input_contract"] == "text-only/1"
    assert "yield_percent" not in prepared


def test_unknown_text_quantity_is_never_borrowed_from_ord():
    raw = record()
    raw["procedure"] = "Add water."
    plan = {"steps": [{"op": "Add", "reagent": "water", "evidence": "Add water."}]}
    protocol = build_ir(raw, plan, {})
    assert "amount" not in protocol["steps"][0]
    with pytest.raises(ValueError, match="unknown source parameters"):
        prepare_protocol(protocol, raw)


def test_amount_cannot_be_borrowed_from_a_different_literal_reagent():
    raw = {"procedure": "Add water (1 mL) and ethanol (7 mL)."}
    plan = {"steps": [{"op": "Add", "reagent": "water", "alias": "water", "amount": {"value": 7, "unit": "mL"},
                       "evidence": raw["procedure"]}]}
    assert any("adjacent" in error for error in validate_evidence(raw, plan))


def test_alias_cannot_relabel_another_reagents_explicit_quantity():
    raw = {"procedure": "Add water (1 mL) and ethanol (7 mL)."}
    plan = {"steps": [{"op": "Add", "reagent": "water", "alias": "ethanol", "amount": {"value": 7, "unit": "mL"},
                       "evidence": raw["procedure"]}]}
    assert any("same literal name" in error for error in validate_evidence(raw, plan))


def test_model_cannot_insert_an_ungrounded_controller_parameter():
    plan = copy.deepcopy(PLAN)
    plan["steps"][1]["controller_setpoint_C"] = 999
    assert any("outside the text extraction contract" in error for error in validate_evidence(record(), plan))


def test_omitted_physical_actions_are_retained_for_library_evolution():
    raw = record()
    raw["procedure"] += " The product was dried under vacuum."
    protocol = build_ir(raw, copy.deepcopy(PLAN), {})
    assert any("dried" in action["evidence"] for action in protocol["extraction"]["unmapped_actions"])
    with pytest.raises(ValueError, match="not mapped"):
        prepare_protocol(protocol, raw)


def test_short_text_is_eligible_without_structured_fallback():
    domain = ChemistryDomain()
    assert domain.eligible({"procedure": "Add water (1 mL)."})
    with pytest.raises(ValueError, match="Structured reconstruction is disabled"):
        domain.extract(record(), Runner(), use_model=False)


@pytest.mark.parametrize("text,dimension,value", [
    ("for 2 days", "duration_s", 172800), ("dose 200 nL", "mL", .0002),
    ("80 µL per well", "mL", .08), ("10 μg", "mg", .01),
    ("50 nmol", "mmol", .00005), ("0.2 L", "mL", 200)])
def test_explicit_units_convert_without_dropping_dimensions(text, dimension, value):
    assert quantities_in_text(text, dimension) == pytest.approx([value])


def test_shared_charge_verb_is_covered_by_separate_literal_reagent_quotes():
    text = "A 5.0 mL microreactor was charged with salt (1.98 mg) and water (1 mL)."
    plan = {"steps": [{"op": "Add", "evidence": "salt (1.98 mg)"},
                      {"op": "Add", "evidence": "water (1 mL)"}]}
    assert uncovered_actions(text, plan) == []


def test_missing_action_quote_is_not_truncated_at_a_decimal_point():
    text = "The salt (1.98 mg) was added. The product was dried for 0.5 hours."
    pending = uncovered_actions(text, {"steps": []})
    assert pending[0]["evidence"] == "The salt (1.98 mg) was added."
    assert pending[1]["evidence"] == "The product was dried for 0.5 hours."


def test_microwave_vial_name_does_not_imply_microwave_irradiation():
    domain = ChemistryDomain()
    assert domain.eligible({"procedure": "Water (1 mL) was added to a microwave vial."})
    assert not domain.eligible({"procedure": "Water (1 mL) was heated under microwave irradiation."})


@pytest.mark.parametrize("article", ["a", "an"])
def test_explicit_quantity_of_article_stays_bound_to_the_literal_material(article):
    name = "9:1 mixture of acetonitrile and buffer" if article == "a" else "aqueous solution"
    text = f"The vial was charged with 400 µL of {article} {name}."
    measurements, _ = local_measurements(text, name)
    assert [(x["value"], x["unit"]) for x in measurements] == [(0.4, "mL")]


def test_optional_representation_adapter_normalizes_before_literal_validation():
    class AliasClient:
        def __init__(self):
            self.payload = None

        def complete(self, system, prompt):
            self.payload = json.loads(prompt)
            plan = copy.deepcopy(PLAN)
            plan["steps"][0]["op"] = "Charge"
            return {"data": plan}

    client = AliasClient()
    contracts = {"aliases": {"Charge": "Add"}}
    def normalize(plan):
        plan["steps"][0]["op"] = "Add"
        return plan
    plan, _ = text_plan(record(), client, representations=contracts, normalizer=normalize)
    assert plan["steps"][0]["op"] == "Add"
    assert client.payload == {"procedure": TEXT, "representations": contracts}


def test_representation_normalization_failure_is_reported_and_retried():
    class AliasClient:
        calls = 0

        def complete(self, system, prompt):
            self.calls += 1
            return {"data": copy.deepcopy(PLAN)}

    client = AliasClient()
    def reject(plan):
        raise ValueError("macro invents an unobserved parameter")
    with pytest.raises(ValueError, match="macro invents an unobserved parameter"):
        text_plan(record(), client, normalizer=reject)
    assert client.calls == 3
