import copy

from protocol_risk.diversity import features, select_diverse, summarize


def sample(identifier, parent, source="source1", amount=1, reference="reagent"):
    return {"id": identifier, "parent_id": parent, "source": {"dataset_id": source},
            "label": {"evidence": [{"rule_id": "D3.undeclared_reference"}]},
            "diff": [{"op": "replace", "path": "/steps/0/" + reference, "value": amount}],
            "protocol": {"steps": [{"op": "Add"}], "hardware": {"nodes": {"reactor": {"apparatus_kind": "vial"}}}}}


def test_distinct_sources_and_fresh_parents_win_over_first_file_order():
    candidates = [sample("a", "p1"), sample("b", "p1"), sample("c", "p2"), sample("d", "p3", "source2")]
    chosen = select_diverse(candidates, 3)
    assert {s["parent_id"] for s in chosen} == {"p1", "p2", "p3"}
    assert {s["source"]["dataset_id"] for s in chosen} == {"source1", "source2"}
    assert chosen == select_diverse(list(reversed(candidates)), 3)


def test_numeric_variations_are_not_distinct_mechanisms():
    a, b = sample("a", "p1", amount=1), sample("b", "p2", amount=100)
    assert features(a)["mechanism"] == features(b)["mechanism"]
    b["diff"][0]["path"] = "/steps/0/vessel"
    assert features(a)["mechanism"] != features(b)["mechanism"]


def test_exhausted_diversity_is_reported_without_inventing_groups():
    candidates = [sample(str(i), "one-parent") for i in range(12)]
    original = copy.deepcopy(candidates)
    result = summarize(select_diverse(candidates, 10))
    assert result["parent"]["unique"] == 1 and result["mechanism"]["unique"] == 1
    assert result["reaction"]["missing"] == 10 and candidates == original
    assert "mechanism_has_one_observed_group" in result["limitations"]
