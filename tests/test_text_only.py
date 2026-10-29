"""Metamorphic checks at the text/reference boundary; no remote API is used."""
import copy
import json

import pytest

from mosaic.chemistry import ChemistryDomain
from mosaic.canonical import finalize_protocol
from mosaic.protocol.extract import build_ir, text_plan, text_source, validate_evidence, uncovered_actions
from mosaic.protocol.crosscheck import quantities_in_text
from mosaic.protocol.amounts import local_measurements
from mosaic.protocol.validation import prepare_protocol


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


def test_admitted_library_composition_is_used_by_source_extractor():
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
    prepared = prepare_protocol(extracted["protocol"], raw)
    assert "DoseThenStir" in runner.client_prompt["representations"]["macros"]
    assert [step["op"] for step in prepared["steps"]] == ["Add", "Stir"]
    assert prepared["steps"][1]["duration_s"] == 60
    assert "DoseThenStir" not in finalize_protocol(prepared)["xdl"]


def test_bounded_repair_includes_failed_proposal_without_reference_fields():
    requests = []
    class RepairClient:
        def complete(self, system, prompt):
            requests.append(json.loads(prompt))
            proposed = copy.deepcopy(PLAN)
            if len(requests) == 1:
                proposed["steps"][0]["amount"]["value"] = 999
            return {"data": proposed, "model": "explicit-test-double"}
    proposed, _ = text_plan(record(), RepairClient())
    assert len(requests) == 2 and proposed["steps"][0]["amount"]["value"] == 1
    assert requests[1]["repair"]["previous_proposal"]["steps"][0]["amount"]["value"] == 999
    assert requests[1]["repair"]["validation_errors"]
    assert "ord_component" not in json.dumps(requests)


def test_short_heater_setup_quote_is_retained_as_context_not_false_omission():
    raw = {"id": "heater_text", "raw_sha256": "test-source",
           "source": {"db": "TEXT", "url": "https://example.invalid/heater"},
           "procedure": "water (1 mL) was added. The vial was placed into a pre-heated aluminum block at 80 oC for 1 hour."}
    plan = {"steps": [{"op": "Add", "reagent": "water", "amount": {"value": 1, "unit": "mL"},
                       "evidence": "water (1 mL) was added."},
                      {"op": "HeatChill", "temp_C": 80, "duration_s": 3600,
                       "evidence": "placed into a pre-heated aluminum block at 80 oC for 1 hour"}],
            "unmapped_actions": [{"evidence": "pre-heated aluminum block at 80 oC", "reason": "heater preparation"}]}
    prepared = prepare_protocol(build_ir(raw, plan, {}), raw)
    assert not prepared["extraction"]["unmapped_actions"]
    assert prepared["context"]["source_context_events"][0]["kind"] == "source_heater_setup"


def test_bad_critic_pointer_keeps_valid_text_plan_and_records_rejection():
    class BadPointerRunner(Runner):
        def model_call(self, role, system, payload):
            if role == "critic":
                return {"data": {"findings": [], "patch": [
                    {"op": "replace", "path": "/steps/0/params/temp_C", "value": 100}]}}
            return super().model_call(role, system, payload)
    extracted = ChemistryDomain().extract(record(), BadPointerRunner())
    assert extracted["notes"]["critic_rejected"]["error_class"] == "JsonPointerException"
    assert extracted["protocol"]["steps"][0]["amount"]["value"] == 1


def test_every_extraction_role_sees_only_literal_text_and_proposed_plan():
    runner = Runner()
    result = ChemistryDomain().extract(record(), runner)
    assert runner.client.prompts == [{"procedure": TEXT}]
    assert set(runner.roles[0][1]) == {"source", "plan"}
    assert runner.roles[1][1]["source"] == TEXT
    assert set(runner.roles[1][1]) == {"source", "equipment_catalog", "equipment_aliases"}
    serialized = json.dumps([runner.client.prompts, runner.roles])
    assert "ord_component" not in serialized and "ARGON" not in serialized
    assert result["protocol"]["reagents"][0]["smiles"] is None


