"""Select a source-supported target yield without maximizing across products."""
from __future__ import annotations

import math

POLICY = "unique_target_unique_percentage_v1"


def target_yield(raw):
    products = [(f"/outcomes/{oi}/products/{pi}", product)
                for oi, outcome in enumerate(raw.get("outcomes", []))
                for pi, product in enumerate(outcome.get("products", []))
                if product.get("reaction_role") in ("PRODUCT", None)]
    explicit = [(path, product) for path, product in products if product.get("is_desired_product") is True]
    candidates = explicit or [(path, product) for path, product in products
                              if product.get("is_desired_product") is not False]
    evidence = {"policy": POLICY, "target_count": len(candidates),
                "selection": "explicit_desired_product" if explicit else "sole_nonexcluded_product",
                "status": "ambiguous_target" if len(candidates) > 1 else "missing_target",
                "measurements": []}
    if len(candidates) != 1:
        return None, evidence
    path, product = candidates[0]
    evidence["target_source_path"] = path
    invalid = False
    for index, measurement in enumerate(product.get("measurements", [])):
        if measurement.get("type") != "YIELD" or "percentage" not in measurement:
            continue
        value = measurement["percentage"].get("value")
        valid = (isinstance(value, (int, float)) and not isinstance(value, bool)
                 and math.isfinite(value) and 0 <= value <= 100)
        invalid |= not valid
        evidence["measurements"].append({"source_path": path + f"/measurements/{index}",
                                         "percentage": value, "valid": valid,
                                         "analysis_key": measurement.get("analysis_key")})
    values = {m["percentage"] for m in evidence["measurements"] if m["valid"]}
    if invalid:
        evidence["status"] = "invalid_percentage"
    elif not values:
        evidence["status"] = "missing_percentage"
    elif len(values) > 1:
        evidence["status"] = "conflicting_measurements"
    else:
        evidence["status"] = "selected"
        return float(next(iter(values))), evidence
    return None, evidence
