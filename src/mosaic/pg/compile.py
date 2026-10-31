"""Deterministic backends from one ProcGraph.

* ``to_xdl``      XDL with Prep/Reaction/Workup/Purification sections, steps in a valid topological order.
                  A prepared composite is built in its own vessel and Transferred into the receiver, so
                  "B (made from C+D) is prepared first, then A is added" is explicit in the XDL.
* ``linear_text`` numbered human-readable protocol in execution order
* ``mermaid``     material-flow diagram
* ``ord_like``    reaction-level summary: addition stages, conditions, workup, products (ORD-style)
* ``task_view``   task-construction data: steps, dependency edges, transitive order, parallel levels, slots
"""
from __future__ import annotations

import json
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

from .ir import edges, index, load_ops, precedence_closure, step_refs, topological_order

SECTION = {
    "prepare": "Prep",
    "quench": "Workup", "extract": "Workup", "separate_phases": "Workup", "wash": "Workup", "dry": "Workup",
    "filter": "Workup", "centrifuge": "Workup", "decant": "Workup", "concentrate": "Workup", "adjust_ph": "Workup",
    "chromatograph": "Purification", "crystallize": "Purification", "distill": "Purification",
    "lyophilize": "Purification", "triturate": "Purification", "collect": "Purification",
}
SECTION_ORDER = ["Prep", "Reaction", "Workup", "Purification"]
ATTR = {"temperature": "temp", "duration": "time", "stir_speed": "stir_speed", "pressure": "pressure",
        "rate": "rate", "repeat": "repeats", "concentration": "concentration"}
AMOUNT_ATTR = {"mass": "mass", "volume": "volume", "amount": "amount", "equivalents": "equivalents",
               "relative_loading": "equivalents", "concentration": "concentration"}


class _Ctx:
    def __init__(self, g, prepared_q=None):
        self.g = g
        self.Q = prepared_q or {}
        self.materials, self.equipment, self.steps, self.producer, self.state_out = index(g)
        self.vessel_of = {}
        self.counter = 0

    def name(self, ref):
        if ref in self.materials:
            return self.materials[ref]["name"]
        if ref in self.state_out:
            o = self.state_out[ref]
            return o["label"] or (f"{o['role']} {ref}" if o["role"] != "main" else f"mixture {ref}")
        if ref in self.equipment:
            return self.equipment[ref]["name"]
        return ref

    def qtext(self, ids):
        return ", ".join(self.Q[q]["text"] if q in self.Q else q for q in ids)

    def new_vessel(self, hint="vessel"):
        self.counter += 1
        return f"{hint}_{self.counter}"


def _q(prepared):
    if prepared is None:
        return {}
    if isinstance(prepared, dict):
        return {q["id"]: q for q in prepared.get("quantities", [])}
    return {q.id: q.as_dict() for q in prepared.quantities}


def _fmt(q):
    if q.get("value") is None:
        return q["text"]
    unit = {"degC": "°C", "uL": "µL", "umol": "µmol", "ug": "µg", "equiv": "equiv"}.get(q["unit"], q["unit"])
    v = f"{q['value']:g}"
    return f"{v} {unit}"


def _section_plan(g, order):
    """Monotone section assignment in execution order; hoist pure-material prepare steps into Prep."""
    steps = {s["id"]: s for s in g["steps"]}
    materials = {m["id"] for m in g["materials"]}
    hoist = [sid for sid in order if steps[sid]["op"] == "prepare"
             and all(r in materials for _, r in step_refs(steps[sid]))]
    rest = [sid for sid in order if sid not in hoist]
    plan = [(sid, "Prep") for sid in hoist]
    current = "Reaction"
    for sid in rest:
        sec = SECTION.get(steps[sid]["op"], "Reaction")
        if sec == "Prep":
            sec = "Reaction"  # a prepare that needs an earlier state stays in place
        if SECTION_ORDER.index(sec) > SECTION_ORDER.index(current):
            current = sec
        plan.append((sid, current))
    return plan


