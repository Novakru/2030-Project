import copy

from protocol_risk.admission import hard_review_metrics, judge_admitted


def test_global_low_yield_metrics_cannot_substitute_for_subclass_evidence():
    assert not judge_admitted({"admitted_as_judge": True, "test_metrics": {"auroc": 0.99, "ece": 0.01, "precision_at_p_ge_0_9": 0.99}})


def test_all_required_subclasses_must_meet_every_gate():
    report = {"per_risk": {r: {"admitted": True, "test_metrics": {"auroc": 0.8, "ece": 0.05, "precision_at_p_ge_0_9": 0.85}}
                           for r in ("C1", "C2", "C3", "C4", "C6")}}
    assert judge_admitted(report)
    bad = copy.deepcopy(report)
    bad["per_risk"]["C3"]["test_metrics"]["precision_at_p_ge_0_9"] = None
    assert not judge_admitted(bad)
    bad = copy.deepcopy(report)
    bad["per_risk"]["C4"]["test_metrics"]["ece"] = 0.06
    assert not judge_admitted(bad)


def test_control_reviews_and_duplicate_rows_do_not_satisfy_gold_hard_review_gate():
    rows = [{"id": "a", "reviewer": "person", "correct": "true"},
            {"id": "a", "reviewer": "person", "correct": "true"},
            {"id": "b", "reviewer": "person", "correct": "false"},
            {"id": "control", "reviewer": "person", "correct": "true"}]
    assert hard_review_metrics(rows, {"a", "b"}) == {"count": 2, "errors": 1, "error_rate": 0.5}
