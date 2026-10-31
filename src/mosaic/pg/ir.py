"""ProcGraph IR (``mosaic.procgraph/1``): coercion, validation and graph algorithms.

Representation in one paragraph
-------------------------------
*materials* are chemical identities; *equipment* are vessels/instruments.
*steps* are operations with typed roles: ``target`` (the thing acted on / the
receiver), ``inputs`` (what is introduced, each with bound quantity IDs),
``params`` (conditions bound to quantity IDs or qualitative text) and
``outputs`` (new state IDs, e.g. ``solid``/``filtrate``). A step input or target
may reference a material (fresh from the bottle) or a *state* produced by an
earlier step. These state references ARE the reaction graph: "A added to a
suspension of C and D" becomes ``prepare(C, D) -> x1`` and ``add(target=x1,
inputs=[A]) -> x2``, so x1 must be made first. Described mixtures that the text
never says were prepared get ``origin="described"``; nothing is invented.
"""
from __future__ import annotations

import copy
import difflib
import re
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

import yaml

SCHEMA = "mosaic.procgraph/1"
OPS_PATH = Path(__file__).with_name("ops.yaml")
AMOUNT_KINDS = {"mass", "volume", "amount", "equivalents", "relative_loading", "percent", "concentration",
                "mass_concentration", "relative_volume", "count"}


@lru_cache(maxsize=4)
def load_ops(extra_path=None):
    data = yaml.safe_load(OPS_PATH.read_text(encoding="utf-8"))
    if extra_path and Path(extra_path).exists():
        extra = yaml.safe_load(Path(extra_path).read_text(encoding="utf-8")) or {}
        data["ops"].update(extra.get("ops", {}))
        for name, kinds in extra.get("param_kinds", {}).items():
            data["param_kinds"][name] = kinds
    alias = {}
    for name, spec in data["ops"].items():
        alias[name] = name
        for a in spec.get("aliases", []) or []:
            alias.setdefault(_norm_op(a), name)
    data["alias"] = alias
    return data


def _norm_op(text):
    return re.sub(r"[\s\-]+", "_", str(text).strip().lower())


def _lemmas(word):
    """Cheap verb lemmatizer for op names: stirring/stirred -> stir, dissolving -> dissolve, charged -> charge."""
    w = word
    out = [w]
    for suf in ("ing", "ed", "es", "s"):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            stem = w[: -len(suf)]
            out += [stem, stem + "e"]
            if len(stem) > 3 and stem[-1] == stem[-2]:
                out.append(stem[:-1])
            if stem.endswith("i"):
                out.append(stem[:-1] + "y")
    return out


def _lookup_op(raw, ops):
    key = _norm_op(raw)
    if key in ops["alias"]:
        return ops["alias"][key]
    for cand in _lemmas(key):
        if cand in ops["alias"]:
            return ops["alias"][cand]
    head = key.split("_")[0]
    for cand in _lemmas(head):
        if cand in ops["alias"]:
            return ops["alias"][cand]
    return None


def _norm_name(text):
    text = str(text).lower()
    text = re.sub(r"[\s\u00a0]+", " ", text)
    return text.strip(" .,;:")


