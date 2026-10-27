"""Independent evidence required before admitting hard or soft labels."""
def judge_admitted(report):
    required = ("C1", "C2", "C3", "C4", "C6")
    for risk in required:
        item = report.get("per_risk", {}).get(risk, {})
        metrics = item.get("test_metrics", {})
        if item.get("admitted") is not True:
            return False
        auc, ece, precision = (metrics.get(k) for k in ("auroc", "ece", "precision_at_p_ge_0_9"))
        if any(not isinstance(value, (int, float)) or isinstance(value, bool) for value in (auc, ece, precision)):
            return False
        if not (auc >= 0.80 and ece <= 0.05 and precision >= 0.85):
            return False
    return True

def hard_review_metrics(rows, eligible_ids):
    reviewed = {}
    for row in rows:
        correct = row.get("correct", "").strip().lower()
        if row.get("id") in eligible_ids and row.get("reviewer", "").strip() and correct in ("true", "false", "1", "0"):
            reviewed[row["id"]] = correct in ("true", "1")
    errors = sum(not good for good in reviewed.values())
    return {"count": len(reviewed), "errors": errors, "error_rate": errors / len(reviewed) if reviewed else None}