def to_xdl(g, prepared=None):
    ops = load_ops()
    ctx = _Ctx(g, _q(prepared))
    order = topological_order(g)
    plan = _section_plan(g, order)
    mapping = []
    sections = {k: [] for k in SECTION_ORDER}

    def vessel_for(step):
        if step["vessel"]:
            return step["vessel"]
        if step["target"]:
            t = step["target"]
            if t in ctx.vessel_of:
                return ctx.vessel_of[t]
            if t in ctx.equipment:
                return t
            v = ctx.new_vessel("vessel")
            ctx.vessel_of[t] = v
            return v
        return ctx.new_vessel("prep_vessel" if step["op"] == "prepare" else "vessel")

    def attrs(d):
        return " ".join(f"{k}={quoteattr(str(v))}" for k, v in d.items() if v not in (None, ""))

    def params_attrs(step):
        out, notes = {}, []
        for name, v in step["params"].items():
            if v.get("q"):
                qs = [ctx.Q[q] for q in v["q"] if q in ctx.Q]
                if name in ATTR and qs:
                    out[ATTR[name]] = _fmt(qs[0])
                    if qs[0].get("upper") is not None or len(qs) > 1:
                        notes.append(f"{name}: {ctx.qtext(v['q'])}")
                else:
                    notes.append(f"{name}: {ctx.qtext(v['q'])}")
            elif v.get("text"):
                if name == "method" and v["text"].lower() == "dropwise":
                    out["dropwise"] = "true"
                elif name == "stirring":
                    out["stir"] = "true"
                else:
                    notes.append(f"{name}: {v['text']}")
        return out, notes

    def amount_attrs(amounts):
        out = {}
        for q in amounts:
            if q in ctx.Q:
                key = AMOUNT_ATTR.get(ctx.Q[q]["kind"])
                if key and key not in out:
                    out[key] = _fmt(ctx.Q[q])
        return out

    for sid, sec in plan:
        s = ctx.steps[sid]
        spec = ops["ops"].get(s["op"], {})
        xdl = spec.get("xdl")
        v = vessel_for(s)
        for o in s["outputs"]:
            if o["role"] in ("main", "solid", "organic", "pellet", "residue"):
                ctx.vessel_of[o["id"]] = v
            else:
                ctx.vessel_of[o["id"]] = ctx.new_vessel(o["role"])
        p_attrs, notes = params_attrs(s)
        if s["op"] == "prepare":
            notes = [f"{k}: {ctx.qtext(val['q']) if val.get('q') else val.get('text', '')}" for k, val in s["params"].items()]
        lines = []
        prov = f"{sid} {s['op']}" + (" (described; preparation not reported)" if s["origin"] == "described" else "")
        lines.append(f"<!-- {escape(prov)}" + (f" | {escape('; '.join(notes))}" if notes else "") + " -->")
        if s["op"] in ("prepare", "add", "dilute", "quench", "adjust_ph", "precipitate", "suspend", "dissolve", "transfer"):
            for x in s["inputs"]:
                a = amount_attrs(x["amounts"])
                if x["ref"] in ctx.state_out:  # a prepared composite / earlier state is moved into the receiver
                    lines.append(f"<Transfer {attrs({'from_vessel': ctx.vessel_of.get(x['ref'], x['ref']), 'to_vessel': v, **{k: a[k] for k in a if k == 'volume'}, **p_attrs})}/>")
                else:
                    step_name = "Dissolve" if s["op"] == "dissolve" else "Add"
                    extra = {"solvent": ctx.name(x["ref"])} if step_name == "Dissolve" else {"reagent": ctx.name(x["ref"])}
                    lines.append(f"<{step_name} {attrs({'vessel': v, **extra, **a, **(p_attrs if s['op'] != 'prepare' else {})})}/>")
            if s["op"] == "dissolve" and not s["inputs"]:
                lines.append(f"<Dissolve {attrs({'vessel': v, **p_attrs})}/>")
        elif xdl:
            extra = {}
            if s["op"] == "filter":
                filt = next((o for o in s["outputs"] if o["role"] == "filtrate"), None)
                if filt:
                    extra["filtrate_vessel"] = ctx.vessel_of[filt["id"]]
            if s["op"] in ("wash", "dry", "crystallize") and s["inputs"]:
                key = {"wash": "solvent", "dry": "drying_agent", "crystallize": "solvent"}[s["op"]]
                extra[key] = ", ".join(ctx.name(x["ref"]) for x in s["inputs"])
                for x in s["inputs"]:
                    extra.update({k: val for k, val in amount_attrs(x["amounts"]).items() if k == "volume"})
            if s["op"] in ("extract", "separate_phases"):
                extra = {"from_vessel": v, "separation_vessel": v}
                org = next((o for o in s["outputs"] if o["role"] == "organic"), None)
                aq = next((o for o in s["outputs"] if o["role"] == "aqueous"), None)
                if org:
                    extra["to_vessel"] = ctx.vessel_of[org["id"]]
                if aq:
                    extra["waste_phase_to_vessel" if org else "to_vessel"] = ctx.vessel_of[aq["id"]]
                if s["inputs"]:
                    extra["solvent"] = ", ".join(ctx.name(x["ref"]) for x in s["inputs"])
                lines.append(f"<{xdl} {attrs({**extra, **p_attrs})}/>")
            else:
                if s["op"] in ("heat", "reflux", "cool", "react") and "temp" not in p_attrs:
                    p_attrs["temp"] = "reflux" if s["op"] == "reflux" else ""
                lines.append(f"<{xdl} {attrs({'vessel': v, **extra, **p_attrs})}/>")
        else:
            label = s["op_label"] or s["op"]
            lines.append(f"<!-- no XDL step for '{escape(label)}' on {escape(v)}; kept in companion JSON -->")
        sections[sec].extend(lines)
        mapping.append({"step": sid, "section": sec, "vessel": v, "origin": s["origin"], "xdl": xdl})

    hardware = sorted({v for _, sec in plan for v in [m["vessel"] for m in mapping]} | set(ctx.vessel_of.values())
                      | {e["id"] for e in g["equipment"]})
    comp = []
    for h in hardware:
        e = ctx.equipment.get(h)
        comp.append(f'    <Component id={quoteattr(h)} type={quoteattr(e["type"] if e else "reactor")}'
                    + (f' name={quoteattr(e["name"])}' if e else "") + "/>")
    reagents = "\n".join(f"    <Reagent name={quoteattr(m['name'])}/>" for m in g["materials"])
    body = []
    for sec in SECTION_ORDER:
        if sections[sec]:
            body.append(f"    <{sec}>\n" + "\n".join("      " + l for l in sections[sec]) + f"\n    </{sec}>")
    xml = ("<?xml version=\"1.0\" encoding=\"utf-8\"?>\n<XDL>\n  <Synthesis>\n  <Hardware>\n" + "\n".join(comp)
           + "\n  </Hardware>\n  <Reagents>\n" + reagents + "\n  </Reagents>\n  <Procedure>\n" + "\n".join(body)
           + "\n  </Procedure>\n  </Synthesis>\n</XDL>\n")
    return xml, mapping