# ----------------------------------------------------------------------------- coercion
class Coercer:
    """Normalize a model reply into canonical shape. Every change is logged, never silent."""

    def __init__(self, prepared, ops=None):
        self.p = prepared
        self.ops = ops or load_ops()
        self.log = []

    def note(self, code, msg):
        self.log.append({"code": code, "message": msg})

    def run(self, raw):
        g = copy.deepcopy(raw) if isinstance(raw, dict) else {}
        for wrapper in ("graph", "procgraph", "result", "output"):
            if wrapper in g and isinstance(g[wrapper], dict) and "steps" in g[wrapper]:
                g = g[wrapper]
                self.note("C_UNWRAP", f"unwrapped '{wrapper}'")
        def items(key, fn, allow_str=True):
            out_items = []
            for i, x in enumerate(_as_list(g.get(key))):
                if isinstance(x, str) and allow_str or isinstance(x, dict):
                    out_items.append(fn(x, i) if fn.__code__.co_argcount == 3 else fn(x))
                elif x is not None:
                    self.note("C_DROPPED", f"{key}[{i}] has type {type(x).__name__}; dropped")
            return out_items

        out = {
            "schema": SCHEMA, "source_id": self.p.source_id, "text_sha256": self.p.sha256,
            "materials": items("materials", self._material),
            "equipment": items("equipment", self._equipment),
        }
        out["steps"] = items("steps", self._step, allow_str=False)
        out["products"] = items("products", self._product)
        out["observations"] = items("observations", self._observation)
        if "unbound" not in g and "unbound_quantities" in g:
            g["unbound"] = g["unbound_quantities"]
        out["unbound"] = items("unbound", self._unbound)
        self._dedupe_ids(out)
        self._resolve_refs(out)
        self._auto_fix(out)
        return out

    # ---- deterministic repairs (cheaper and safer than another LLM round)
    def _auto_fix(self, g):
        materials = {m["id"] for m in g["materials"]}
        equipment = {e["id"] for e in g["equipment"]}
        valid_sents = set(self.p.s)
        new_steps = []
        for s in g["steps"]:
            spec = self.ops["ops"].get(s["op"], self.ops["ops"]["other"])
            s["sentences"] = [x for x in s["sentences"] if x in valid_sents]
            s["inputs"] = [x for x in s["inputs"] if x["ref"]]
            for x in list(s["inputs"]):
                if x["ref"] in equipment:
                    s["inputs"].remove(x)
                    s["equipment"].append(x["ref"])
                    self.note("C_EQUIPMENT_INPUT", f"{s['id']}: equipment {x['ref']} moved from inputs")
            if s["target"] and any(x["ref"] == s["target"] for x in s["inputs"]):
                s["inputs"] = [x for x in s["inputs"] if x["ref"] != s["target"]]
                self.note("C_TARGET_IN_INPUTS", f"{s['id']}: target removed from inputs")
            if spec["target"] == "none" and s["target"]:
                s["inputs"].insert(0, {"ref": s["target"], "amounts": [], "role": "", "note": ""})
                s["target"] = None
                self.note("C_TARGET_TO_INPUT", f"{s['id']}: {s['op']} takes no target; moved to inputs")
            if spec["inputs"] == "none" and s["inputs"] and s["op"] != "other":
                # "stirred with X" -> add X, then stir the result
                add_out = s["id"] + "_mix"
                add = {**{k: v for k, v in s.items()}, "id": s["id"] + "_add", "op": "add", "op_label": "",
                       "inputs": s["inputs"], "params": {}, "outputs": [{"id": add_out, "role": "main", "label": ""}],
                       "concurrent_with": None, "after": []}
                new_steps.append(add)
                s["inputs"], s["target"] = [], add_out
                self.note("C_SPLIT_INPUTS", f"{s['id']}: {s['op']} takes no inputs; split into add + {s['op']}")
            self._fix_param_kinds(s)
            new_steps.append(s)
        g["steps"] = new_steps
        self._literals_to_text(g)
        self._reorder(g)

    def _fix_param_kinds(self, s):
        kinds = self.ops["param_kinds"]
        Q = self.p.q
        canonical = {"temperature": "temperature", "time": "duration", "rotation_speed": "stir_speed",
                     "pressure": "pressure", "count": "repeat"}
        for name in list(s["params"]):
            v = s["params"][name]
            qs = [q for q in v.get("q", []) if q in Q]
            allowed = kinds.get(name)
            if not qs or not allowed or all(Q[q].kind in allowed for q in qs):
                continue
            kind = Q[qs[0]].kind
            target = canonical.get(kind)
            if target and target not in s["params"] and all(Q[q].kind == kind for q in qs):
                s["params"][target] = s["params"].pop(name)
                self.note("C_PARAM_RENAMED", f"{s['id']}: {name} holds a {kind}; renamed to {target}")

    def _literals_to_text(self, g):
        for s in g["steps"]:
            for name, v in s["params"].items():
                lits = [q for q in v.get("q", []) if q.startswith("LIT:")]
                if lits:
                    v["q"] = [q for q in v["q"] if not q.startswith("LIT:")]
                    v["text"] = "; ".join([v.get("text", "")] * bool(v.get("text")) + [q[4:] for q in lits])
                    if not v["q"]:
                        v.pop("q")
                    self.note("C_LITERAL_TEXT", f"{s['id']}.{name}: untagged literal kept as text")
            for x in s["inputs"]:
                lits = [q for q in x["amounts"] if q.startswith("LIT:")]
                if lits:
                    x["amounts"] = [q for q in x["amounts"] if not q.startswith("LIT:")]
                    x["note"] = (x["note"] + " " if x["note"] else "") + "; ".join(q[4:] for q in lits)
                    self.note("C_LITERAL_TEXT", f"{s['id']}: untagged amount kept as note")
        for part in ("products",):
            for p in g[part]:
                for key in ("amounts", "yield"):
                    p[key] = [q for q in p[key] if not q.startswith("LIT:")]
        for o in g["observations"]:
            o["quantities"] = [q for q in o["quantities"] if not q.startswith("LIT:")]

    def _reorder(self, g):
        """If a state is used before it is produced, apply a stable topological order of the data flow."""
        producer = {o["id"]: s["id"] for s in g["steps"] for o in s["outputs"]}
        pos = {s["id"]: i for i, s in enumerate(g["steps"])}
        late = any(producer.get(r) is not None and pos[producer[r]] > pos[s["id"]]
                   for s in g["steps"] for _, r in step_refs(s))
        if not late:
            return
        preds = {s["id"]: {producer[r] for _, r in step_refs(s) if r in producer and producer[r] != s["id"]}
                 for s in g["steps"]}
        done, order, steps = set(), [], {s["id"]: s for s in g["steps"]}
        while len(order) < len(steps):
            ready = [sid for sid in pos if sid not in done and preds[sid] <= done]
            if not ready:
                return  # a real cycle: leave it for the validator
            nxt = min(ready, key=pos.get)
            done.add(nxt)
            order.append(steps[nxt])
        g["steps"] = order
        self.note("C_REORDER", "steps reordered so every state is produced before use")

    # ---- primitives
    def _qids(self, value, sentences=()):
        """Accept "Q3", ["Q3","Q4"], "Q3|25.4 g", {"q": ...} or a literal like "25.4 g"."""
        if value is None:
            return []
        if isinstance(value, dict):
            value = value.get("q", value.get("qs", value.get("quantity", value.get("id"))))
        items = value if isinstance(value, list) else [value]
        result = []
        for item in items:
            if isinstance(item, dict):
                result += self._qids(item, sentences)
                continue
            s = str(item).strip()
            m = re.match(r"^«?\s*(Q\d+)\b", s)
            if m:
                result.append(m.group(1))
                continue
            hit = self._find_literal(s, sentences)
            if hit:
                self.note("C_Q_LITERAL", f"literal {s!r} mapped to {hit}")
                result.append(hit)
            else:
                result.append("LIT:" + s)
        return result

    def _find_literal(self, literal, sentences):
        literal_n = re.sub(r"\s+", "", literal.lower())
        candidates = [q for q in self.p.quantities if not sentences or q.sentence in sentences] or self.p.quantities
        for q in candidates:
            if re.sub(r"\s+", "", q.text.lower()).rstrip(".") == literal_n.rstrip("."):
                return q.id
        return None

    def _sentences(self, value):
        items = value if isinstance(value, list) else ([value] if value else [])
        out = []
        for v in items:
            m = re.match(r"^\[?(S\d+)\]?$", str(v).strip())
            if m:
                out.append(m.group(1))
        return out

    def _value(self, v, sentences):
        if isinstance(v, dict):
            if "q" in v or "qs" in v or "quantity" in v:
                qs = self._qids(v, sentences)
                out = {"q": qs}
                if v.get("text"):
                    out["text"] = str(v["text"])
                return out
            if "text" in v:
                return {"text": str(v["text"])}
            if "value" in v:
                return self._value(v["value"], sentences)
            return {"text": str(v)}
        if isinstance(v, list):
            if all(isinstance(x, str) and re.match(r"^Q\d+", x) for x in v):
                return {"q": self._qids(v, sentences)}
            return {"text": ", ".join(map(str, v))}
        if isinstance(v, bool):
            return {"text": "yes" if v else "no"}
        s = str(v).strip()
        if re.match(r"^«?Q\d+", s):
            return {"q": self._qids(s, sentences)}
        hit = self._find_literal(s, sentences)
        if hit:
            self.note("C_Q_LITERAL", f"param literal {s!r} mapped to {hit}")
            return {"q": [hit]}
        return {"text": s}

    def _material(self, m, i):
        if isinstance(m, str):
            m = {"name": m}
        return {
            "id": str(m.get("id") or f"m{i + 1}"),
            "name": str(m.get("name") or m.get("label") or "").strip(),
            "aliases": [str(a) for a in _as_list(m.get("aliases"))],
            "kind": m.get("kind") if m.get("kind") in ("substance", "mixture", "unknown") else "substance",
            "sentences": self._sentences(m.get("sentences", m.get("sentence", m.get("sent")))),
        }

    def _equipment(self, e, i):
        if isinstance(e, str):
            e = {"name": e}
        props = {}
        for k, v in (e.get("props") or {}).items() if isinstance(e.get("props"), dict) else []:
            props[k] = self._value(v, ())
        for item in e.get("props") if isinstance(e.get("props"), list) else []:
            if isinstance(item, dict) and item.get("attr"):
                props[item["attr"]] = self._value(item, ())
        return {
            "id": str(e.get("id") or f"e{i + 1}"),
            "name": str(e.get("name") or "").strip(),
            "type": e.get("type") if e.get("type") in ("vessel", "instrument", "tool", "consumable", "location") else "tool",
            "props": props,
            "sentences": self._sentences(e.get("sentences", e.get("sentence", e.get("sent")))),
        }

    def _step(self, s, i):
        sentences = self._sentences(s.get("sentences", s.get("sentence", s.get("sent"))))
        op_raw = str(s.get("op") or s.get("operation") or "other")
        op = _lookup_op(op_raw, self.ops)
        op_label = s.get("op_label")
        if op is None:
            close = difflib.get_close_matches(_norm_op(op_raw), list(self.ops["ops"]), n=1, cutoff=0.85)
            if close:
                op = close[0]
                self.note("C_OP_FUZZY", f"op {op_raw!r} -> {op}")
            else:
                op, op_label = "other", op_label or str(op_raw)
                self.note("C_OP_OTHER", f"op {op_raw!r} not in library -> other")
        outputs = []
        for o in _as_list(s.get("outputs", s.get("output"))):
            if isinstance(o, str):
                outputs.append({"id": o, "role": "main", "label": ""})
            elif isinstance(o, dict) and o.get("id"):
                outputs.append({"id": str(o["id"]), "role": str(o.get("role") or "main"), "label": str(o.get("label") or "")})
        inputs = []
        for x in _as_list(s.get("inputs")):
            if isinstance(x, str):
                x = {"ref": x}
            if not isinstance(x, dict):
                continue
            inputs.append({
                "ref": str(x.get("ref") or x.get("material") or x.get("id") or x.get("name") or ""),
                "amounts": self._qids(x.get("amounts", x.get("amount", x.get("q"))), sentences),
                "role": str(x.get("role") or ""),
                "note": str(x.get("note") or ""),
            })
        params = {}
        raw_params = s.get("params") or {}
        if isinstance(raw_params, list):
            raw_params = {p.get("name") or p.get("attr"): p for p in raw_params if isinstance(p, dict)}
        if not isinstance(raw_params, dict):
            raw_params = {}
        for k, v in raw_params.items():
            if k is None or v is None or v == "" or v == [] or v == {}:
                continue
            params[_norm_op(k)] = self._value(v, sentences)
        target = s.get("target")
        if isinstance(target, dict):
            target = target.get("ref") or target.get("state") or target.get("id")
        if isinstance(target, list):
            target = target[0] if target else None
        return {
            "id": str(s.get("id") or f"t{i + 1}"),
            "op": op, "op_label": str(op_label) if op_label else "",
            "origin": "described" if s.get("origin") in ("described", "implied", "described_mixture") else "action",
            "sentences": sentences,
            "surface": str(s.get("surface") or ""),
            "target": str(target) if target else None,
            "inputs": inputs, "params": params,
            "vessel": str(s["vessel"]) if s.get("vessel") else None,
            "equipment": [str(e) for e in _as_list(s.get("equipment"))],
            "outputs": outputs,
            "concurrent_with": str(s["concurrent_with"]) if s.get("concurrent_with") else None,
            "after": [str(a) for a in _as_list(s.get("after"))],
        }

    def _product(self, x):
        if isinstance(x, str):
            x = {"ref": x}
        sentences = self._sentences(x.get("sentences", x.get("sentence")))
        return {
            "ref": str(x.get("ref") or x.get("material") or ""),
            "state": str(x["state"]) if x.get("state") else None,
            "amounts": self._qids(x.get("amounts", x.get("amount")), sentences),
            "yield": self._qids(x.get("yield"), sentences),
            "form": str(x.get("form") or ""),
            "sentences": sentences,
        }

    def _observation(self, x):
        if isinstance(x, str):
            x = {"text": x}
        sentences = self._sentences(x.get("sentences", x.get("sentence")))
        return {"sentences": sentences, "text": str(x.get("text") or ""), "step": str(x["step"]) if x.get("step") else None,
                "quantities": self._qids(x.get("quantities", x.get("q")), sentences)}

    def _unbound(self, x):
        if isinstance(x, str):
            x = {"q": x}
        q = self._qids(x.get("q"))
        return {"q": q[0] if q else "", "reason": str(x.get("reason") or "")}

    # ---- graph-level fixes
    def _dedupe_ids(self, g):
        seen = set()
        for m in g["materials"]:
            m["id"] = self._fresh(m["id"], seen)
        for e in g["equipment"]:
            e["id"] = self._fresh(e["id"], seen)
        for s in g["steps"]:
            s["id"] = self._fresh(s["id"], seen)
        for s in g["steps"]:
            for o in s["outputs"]:
                new = self._fresh(o["id"], seen)
                if new != o["id"]:
                    self.note("C_STATE_RENAMED", f"state {o['id']} produced twice; second renamed {new}")
                    self._rename_after(g, s, o["id"], new)
                    o["id"] = new

    def _fresh(self, ident, seen):
        ident = re.sub(r"[^A-Za-z0-9_\-]", "_", ident) or "x"
        if ident not in seen:
            seen.add(ident)
            return ident
        k = 2
        while f"{ident}_{k}" in seen:
            k += 1
        seen.add(f"{ident}_{k}")
        return f"{ident}_{k}"

    def _rename_after(self, g, step, old, new):
        later = False
        for s in g["steps"]:
            if s is step:
                later = True
                continue
            if later:
                if s["target"] == old:
                    s["target"] = new
                for x in s["inputs"]:
                    if x["ref"] == old:
                        x["ref"] = new

    def _resolve_refs(self, g):
        """Map name-like refs to IDs (exact name/alias/label match only)."""
        ids = {m["id"] for m in g["materials"]} | {o["id"] for s in g["steps"] for o in s["outputs"]} | {e["id"] for e in g["equipment"]}
        by_name = {}
        for m in g["materials"]:
            for n in [m["name"], *m["aliases"]]:
                by_name.setdefault(_norm_name(n), m["id"])
        for s in g["steps"]:
            for o in s["outputs"]:
                if o["label"]:
                    by_name.setdefault(_norm_name(o["label"]), o["id"])
        eq_name = {_norm_name(e["name"]): e["id"] for e in g["equipment"]}

        text_l = self.p.text.lower()

        def fix(ref):
            if not ref or ref in ids:
                return ref
            hit = by_name.get(_norm_name(ref)) or eq_name.get(_norm_name(ref))
            if hit:
                self.note("C_REF_BY_NAME", f"ref {ref!r} resolved to {hit}")
                return hit
            # A name that appears in the text but was not declared: register it as a material.
            if not re.fullmatch(r"[a-z]{1,2}\d+(?:_\d+)?", ref) and len(ref) >= 2 and _norm_name(ref) in text_l:
                new = self._fresh("m_" + re.sub(r"\W+", "_", ref.lower())[:30], ids)
                g["materials"].append({"id": new, "name": ref, "aliases": [], "kind": "substance", "sentences": []})
                by_name[_norm_name(ref)] = new
                self.note("C_MATERIAL_ADDED", f"undeclared material {ref!r} registered as {new}")
                return new
            return ref

        for s in g["steps"]:
            s["target"] = fix(s["target"])
            for x in s["inputs"]:
                x["ref"] = fix(x["ref"])
            if s["vessel"] and s["vessel"] not in ids:
                s["vessel"] = eq_name.get(_norm_name(s["vessel"]), s["vessel"])
            s["equipment"] = [eq_name.get(_norm_name(e), e) if e not in ids else e for e in s["equipment"]]
        for p in g["products"]:
            p["ref"] = fix(p["ref"])


