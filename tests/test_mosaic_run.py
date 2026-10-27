import json

from mosaic import BuildSpec, Runtime, build, resume
from mosaic.audit_bridge import publish
from mosaic.registry import Registry
from mosaic.store import RunStore
from protocol_risk.io import digest, read_json


class LiteralDomain:
    """A test-only domain proves the core does not require chemistry fields."""
    name = "fixture.wait/1"

    def registry(self):
        return Registry({"schema": "mosaic.registry/1", "devices": [], "operations": {"Wait": {}},
                         "macros": {}, "risks": {}, "observations": [], "operation_candidates": [], "aliases": {}, "changes": []})

    def library_paths(self):
        return []

    def extract(self, raw, runner, **options):
        return {"duration_s": raw["raw"]["duration_s"]}

    def validate(self, extracted, raw, run_id):
        return {"id": "fixture_positive", "raw_id": raw["id"], "raw_sha256": raw["raw_sha256"], "source": raw["source"],
                "steps": [{"id": "wait", "op": "Wait", "duration_s": extracted["duration_s"]}], "quality": {"tier": "silver"}}

    def mutate(self, parents, runner, **options):
        return [], {"coverage": {}, "rejected": {}}


def test_frozen_batch_replays_offline_and_is_actually_importable_in_audit(tmp_path):
    from audit import db

    raw = {"id": "authored_fixture", "raw": {"duration_s": 60},
           "source": {"db": "AUTHORED_CONTROL", "url": "https://example.invalid/test-fixture"}}
    raw["raw_sha256"] = digest(raw["raw"])
    spec = BuildSpec(output_dir=str(tmp_path / "runs"), domain=LiteralDomain.name,
                     positives=1, text_limit=0, llm_perturbations=0, max_calls=0)
    result = build(spec, runtime=Runtime(records=[raw], domain=LiteralDomain(), offline=True))
    manifest = read_json(result["run_dir"] + "/manifest.json")
    assert result["positives"] == 1 and result["risk_shortfalls"] == {}
    assert RunStore(result["run_dir"], manifest["request"]).verify()
    again = resume(result["run_dir"], offline=True, runtime=Runtime(domain=LiteralDomain()))
    assert again["run_id"] == result["run_id"] and again["model_calls"] == 0
    database = tmp_path / "audit.sqlite3"
    receipt = publish(result["run_dir"], database)
    assert receipt["inserted"] == 1 and receipt["statistics"]["pending"] == 1
    row = db.get_record(database, "fixture_positive")
    assert row["record_type"] == "positive"
    assert json.loads(row["raw_json"])["steps"][0]["duration_s"] == 60
    assert publish(result["run_dir"], database)["skipped"] == 1