def linear_text(g, prepared=None):
    ctx = _Ctx(g, _q(prepared))
    order = topological_order(g)
    num = {sid: i for i, sid in enumerate(order, 1)}
    out = []
    for sid in order:
        s = ctx.steps[sid]
        parts = [s["op"].replace("_", " ").upper() + (f" ({s['op_label']})" if s["op_label"] else "")]
        if s["origin"] == "described":
            parts.append("[described in text]")
        if s["target"]:
            src = ctx.producer.get(s["target"])
            parts.append(f"on {ctx.name(s['target'])}" + (f" (from step {num[src]})" if src else ""))
        if s["inputs"]:
            ins = []
            for x in s["inputs"]:
                src = ctx.producer.get(x["ref"])
                t = ctx.name(x["ref"]) + (f" (from step {num[src]})" if src else "")
                if x["amounts"]:
                    t += f" [{ctx.qtext(x['amounts'])}]"
                ins.append(t)
            parts.append(("with " if s["op"] != "prepare" else "from ") + "; ".join(ins))
        if s["vessel"]:
            parts.append(f"in {ctx.name(s['vessel'])}")
        for k, v in s["params"].items():
            parts.append(f"{k}: " + (ctx.qtext(v["q"]) if v.get("q") else v.get("text", "")))
        outs = [(o["label"] + (f" ({o['role']})" if o["role"] != "main" else "")) if o["label"] else
                (o["role"] if o["role"] != "main" else "") for o in s["outputs"]]
        outs = [o for o in outs if o]
        line = f"{num[sid]}. " + ", ".join(parts) + (f" → {', '.join(outs)}" if outs and any(outs) else "")
        out.append(line)
    for p in g["products"]:
        out.append(f"Product: {ctx.name(p['ref'])}" + (f" {ctx.qtext(p['amounts'])}" if p["amounts"] else "")
                   + (f", yield {ctx.qtext(p['yield'])}" if p["yield"] else "") + (f", {p['form']}" if p["form"] else ""))
    return "\n".join(out)