def _as_list(v):
    if v is None or v == "":
        return []
    return v if isinstance(v, list) else [v]


def _dict(v):
    return v if isinstance(v, dict) else {}


def coerce(raw, prepared, ops=None):
    c = Coercer(prepared, ops)
    return c.run(raw), c.log


# ----------------------------------------------------------------------------- graph
def index(g):
    materials = {m["id"]: m for m in g["materials"]}
    equipment = {e["id"]: e for e in g["equipment"]}
    steps = {s["id"]: s for s in g["steps"]}
    producer, state_out = {}, {}
    for s in g["steps"]:
        for o in s["outputs"]:
            producer.setdefault(o["id"], s["id"])
            state_out[o["id"]] = o
    return materials, equipment, steps, producer, state_out


def step_refs(step):
    refs = []
    if step["target"]:
        refs.append(("target", step["target"]))
    refs += [("input", x["ref"]) for x in step["inputs"]]
    return refs


def edges(g):
    """Typed precedence edges (a -> b means a must happen before b)."""
    _, _, steps, producer, _ = index(g)
    out = set()
    for s in g["steps"]:
        for role, ref in step_refs(s):
            if ref in producer and producer[ref] != s["id"]:
                out.add((producer[ref], s["id"], "flow:" + role))
        for a in s["after"]:
            if a in steps and a != s["id"]:
                out.add((a, s["id"], "after"))
    # Steps with no material link at all (e.g. "the plate was sealed" with no target) are
    # chained to their predecessor in list order, conservatively.
    linked = {a for a, b, _ in out} | {b for a, b, _ in out}
    order = [s["id"] for s in g["steps"]]
    for i, sid in enumerate(order[1:], 1):
        s = steps[sid]
        if sid not in linked and not s["target"] and not s["inputs"] and not s["concurrent_with"]:
            out.add((order[i - 1], sid, "sequence"))
    return sorted(out)