def test_removing_or_poisoning_ord_fields_cannot_change_operations_hardware_or_xdl():
    raw = record()
    variants = [raw, text_source(raw), {**raw, "components": [], "setup": {"vessel": {"type": "WELL_PLATE"}},
                "conditions": {"flow": {"details": "poison"}}, "atmosphere": {"type": "NITROGEN"},
                "temperature": {"value": -100}, "duration": {"value": 100000},
                "yield_percent": None, "reaction_smiles": "poison"}]
    prepared = [finalize_protocol(prepare_protocol(build_ir(row, copy.deepcopy(PLAN), {}), row)) for row in variants]
    for field in ("steps", "reagents", "context", "hardware", "xdl", "canonical_sha1"):
        assert prepared[0][field] == prepared[1][field] == prepared[2][field]
    assert prepared[0]["hardware"]["nodes"]["reactor"]["params"]["capacity_mL"] == 5
    assert prepared[0]["crosscheck"] == prepared[1]["crosscheck"] == prepared[2]["crosscheck"]
    assert not prepared[0]["crosscheck"]["conflicts"]
    assert "inert_required" not in prepared[0]["context"]


def test_plain_text_needs_no_ord_metadata_or_outcome_to_produce_xdl():
    raw = {"id": "plain", "procedure": TEXT, "source": {"db": "TEXT", "url": "file:///experiment.txt"}}
    plan, _ = text_plan(raw, Client())
    prepared = prepare_protocol(build_ir(raw, plan, {}), raw)
    xml = finalize_protocol(prepared)["xdl"]
    assert "<Add " in xml and "<HeatChill " in xml
    assert prepared["quality"]["source_input_contract"] == "text-only/1"
    assert "yield_percent" not in prepared


def test_unknown_text_quantity_is_never_borrowed_from_ord():
    raw = record()
    raw["procedure"] = "Add water."
    plan = {"steps": [{"op": "Add", "reagent": "water", "evidence": "Add water."}]}
    protocol = build_ir(raw, plan, {})
    assert "amount" not in protocol["steps"][0]
    prepared = prepare_protocol(protocol, raw)
    assert prepared["steps"][0]["missing_parameters"]["amount"]["marker"] == "__NOT_REPORTED__"


def test_amount_cannot_be_borrowed_from_a_different_literal_reagent():
    raw = {"procedure": "Add water (1 mL) and ethanol (7 mL)."}
    plan = {"steps": [{"op": "Add", "reagent": "water", "alias": "water", "amount": {"value": 7, "unit": "mL"},
                       "evidence": raw["procedure"]}]}
    assert any("adjacent" in error for error in validate_evidence(raw, plan))


def test_base_extractor_keeps_independent_mass_and_molar_amount_without_another_agent():
    text = "Salt (18 mg, 1 mmol) was added to a vial."
    raw = {"id": "dual_amount", "procedure": text}
    plan = {"steps": [{"op": "Add", "reagent": "Salt", "amount": {"value": 18, "unit": "mg"}, "evidence": text}]}
    built = build_ir(raw, plan, {})
    assert {(q["value"], q["unit"]) for q in built["steps"][0]["source_quantities"]} == {(18, "mg"), (1, "mmol")}
    record = finalize_protocol(prepare_protocol(built, raw))
    assert 'mass="18 mg"' in record["xdl"] and 'amount="1 mmol"' in record["xdl"]


def test_explicit_source_label_does_not_allow_an_unrelated_reagents_quantity():
    text = "Add named reagent (X: 2 mg, 1 mmol) and water (3 mL)."
    plan = {"steps": [{"op": "Add", "reagent": "named reagent", "alias": "X", "evidence": text,
                       "amount": {"value": 2, "unit": "mg"}}]}
    assert not validate_evidence({"procedure": text}, plan)
    plan["steps"][0]["alias"] = "water"
    assert validate_evidence({"procedure": text}, plan)


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
