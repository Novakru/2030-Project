"""Score a predicted ProcGraph against a gold ProcGraph of the same text.

Metrics (all in [0, 1]):
  material_f1      chemical identities found (fuzzy name/alias match)
  step_f1          operations found (aligned by op family + sentence + participants)
  op_acc           exact op label among aligned steps
  qty_binding      each tagged quantity attached to the right place (strict) / right step (loose)
  qty_coverage     fraction of procedure quantities bound at all
  role_acc         target (receiver) and inputs refer to the right material/state
  flow_f1          material-flow edges producer->consumer (the reaction graph itself)
  order_f1         precedence pairs implied by the graph (transitive), i.e. "B made before A added"
  overall          mean of material_f1, step_f1, qty_binding, role_acc, flow_f1, order_f1
"""
from __future__ import annotations

import re
from collections import defaultdict

from .ir import index, precedence_closure, step_refs

OP_FAMILIES = [
    {"add", "prepare", "dissolve", "suspend", "dilute", "transfer", "quench", "precipitate", "adjust_ph"},
    {"heat", "reflux", "react", "stir", "wait"},
    {"cool", "store", "wait"},
    {"filter", "collect", "centrifuge", "decant"},
    {"wash", "triturate", "suspend", "extract", "other"},
    {"concentrate", "distill", "lyophilize", "dry"},
    {"analyze", "monitor", "sample"},
    {"inert", "seal", "setup", "open", "other"},
    {"extract", "separate_phases"},
    {"chromatograph", "collect"},
]


def op_score(a, b):
    if a == b:
        return 1.0
    if any(a in f and b in f for f in OP_FAMILIES):
        return 0.6
    return 0.0


def _tokens(name):
    return {t for t in re.split(r"[^a-z0-9α-ω]+", name.lower()) if t and t not in {"of", "the", "a", "an", "dry", "in"}}


def name_score(a_names, b_names):
    best = 0.0
    for a in a_names:
        for b in b_names:
            an, bn = re.sub(r"\s+", " ", a.lower()).strip(), re.sub(r"\s+", " ", b.lower()).strip()
            if not an or not bn:
                continue
            if an == bn:
                return 1.0
            if (an in bn or bn in an) and min(len(an), len(bn)) >= 3:
                best = max(best, 0.85)
            ta, tb = _tokens(an), _tokens(bn)
            if ta and tb:
                best = max(best, len(ta & tb) / len(ta | tb))
    return best


def _greedy(pairs, threshold):
    pairs = sorted(pairs, key=lambda x: -x[0])
    used_a, used_b, out = set(), set(), {}
    for score, a, b in pairs:
        if score < threshold or a in used_a or b in used_b:
            continue
        used_a.add(a)
        used_b.add(b)
        out[a] = b
    return out


def prf(tp, n_pred, n_gold):
    p = tp / n_pred if n_pred else (1.0 if not n_gold else 0.0)
    r = tp / n_gold if n_gold else (1.0 if not n_pred else 0.0)
    f = 2 * p * r / (p + r) if p + r else 0.0
    return round(p, 4), round(r, 4), round(f, 4)


