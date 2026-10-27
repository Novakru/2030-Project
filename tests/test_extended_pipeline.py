"""Exercise the default text-to-extension-to-library-to-audit seam, without HTTP."""
import copy
import json
from pathlib import Path

from mosaic import BuildSpec, Runtime, build, resume
from mosaic.audit_bridge import publish
from mosaic.registry import Registry
from protocol_risk.extensions import read_extended_xdl
from protocol_risk.io import digest, read_json, read_jsonl


SOURCE = "Water was added to a 10 mL vial. The mixture was stirred overnight. The solid was dried under vacuum."
CORE = [{"op": "Add", "reagent": "Water", "alias": "Water", "evidence": "Water was added to a 10 mL vial."},
        {"op": "Stir", "evidence": "The mixture was stirred overnight."}]
DEFINITION = {"domain": "chemistry", "description": "Dry an isolated solid under a stated condition",
    "parameters": {"condition": {"type": "string", "required": True},
                   "duration_s": {"type": "number", "unit": "s", "required": True}},
    "effects": ["solvent_removed_from_solid"], "hardware_roles": ["vacuum_drying"]}
DRY = {"op": "Dry", "evidence": "The solid was dried under vacuum.", "stage": "workup", "parameters": {
    "condition": {"value": "vacuum", "evidence": "The solid was dried under vacuum."},
    "duration_s": {"status": "not_reported", "marker": "__NOT_REPORTED__", "raw": None,
                   "evidence": "The solid was dried under vacuum."}}}


class Client:
    def complete(self, system, prompt, cache=True):
        if system.startswith("Extract an entire"):
            data = {"steps": CORE, "unmapped_actions": [{"evidence": DRY["evidence"], "reason": "new drying semantics"}]}
        elif system.startswith("Complete a source-grounded"):
            assert "reference_only" not in prompt
            data = {"steps": CORE + [DRY], "definitions": {"Dry": DEFINITION}, "uncertainties": []}
        elif "independent source-fidelity critic" in system:
            data = {"findings": [], "patch": []}
        elif "apparatus-mapping specialist" in system:
            data = {"mentions": [], "unknowns": []}
        else:
            data = {"proposals": []}
        return {"data": copy.deepcopy(data), "model": "explicit-test-double"}


def test_default_pipeline_admits_new_atomic_expression_and_missing_source_parameters(tmp_path):
    raw = {"id": "extension_fixture", "procedure": SOURCE, "raw": {"text": SOURCE},
           "source": {"db": "TEXT", "url": "https://example.invalid/explicit-test-fixture"}}
    raw["raw_sha256"] = digest(raw["raw"])
    result = build(BuildSpec(output_dir=str(tmp_path / "runs"), positives=1, per_risk=0,
                            llm_perturbations=0, max_calls=10, workers=1),
                   runtime=Runtime(records=[raw], client_factory=lambda model: Client()))
    root = Path(result["run_dir"])
    protocol = list(read_jsonl(root / result["review_bundle"]["positives"]))[0]
    assert result["positives"] == 1 and result["failures"] == 0
    assert [step["op"] for step in protocol["steps"]] == ["Add", "Stir", "Dry"]
    assert protocol["quality"]["representation_complete"]
    assert not protocol["quality"]["parameters_complete"]
    assert not protocol["quality"]["execution_ready"]
    assert protocol["steps"][0]["missing_parameters"]["amount"]["marker"] == "__NOT_REPORTED__"
    assert protocol["steps"][1]["missing_parameters"]["duration_s"]["raw"] == "overnight"
    assert "__NOT_REPORTED__" in protocol["xdl"] and "__QUALITATIVE__" in protocol["xdl"]
    assert read_extended_xdl(protocol["xdl"])["steps"] == protocol["steps"]
    registry = Registry(read_json(root / result["library_registry"]))
    definition = next(iter(registry.snapshot["extension_operations"].values()))
    assert definition["name"] == "Dry" and definition["representation_status"] == "admitted"
    assert definition["execution_supported"] is False and definition["evidence"]
    assert publish(root, tmp_path / "reviews.sqlite3")["inserted"] == 1
    before = {p.name: p.read_bytes() for p in (root / Path(result["review_bundle"]["positives"]).parent).rglob("*") if p.is_file()}
    again = resume(root, offline=True)
    assert again["new_model_calls"] == 0
    after = {p.name: p.read_bytes() for p in (root / Path(result["review_bundle"]["positives"]).parent).rglob("*") if p.is_file()}
    assert before == after
    from mosaic.verification import verify_dataset
    checked = verify_dataset(root, upstream=False)
    assert checked["passed"], checked["issues"]