def mermaid(g, prepared=None):
    ctx = _Ctx(g, _q(prepared))
    lines = ["flowchart TD"]
    used_mats = set()
    safe = lambda t: t.replace('"', "'")[:60]
    for s in g["steps"]:
        style = "{{" if s["origin"] == "described" else "["
        close = "}}" if s["origin"] == "described" else "]"
        label = s["op"] + (f": {s['op_label']}" if s["op_label"] else "")
        ps = [f"{k}={ctx.qtext(v['q']) if v.get('q') else v.get('text','')}" for k, v in s["params"].items()][:3]
        lines.append(f'  {s["id"]}{style}"{safe(label)}' + (f"<br/>{safe('; '.join(ps))}" if ps else "") + f'"{close}')
        for role, ref in step_refs(s):
            amt = ""
            if role == "input":
                x = next(x for x in s["inputs"] if x["ref"] == ref)
                amt = ctx.qtext(x["amounts"])
            edge_label = ("receiver" if role == "target" else "add") + (f" {amt}" if amt else "")
            if ref in ctx.producer:
                o = ctx.state_out[ref]
                tag = o["role"] if o["role"] != "main" else (o["label"] or "")
                lines.append(f'  {ctx.producer[ref]} -->|"{safe(tag + " / " + edge_label if tag else edge_label)}"| {s["id"]}')
            elif ref in ctx.materials:
                used_mats.add(ref)
                lines.append(f'  {ref} -->|"{safe(edge_label)}"| {s["id"]}')
    for m in sorted(used_mats):
        lines.insert(1, f'  {m}(["{safe(ctx.materials[m]["name"])}"])')
    for a, b, k in edges(g):
        if k in ("sequence", "after"):
            lines.append(f"  {a} -.-> {b}")
    return "\n".join(lines)


def ord_like(g, prepared=None):
    """Reaction-level summary grouped by addition stage (compatible with ORD-style inputs/conditions/outcomes)."""
    ctx = _Ctx(g, _q(prepared))
    order = topological_order(g)
    stages, conditions, workup, k = [], [], [], 0
    for sid in order:
        s = ctx.steps[sid]
        if s["op"] in ("add", "prepare", "dissolve", "suspend") and s["inputs"]:
            k += 1
            comps = []
            for x in s["inputs"]:
                if x["ref"] in ctx.materials:
                    comps.append({"name": ctx.name(x["ref"]), "amounts": [ctx.Q[q]["text"] for q in x["amounts"] if q in ctx.Q],
                                  "role": x["role"]})
                else:
                    comps.append({"state": ctx.name(x["ref"]), "from_step": ctx.producer.get(x["ref"]),
                                  "amounts": [ctx.Q[q]["text"] for q in x["amounts"] if q in ctx.Q]})
            stages.append({"stage": k, "step": sid, "op": s["op"], "origin": s["origin"],
                           "into": ctx.name(s["target"]) if s["target"] else None, "components": comps,
                           "conditions": {n: (ctx.qtext(v["q"]) if v.get("q") else v.get("text")) for n, v in s["params"].items()}})
        elif s["op"] in ("heat", "stir", "reflux", "cool", "wait", "react", "inert", "irradiate"):
            conditions.append({"step": sid, "op": s["op"],
                               **{n: (ctx.qtext(v["q"]) if v.get("q") else v.get("text")) for n, v in s["params"].items()}})
        elif SECTION.get(s["op"]) in ("Workup", "Purification"):
            workup.append({"step": sid, "op": s["op"], "with": [ctx.name(x["ref"]) for x in s["inputs"]],
                           **{n: (ctx.qtext(v["q"]) if v.get("q") else v.get("text")) for n, v in s["params"].items()}})
    products = [{"name": ctx.name(p["ref"]), "amounts": [ctx.Q[q]["text"] for q in p["amounts"] if q in ctx.Q],
                 "yield": [ctx.Q[q]["text"] for q in p["yield"] if q in ctx.Q], "form": p["form"]} for p in g["products"]]
    return {"addition_stages": stages, "conditions": conditions, "workup": workup, "products": products}