def precedence_closure(g, kinds=None):
    succ = defaultdict(set)
    for a, b, k in edges(g):
        if kinds is None or k.split(":")[0] in kinds:
            succ[a].add(b)
    closure = set()
    for start in [s["id"] for s in g["steps"]]:
        stack, seen = list(succ[start]), set()
        while stack:
            n = stack.pop()
            if n in seen:
                continue
            seen.add(n)
            closure.add((start, n))
            stack.extend(succ[n])
    return closure


def topological_order(g):
    """Stable topological order (list order among unconstrained steps). Raises on cycles."""
    order = [s["id"] for s in g["steps"]]
    pos = {sid: i for i, sid in enumerate(order)}
    preds = defaultdict(set)
    for a, b, _ in edges(g):
        preds[b].add(a)
    done, result = set(), []
    while len(result) < len(order):
        ready = [sid for sid in order if sid not in done and preds[sid] <= done]
        if not ready:
            cyc = [sid for sid in order if sid not in done]
            raise ValueError("cycle among steps: " + ", ".join(cyc))
        nxt = min(ready, key=pos.get)
        done.add(nxt)
        result.append(nxt)
    return result


def lineage(g, state_id):
    """All steps and materials upstream of a state."""
    materials, _, steps, producer, _ = index(g)
    seen_steps, seen_mat, stack = set(), set(), [state_id]
    while stack:
        ref = stack.pop()
        if ref in materials:
            seen_mat.add(ref)
            continue
        sid = producer.get(ref)
        if not sid or sid in seen_steps:
            continue
        seen_steps.add(sid)
        stack += [r for _, r in step_refs(steps[sid])]
    return seen_steps, seen_mat


