"""Graph-aware perturbations for building tasks (ordering, error detection, slot filling).

Because dependencies are explicit, every perturbation carries a correct label:
  * swap two steps -> "valid" only if neither must precede the other
  * swap receiver/added material -> always a semantic change ("role_reversal")
  * scale a quantity -> the literal in the text and the graph slot change together
  * drop a step -> lists which later steps lose their input
"""
from __future__ import annotations

import copy
import random
import re

from .ir import index, precedence_closure, step_refs, topological_order


def order_pairs(g):
    """All step pairs labelled must_precede / must_follow / independent."""
    closure = precedence_closure(g)
    ids = [s["id"] for s in g["steps"]]
    out = []
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            label = "must_precede" if (a, b) in closure else "must_follow" if (b, a) in closure else "independent"
            out.append({"a": a, "b": b, "label": label})
    return out


def swap_steps(g, a, b):
    """Return (new_graph, valid). Valid iff the new list order is still a topological order."""
    g2 = copy.deepcopy(g)
    pos = {s["id"]: i for i, s in enumerate(g2["steps"])}
    i, j = pos[a], pos[b]
    g2["steps"][i], g2["steps"][j] = g2["steps"][j], g2["steps"][i]
    closure = precedence_closure(g)
    new_pos = {s["id"]: k for k, s in enumerate(g2["steps"])}
    valid = all(new_pos[x] < new_pos[y] for x, y in closure)
    return g2, valid


def reverse_roles(g, step_id):
    """Swap target and the first input of an add-like step (a classic extraction error)."""
    g2 = copy.deepcopy(g)
    s = next(s for s in g2["steps"] if s["id"] == step_id)
    if not s["target"] or not s["inputs"]:
        raise ValueError("step needs both target and inputs")
    s["target"], s["inputs"][0]["ref"] = s["inputs"][0]["ref"], s["target"]
    return g2


def scale_quantity(text, prepared, qid, factor):
    """Return a perturbed text where one quantity literal is scaled; the Q id stays the same."""
    q = prepared.q[qid]
    if q.value is None:
        raise ValueError("quantity has no numeric value")
    new_value = q.value * factor
    literal = text[q.start:q.end]
    m = re.search(r"\d+(?:\.(\d+))?", literal)
    if m is None:
        raise ValueError("no numeric literal")
    decimals = len(m.group(1) or "")
    num = f"{new_value:.{decimals}f}" if decimals else f"{new_value:.4g}"
    new_literal = literal[:m.start()] + num + literal[m.end():]
    return text[:q.start] + new_literal + text[q.end:], {"q": qid, "from": literal, "to": new_literal}


def drop_step(g, step_id):
    """Remove a step; report downstream steps that lose an input (for 'missing step' tasks)."""
    g2 = copy.deepcopy(g)
    _, _, steps, producer, _ = index(g)
    outs = {o["id"] for o in steps[step_id]["outputs"]}
    broken = [s["id"] for s in g["steps"] if any(r in outs for _, r in step_refs(s))]
    g2["steps"] = [s for s in g2["steps"] if s["id"] != step_id]
    return g2, broken


def sample_tasks(g, prepared, n=10, seed=0):
    """A small mixed set of labelled task items from one graph."""
    rng = random.Random(seed)
    items = []
    pairs = order_pairs(g)
    rng.shuffle(pairs)
    for p in pairs[: n // 2]:
        items.append({"type": "order_pair", **p})
    adds = [s["id"] for s in g["steps"] if s["target"] and s["inputs"]]
    for sid in adds[:2]:
        items.append({"type": "role_reversal", "step": sid, "label": "invalid"})
    numeric = [q for q in prepared.procedure_quantities() if q.value]
    for q in rng.sample(numeric, min(len(numeric), max(1, n // 4))):
        _, change = scale_quantity(prepared.text, prepared, q.id, rng.choice([0.1, 2, 10]))
        items.append({"type": "quantity_error", **change})
    order = topological_order(g)
    items.append({"type": "reference_order", "order": order})
    return items