def task_view(g, prepared=None):
    """Everything a task builder needs, with no text parsing left to do."""
    ctx = _Ctx(g, _q(prepared))
    order = topological_order(g)
    preds = {}
    for a, b, _ in edges(g):
        preds.setdefault(b, set()).add(a)
    level = {}
    for sid in order:
        level[sid] = 1 + max((level[p] for p in preds.get(sid, ())), default=-1)
    groups = {}
    for sid, lv in level.items():
        groups.setdefault(lv, []).append(sid)
    slots = []
    for s in g["steps"]:
        for x in s["inputs"]:
            for q in x["amounts"]:
                slots.append({"q": q, "step": s["id"], "slot": "input_amount", "of": ctx.name(x["ref"]),
                              "text": ctx.Q.get(q, {}).get("text"), "kind": ctx.Q.get(q, {}).get("kind")})
        for n, v in s["params"].items():
            for q in v.get("q", []):
                slots.append({"q": q, "step": s["id"], "slot": n, "text": ctx.Q.get(q, {}).get("text"),
                              "kind": ctx.Q.get(q, {}).get("kind")})
    return {
        "execution_order": order,
        "edges": [{"from": a, "to": b, "kind": k} for a, b, k in edges(g)],
        "must_precede": sorted([list(p) for p in precedence_closure(g)]),
        "parallel_levels": [sorted(v, key=order.index) for _, v in sorted(groups.items())],
        "steps": [{"id": sid, "op": ctx.steps[sid]["op"], "origin": ctx.steps[sid]["origin"],
                   "sentences": ctx.steps[sid]["sentences"]} for sid in order],
        "quantity_slots": slots,
        "linear_text": linear_text(g, prepared).splitlines(),
    }


def write_outputs(result, out_dir):
    from .ir import index as _i  # noqa: F401
    out_dir = Path(out_dir)
    sid = "".join(c if c.isalnum() or c in "-_." else "_" for c in result["source_id"])[:120]
    g, prepared = result["graph"], result.get("prepared")
    try:
        xml, mapping = to_xdl(g, prepared)
    except ValueError as err:  # cycle
        xml, mapping = f"<!-- not compiled: {escape(str(err))} -->\n", []
    for sub in ("xdl", "views", "tasks"):
        (out_dir / sub).mkdir(parents=True, exist_ok=True)
    (out_dir / "xdl" / f"{sid}.xdl").write_text(xml, encoding="utf-8")
    try:
        view = (f"# {result['source_id']}\n\nstatus: {result.get('status')}\n\n## Protocol (execution order)\n\n"
                + linear_text(g, prepared) + "\n\n## Material flow\n\n```mermaid\n" + mermaid(g, prepared) + "\n```\n")
        tasks = {"source_id": result["source_id"], "ord_like": ord_like(g, prepared), **task_view(g, prepared),
                 "xdl_mapping": mapping}
    except ValueError as err:
        view, tasks = f"# {result['source_id']}\n\nnot rendered: {err}\n", {"error": str(err)}
    (out_dir / "views" / f"{sid}.md").write_text(view, encoding="utf-8")
    (out_dir / "tasks" / f"{sid}.json").write_text(json.dumps(tasks, ensure_ascii=False, indent=1), encoding="utf-8")