class Scorer:
    def __init__(self, gold_doc, pred_graph, pred_quantities):
        self.gold_doc = gold_doc
        self.g = gold_doc["graph"]
        self.p = pred_graph
        self.optional = {o.lower() for o in gold_doc.get("optional_materials", [])}
        gq = {q["id"]: (q["start"], q["end"]) for q in gold_doc["quantities"]}
        pq = {q["id"] if isinstance(q, dict) else q.id: ((q["start"], q["end"]) if isinstance(q, dict) else (q.start, q.end))
              for q in pred_quantities}
        span_to_gold = {v: k for k, v in gq.items()}
        self.qmap = {}
        for pid, span in pq.items():
            if span in span_to_gold:
                self.qmap[pid] = span_to_gold[span]
            else:
                for gid, (s, e) in gq.items():
                    if not (span[1] <= s or span[0] >= e):
                        self.qmap[pid] = gid
                        break

    # ------------------------------------------------------------------ materials
    def align_materials(self):
        gm = [m for m in self.g["materials"]]
        pm = [m for m in self.p["materials"]]
        pairs = []
        for a in pm:
            for b in gm:
                pairs.append((name_score([a["name"], *a["aliases"]], [b["name"], *b["aliases"]]), a["id"], b["id"]))
        self.mat = _greedy(pairs, 0.5)
        gold_count = [m for m in gm if m["name"].lower() not in self.optional]
        pred_count = [m for m in pm if m["id"] in self.mat or not any(
            name_score([m["name"], *m["aliases"]], [o]) >= 0.85 for o in self.optional)]
        tp = sum(1 for m in pred_count if m["id"] in self.mat
                 and next(g for g in gm if g["id"] == self.mat[m["id"]])["name"].lower() not in self.optional)
        return prf(tp, len(pred_count) - sum(1 for m in pred_count if m["id"] in self.mat and next(
            g for g in gm if g["id"] == self.mat[m["id"]])["name"].lower() in self.optional), len(gold_count))

    # ------------------------------------------------------------------ steps
    def _root_materials(self, graph, step):
        """Materials that flow into a step (directly or via upstream states)."""
        materials, _, steps, producer, _ = index(graph)
        seen, stack, out = set(), [r for _, r in step_refs(step)], set()
        while stack:
            r = stack.pop()
            if r in materials:
                out.add(r)
            elif r in producer and producer[r] not in seen:
                seen.add(producer[r])
                stack += [x for _, x in step_refs(steps[producer[r]])]
        return out

    def align_steps(self):
        gsteps, psteps = self.g["steps"], self.p["steps"]
        groot = {s["id"]: self._root_materials(self.g, s) for s in gsteps}
        proot = {s["id"]: {self.mat.get(m) for m in self._root_materials(self.p, s)} - {None} for s in psteps}
        gpos = {s["id"]: i / max(1, len(gsteps) - 1) for i, s in enumerate(gsteps)}
        ppos = {s["id"]: i / max(1, len(psteps) - 1) for i, s in enumerate(psteps)}
        gq = {s["id"]: self._step_qs(s, self.g, gold=True) for s in gsteps}
        pq = {s["id"]: self._step_qs(s, self.p, gold=False) for s in psteps}
        pairs = []
        for a in psteps:
            for b in gsteps:
                o = op_score(a["op"], b["op"])
                if o == 0:
                    continue
                sent = len(set(a["sentences"]) & set(b["sentences"])) > 0
                ra, rb = proot[a["id"]], groot[b["id"]]
                part = len(ra & rb) / len(ra | rb) if ra | rb else 0.5
                qa, qb = pq[a["id"]], gq[b["id"]]
                qs = len(qa & qb) / len(qa | qb) if qa | qb else 0.5
                pos = 1 - abs(ppos[a["id"]] - gpos[b["id"]])
                score = 0.35 * o + 0.2 * sent + 0.15 * part + 0.2 * qs + 0.1 * pos
                pairs.append((score, a["id"], b["id"]))
        self.st = _greedy(pairs, 0.5)
        return prf(len(self.st), len(psteps), len(gsteps))

    def _step_qs(self, s, graph, gold):
        qs = set()
        for x in s["inputs"]:
            qs |= set(x["amounts"])
        for v in s["params"].values():
            qs |= set(v.get("q", []))
        return qs if gold else {self.qmap.get(q) for q in qs} - {None}

    # ------------------------------------------------------------------ refs
    def _node(self, graph, ref, gold):
        materials, _, _, producer, _ = index(graph)
        if ref in materials:
            return ("mat", ref if gold else self.mat.get(ref))
        if ref in producer:
            return ("step", producer[ref] if gold else self.st.get(producer[ref]))
        return ("other", ref)

    def roles(self):
        gsteps = {s["id"]: s for s in self.g["steps"]}
        correct = total = 0
        details = []
        for p in self.p["steps"]:
            if p["id"] not in self.st:
                continue
            g = gsteps[self.st[p["id"]]]
            if g["target"]:
                total += 1
                ok = p["target"] is not None and self._node(self.p, p["target"], False) == self._node(self.g, g["target"], True)
                correct += ok
                if not ok:
                    details.append(f"{g['id']} target: gold {g['target']} pred {p['target']}")
            gin = {self._node(self.g, x["ref"], True) for x in g["inputs"]}
            if gin:
                pin = {self._node(self.p, x["ref"], False) for x in p["inputs"]}
                total += 1
                ok = len(gin & pin) / len(gin | pin) >= 0.99
                correct += ok
                if not ok:
                    details.append(f"{g['id']} inputs differ")
        return (round(correct / total, 4) if total else 1.0), details

    def flow(self):
        def flow_edges(graph, gold):
            out = set()
            _, _, _, producer, _ = index(graph)
            for s in graph["steps"]:
                for role, ref in step_refs(s):
                    if ref in producer:
                        a = producer[ref] if gold else self.st.get(producer[ref])
                        b = s["id"] if gold else self.st.get(s["id"])
                        out.add((a, b))
            return out
        g, p = flow_edges(self.g, True), flow_edges(self.p, False)
        p_valid = {e for e in p if None not in e}
        return prf(len(g & p_valid), len(p), len(g))

    def order(self):
        g = precedence_closure(self.g)
        p = {(self.st.get(a), self.st.get(b)) for a, b in precedence_closure(self.p)}
        aligned_gold = set(self.st.values())
        g_r = {(a, b) for a, b in g if a in aligned_gold and b in aligned_gold}
        p_r = {(a, b) for a, b in p if a and b}
        reversed_pairs = sum(1 for a, b in p_r if (b, a) in g_r)
        # Recall over ALL gold pairs: a missing preparation step loses its "made before use" pairs.
        return prf(len(g_r & p_r), len(p_r), len(g)), reversed_pairs

    # ------------------------------------------------------------------ quantities
    def _bindings(self, graph, gold):
        out = {}
        mapq = (lambda q: q) if gold else (lambda q: self.qmap.get(q))
        for s in graph["steps"]:
            sid = s["id"] if gold else self.st.get(s["id"])
            for x in s["inputs"]:
                node = self._node(graph, x["ref"], gold)
                for q in x["amounts"]:
                    out[mapq(q)] = ("input", sid, node)
            for name, v in s["params"].items():
                for q in v.get("q", []):
                    out[mapq(q)] = ("param", sid, name)
        for e in graph["equipment"]:
            for name, v in e["props"].items():
                for q in v.get("q", []):
                    out[mapq(q)] = ("equipment", None, None)
        for pr in graph["products"]:
            node = self._node(graph, pr["ref"], gold) if pr["ref"] else None
            for q in pr["amounts"]:
                out[mapq(q)] = ("product", None, node)
            for q in pr["yield"]:
                out[mapq(q)] = ("yield", None, node)
        for ob in graph["observations"]:
            for q in ob["quantities"]:
                out.setdefault(mapq(q), ("observation", None, None))
        for u in graph["unbound"]:
            out.setdefault(mapq(u["q"]), ("unbound", None, None))
        out.pop(None, None)
        return out

    def quantities(self):
        g, p = self._bindings(self.g, True), self._bindings(self.p, False)
        strict = loose = 0
        wrong = []
        for q, gb in g.items():
            pb = p.get(q)
            if pb is None:
                wrong.append(f"{q}: missing (gold {gb[0]})")
                continue
            if gb[0] in ("product", "yield"):
                ok_strict = pb[0] == gb[0] and (pb[2] == gb[2] or gb[2] is None)
                ok_loose = pb[0] in ("product", "yield", "observation")
            elif gb[0] in ("observation", "unbound", "equipment"):
                ok_strict = ok_loose = pb[0] in ("observation", "unbound", "equipment")
            else:
                ok_loose = pb[0] in ("input", "param") and pb[1] == gb[1]
                ok_strict = pb == gb
            strict += ok_strict
            loose += ok_loose
            if not ok_strict:
                wrong.append(f"{q}: gold {gb} pred {pb}")
        n = len(g) or 1
        bound = [q for q, b in p.items() if b[0] != "unbound"]
        gold_bound = [q for q, b in g.items() if b[0] != "unbound"]
        cov = len(set(bound) & set(gold_bound)) / (len(gold_bound) or 1)
        return round(strict / n, 4), round(loose / n, 4), round(cov, 4), wrong

    def run(self):
        mp, mr, mf = self.align_materials()
        sp, sr, sf = self.align_steps()
        gsteps = {s["id"]: s for s in self.g["steps"]}
        op_acc = (sum(gsteps[g]["op"] == next(s for s in self.p["steps"] if s["id"] == p)["op"] for p, g in self.st.items())
                  / len(self.st)) if self.st else 0.0
        role_acc, role_details = self.roles()
        fp, fr, ff = self.flow()
        (op_, or_, of), reversed_pairs = self.order()
        qs, ql, qc, qwrong = self.quantities()
        overall = (mf + sf + qs + role_acc + ff + of) / 6
        return {
            "material_p": mp, "material_r": mr, "material_f1": mf,
            "step_p": sp, "step_r": sr, "step_f1": sf, "op_acc": round(op_acc, 4),
            "qty_binding": qs, "qty_binding_loose": ql, "qty_coverage": qc,
            "role_acc": role_acc, "flow_p": fp, "flow_r": fr, "flow_f1": ff,
            "order_p": op_, "order_r": or_, "order_f1": of, "order_reversed_pairs": reversed_pairs,
            "overall": round(overall, 4),
            "errors": {"quantities": qwrong[:30], "roles": role_details[:30]},
        }


METRIC_KEYS = ["material_f1", "step_f1", "op_acc", "qty_binding", "qty_binding_loose", "qty_coverage", "role_acc",
               "flow_f1", "order_f1", "overall"]


def score(gold_doc, pred_graph, pred_quantities):
    return Scorer(gold_doc, pred_graph, pred_quantities).run()


def aggregate(results):
    agg = defaultdict(list)
    for r in results.values():
        if r is None:
            for k in METRIC_KEYS:
                agg[k].append(0.0)
            continue
        for k in METRIC_KEYS:
            agg[k].append(r[k])
    return {k: round(sum(v) / len(v), 4) for k, v in agg.items() if v}
