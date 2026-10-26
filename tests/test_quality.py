from protocol_risk.quality import atomic_inventory


def test_mapped_ir_does_not_claim_complete_source_coverage_or_proven_minimality():
    snapshots = [{"id": "fixture", "steps": [{"op": "Add"}], "extraction": {
        "unmapped_actions": [{"evidence": "Adjust the pH to 7", "reason": "endpoint unrepresented"}]}}]
    report = atomic_inventory([{"steps": [{"op": "Add"}, {"op": "Atmosphere", "mode": "environment"}]}], snapshots)
    assert report["source_action_coverage"] is None and report["minimality_proven"] is False
    assert report["unmapped_snapshot_actions"] == 1
    assert report["operations"]["Atmosphere"]["context_only_steps"] == 1
    assert "target_pH" in report["macro_candidates"]["AdjustPH"]["parameters_without_primitive_field"]
    assert report["operations"]["Irradiate"]["reduction_status"] == "defer_removal_broader_source_coverage_needed"