# ----------------------------------------------------------------------------- validation
# Codes that only mean "not every quantity is placed perfectly": the graph is still usable.
SOFT_CODES = {"E_Q_UNBOUND", "E_Q_KIND", "E_Q_DUP", "E_Q_LITERAL"}


def status_of(errors):
    if not errors:
        return "ok"
    return "incomplete" if all(e["code"] in SOFT_CODES for e in errors) else "has_errors"


def validate(g, prepared, ops=None):
    """Return (errors, warnings). Errors are blocking and are sent to the repair agent."""
    ops = ops or load_ops()
    errors, warnings = [], []
    E = lambda code, where, msg: errors.append({"code": code, "where": where, "message": msg})
    W = lambda code, where, msg: warnings.append({"code": code, "where": where, "message": msg})
    if not g["steps"]:
        E("E_EMPTY", "steps", "no steps extracted")
        return errors, warnings
    materials, equipment, steps, producer, state_out = index(g)
    Q = prepared.q
    S = prepared.s
    text_l = prepared.text.lower()

    for m in g["materials"]:
        if not m["name"]:
            E("E_MATERIAL_NAME", m["id"], "material has empty name")
        elif not _grounded(m, text_l):
            W("W_NAME_UNGROUNDED", m["id"], f"material name {m['name']!r} not found in text")

    available = set(materials)  # materials are always available; states only after production
    bindings = defaultdict(list)

    def bind(qs, where, kind_ok=None, param=None):
        for q in qs:
            if q.startswith("LIT:"):
                E("E_Q_LITERAL", where, f"{q[4:]!r} is not a tagged quantity; use a «Q» id or put it in text")
                continue
            if q not in Q:
                E("E_Q_UNKNOWN", where, f"{q} does not exist")
                continue
            bindings[q].append(where)
            if kind_ok and Q[q].kind not in kind_ok:
                E("E_Q_KIND", where, f"{q} ({Q[q].text!r}, kind {Q[q].kind}) cannot be {param}")

    for i, s in enumerate(g["steps"]):
        sid = s["id"]
        spec = ops["ops"].get(s["op"], ops["ops"]["other"])
        for sent in s["sentences"]:
            if sent not in S:
                E("E_SENTENCE", sid, f"unknown sentence {sent}")
        if not s["sentences"]:
            W("W_NO_SENTENCE", sid, "step has no sentence anchor")
        if s["surface"] and s["sentences"] and not any(_fuzzy_in(s["surface"], S[x].text) for x in s["sentences"] if x in S):
            W("W_SURFACE", sid, f"surface {s['surface']!r} not found in {s['sentences']}")
        if s["op"] == "other":
            W("W_OP_OTHER", sid, f"op_label {s['op_label']!r} not in library (curation queue)")
        # role contract
        if spec["target"] == "required" and not s["target"] and not s["vessel"]:
            E("E_ROLE_TARGET", sid, f"{s['op']} needs a target (the state/material acted on)")
        if spec["target"] == "none" and s["target"]:
            E("E_ROLE_TARGET", sid, f"{s['op']} takes no target; components go in inputs")
        if spec["inputs"] == "required" and not s["inputs"]:
            E("E_ROLE_INPUTS", sid, f"{s['op']} needs inputs")
        if spec["inputs"] == "none" and s["inputs"]:
            E("E_ROLE_INPUTS", sid, f"{s['op']} takes no inputs; use a separate add step or params")
        for role, ref in step_refs(s):
            if not ref:
                E("E_REF", sid, f"empty {role} ref")
            elif ref in equipment:
                if role == "target":
                    continue  # acting on equipment (purge a flask, seal a plate) is allowed
                E("E_REF_KIND", sid, f"{role} {ref} is equipment; put it in vessel/equipment")
            elif ref not in materials and ref not in producer:
                E("E_REF", sid, f"{role} {ref!r} is neither a material id nor a produced state id")
            elif ref in producer and ref not in available:
                E("E_USE_BEFORE_DEF", sid, f"{role} {ref} is used before step {producer[ref]} produces it; reorder steps")
        if s["target"] and s["target"] in [x["ref"] for x in s["inputs"]]:
            E("E_ROLE_SELF", sid, "target also listed as input")
        for x in s["inputs"]:
            bind(x["amounts"], f"{sid}.inputs[{x['ref']}]", AMOUNT_KINDS, "an input amount")
        for name, v in s["params"].items():
            kinds = ops["param_kinds"].get(name)
            bind(v.get("q", []), f"{sid}.params.{name}", set(kinds) if kinds else None, name)
            if not v.get("q") and not v.get("text"):
                W("W_PARAM_EMPTY", sid, f"param {name} empty")
        if s["vessel"] and s["vessel"] not in equipment:
            E("E_REF", sid, f"vessel {s['vessel']!r} not in equipment")
        for e in s["equipment"]:
            if e not in equipment:
                E("E_REF", sid, f"equipment {e!r} not defined")
        for o in s["outputs"]:
            if spec["outputs"] and o["role"] not in spec["outputs"] and s["op"] != "other":
                W("W_OUTPUT_ROLE", sid, f"output role {o['role']!r} unusual for {s['op']} (expected {spec['outputs']})")
            available.add(o["id"])
        if not s["outputs"] and spec["outputs"] and s["op"] not in ("discard", "analyze", "monitor"):
            W("W_NO_OUTPUT", sid, "step produces no state; later steps cannot reference its result")
        if s["concurrent_with"] and s["concurrent_with"] not in steps:
            E("E_REF", sid, f"concurrent_with {s['concurrent_with']} unknown")
        for a in s["after"]:
            if a not in steps:
                E("E_REF", sid, f"after {a} unknown")

    for e in g["equipment"]:
        for name, v in e["props"].items():
            bind(v.get("q", []), f"{e['id']}.props.{name}")
    for p in g["products"]:
        if p["ref"] and p["ref"] not in materials and p["ref"] not in producer:
            E("E_REF", "products", f"product ref {p['ref']!r} unknown")
        if p["state"] and p["state"] not in producer:
            E("E_REF", "products", f"product state {p['state']!r} unknown")
        bind(p["amounts"], f"product[{p['ref']}].amounts", AMOUNT_KINDS, "a product amount")
        bind(p["yield"], f"product[{p['ref']}].yield", {"percent"}, "a yield")
    for ob in g["observations"]:
        bind(ob["quantities"], "observation")
        if ob["step"] and ob["step"] not in steps:
            W("W_REF", "observation", f"observation step {ob['step']} unknown")
    for u in g["unbound"]:
        if u["q"] in Q:
            bindings[u["q"]].append("unbound")

    for q, where in bindings.items():
        real = [w for w in where if w not in ("unbound", "observation")]
        if len(set(real)) > 1:
            E("E_Q_DUP", q, f"{q} ({Q[q].text!r}) bound in several places: {sorted(set(real))}; keep one")
    for q in prepared.procedure_quantities():
        if q.id not in bindings:
            E("E_Q_UNBOUND", q.id, f"{q.id} ({q.text!r} in {q.sentence}) is not used; bind it or list it in unbound with a reason")

    try:
        topological_order(g)
    except ValueError as err:
        E("E_CYCLE", "steps", str(err))

    consumed = {r for s in g["steps"] for _, r in step_refs(s)} | {p["state"] for p in g["products"]} | {p["ref"] for p in g["products"]}
    for s in g["steps"]:
        for o in s["outputs"]:
            if o["id"] not in consumed and s is not g["steps"][-1] and o["role"] == "main":
                later = g["steps"][g["steps"].index(s) + 1:]
                if any(x["op"] not in ("analyze", "discard", "monitor") for x in later):
                    W("W_STATE_UNUSED", s["id"], f"state {o['id']} is never used later (missed coreference?)")
    return errors, warnings


def _grounded(m, text_l):
    names = [m["name"], *m["aliases"]]
    for n in names:
        n_l = _norm_name(n)
        if n_l and n_l in text_l:
            return True
        tokens = [t for t in re.split(r"[\s,()]+", n_l) if len(t) > 2]
        if tokens and sum(t in text_l for t in tokens) / len(tokens) >= 0.6:
            return True
    return False


def _fuzzy_in(needle, hay):
    n, h = _norm_name(needle), _norm_name(hay)
    if n in h:
        return True
    words = [w for w in re.split(r"\W+", n) if w]
    return bool(words) and sum(w in h for w in words) / len(words) >= 0.7
