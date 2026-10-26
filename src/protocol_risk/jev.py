"""Leakage-controlled HTE low-yield baseline; it cannot admit per-risk judges."""
from __future__ import annotations

import json
import math

import numpy as np

from .conditions import chemical_key
from .ingest import read_raw
from .io import ROOT, canonical, write_json
from .pipeline import split_group
from .yields import POLICY as YIELD_POLICY

HTE_IDS = {
    "ord_dataset-46ff9a32d9e04016b9380b1b1ef949c3",  # Ahneman
    "ord_dataset-68cb8b4b2b384e3d85b5b1efae58b203",  # Suzuki HTE
    "ord_dataset-5c9a10329a8a48968d18879a48bb8ab2",  # Chan-Lam triplicates
}


def features(raw):
    output = {}
    if raw["temperature"]:
        output["temperature_scaled"] = raw["temperature"]["value"] / 100
    if raw["duration"]:
        output["log_duration_s"] = math.log1p(max(0, raw["duration"]["value"]))
    for c in raw["components"]:
        if c.get("amount") and c["amount"]["value"] == 0:
            continue
        key = c["role"] + ":" + chemical_key(c.get("smiles"), c["name"])
        output[key] = 1.0
        if c.get("amount"):
            q = c["amount"]
            output["log_amount:" + key + ":" + str(q["unit"])] = math.log1p(max(0, q["value"]))
    output["atmosphere:" + raw["atmosphere"].get("type", "UNKNOWN")] = 1.0
    return output


def metrics(y, probabilities):
    from sklearn.metrics import roc_auc_score
    predicted = probabilities >= 0.9
    ece, bins = 0.0, []
    for low in np.arange(0, 1, 0.1):
        mask = (probabilities >= low) & (probabilities <= low + 0.1 if low > 0.89 else probabilities < low + 0.1)
        if mask.any():
            confidence, frequency = float(probabilities[mask].mean()), float(y[mask].mean())
            ece += float(mask.mean()) * abs(confidence - frequency)
            bins.append({"p_mean": confidence, "observed_failure_rate": frequency, "count": int(mask.sum())})
    return {"n": len(y), "auroc": float(roc_auc_score(y, probabilities)) if len(set(y)) > 1 else None,
            "ece": ece, "precision_at_p_ge_0_9": float(y[predicted].mean()) if predicted.any() else None,
            "high_confidence_count": int(predicted.sum()), "reliability_bins": bins}


def train():
    import joblib
    import pyarrow as pa
    import pyarrow.parquet as pq
    from sklearn.feature_extraction import DictVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import StratifiedGroupKFold

    records, xs, labels, groups = [], [], [], []
    for raw in read_raw():
        if raw["source"]["dataset_id"] not in HTE_IDS or raw["yield_percent"] is None:
            continue
        value = raw["yield_percent"]
        if not (value < 5 or value > 30) or not raw.get("reaction_smiles"):
            continue
        feature = features(raw)
        group = split_group(raw)
        records.append({"id": raw["id"], "source_dataset_id": raw["source"]["dataset_id"],
                        "source_url": raw["source"]["url"], "raw_sha256": raw["raw_sha256"],
                        "reaction_smiles": raw["reaction_smiles"], "yield_percent": value,
                        "yield_evidence_json": canonical(raw["yield_evidence"]),
                        "label_type": "real", "observed_low_yield": value < 5,
                        "risk_l2": None, "causal_risk_attribution": "unavailable", "split_group": group,
                        "features_json": canonical(feature)})
        xs.append(feature)
        labels.append(int(value < 5))
        groups.append(group)
    y = np.array(labels)
    folds = list(StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=20261025).split(np.zeros(len(y)), y, groups))
    test_ids, val_ids = folds[0][1], folds[1][1]
    held = set(test_ids) | set(val_ids)
    train_ids = np.array([i for i in range(len(y)) if i not in held])
    group_sets = [set(groups[i] for i in ids) for ids in (train_ids, val_ids, test_ids)]
    if any(group_sets[i] & group_sets[j] for i in range(3) for j in range(i + 1, 3)):
        raise AssertionError("Scaffold split leakage")
    vectorizer = DictVectorizer()
    train_x = vectorizer.fit_transform([xs[i] for i in train_ids])
    val_x = vectorizer.transform([xs[i] for i in val_ids])
    test_x = vectorizer.transform([xs[i] for i in test_ids])
    model = LogisticRegression(max_iter=1500, C=0.25, random_state=20261025)
    model.fit(train_x, y[train_ids])
    calibrator = LogisticRegression(C=1.0, random_state=20261025)
    calibrator.fit(model.decision_function(val_x).reshape(-1, 1), y[val_ids])
    probability = calibrator.predict_proba(model.decision_function(test_x).reshape(-1, 1))[:, 1]
    test_metrics = metrics(y[test_ids], probability)
    for ids, split in ((train_ids, "train"), (val_ids, "val"), (test_ids, "test")):
        for index in ids:
            records[index]["split"] = split
    (ROOT / "data/hte").mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(records), ROOT / "data/hte/observations.parquet", compression="zstd")
    (ROOT / "models").mkdir(parents=True, exist_ok=True)
    joblib.dump({"vectorizer": vectorizer, "model": model, "calibrator": calibrator,
                 "target": "observed_yield_below_5_percent", "admitted_as_judge": False},
                ROOT / "models/hte_baseline.joblib")
    errors = []
    for index, p in zip(test_ids, probability):
        error = abs(int(y[index]) - float(p))
        errors.append({"id": records[index]["id"], "yield_percent": records[index]["yield_percent"],
                       "p_low_yield": float(p), "absolute_error": error})
    errors.sort(key=lambda row: row["absolute_error"], reverse=True)
    report = {"target": "observed_yield_below_5_percent", "observations": len(y),
              "yield_policy": YIELD_POLICY,
              "measured_failures": int(y.sum()), "measured_successes": int((1 - y).sum()),
              "scaffold_groups": len(set(groups)), "split": {"train": len(train_ids), "val": len(val_ids), "test": len(test_ids)},
              "test_metrics": test_metrics, "scaffold_leakage": False,
              "model": "DictVectorizer + LogisticRegression + validation-only Platt calibration",
              "admitted_as_judge": False,
              "per_risk": {risk: {"admitted": False, "reason": "HTE outcomes have no causal per-risk labels"}
                           for risk in ("C1", "C2", "C3", "C4", "C6")},
              "failure_cases": errors[:20],
              "limitations": ["No causal risk attribution; general low-yield metrics do not qualify a C-subclass judge.",
                              "No soft hypotheses or authored controls were used in this model.",
                              "Calibration and testing use different product-scaffold groups."]}
    write_json(ROOT / "reports/jev_metrics.json", report)
    _plot_reliability(test_metrics["reliability_bins"])
    return {k: report[k] for k in ("observations", "measured_failures", "scaffold_groups", "test_metrics", "admitted_as_judge")}


def _plot_reliability(bins):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(5, 4), layout="constrained")
    ax.plot([0, 1], [0, 1], "--", color="#888888", label="ideal")
    ax.plot([b["p_mean"] for b in bins], [b["observed_failure_rate"] for b in bins], "o-", color="#245c7a", label="held-out HTE")
    ax.set(xlabel="Predicted probability of yield <5%", ylabel="Observed frequency", xlim=(0, 1), ylim=(0, 1))
    ax.legend(frameon=False)
    fig.savefig(ROOT / "reports/hte_reliability.png", dpi=180)
    plt.close(fig)
