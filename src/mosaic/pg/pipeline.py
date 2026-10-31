"""Per-document agent loop and resumable batch runner.

    prepare (program) -> extractor (LLM) -> coerce + validate (program)
        -> [repairer (LLM) while blocking errors, max N rounds]
        -> [critic (LLM)] -> [repairer (LLM) on critic issues]
        -> compile (program): XDL, views, task data

A repair is accepted only if it does not increase the number of blocking errors,
so a bad repair can never destroy a good extraction.
"""
from __future__ import annotations

import json
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

from .ir import coerce, load_ops, status_of, validate
from .preprocess import prepare
from .prompts import CRITIC_SYSTEM, PROMPT_VERSION, REPAIR_SYSTEM, extractor_system, extractor_user


@dataclass
class Config:
    repair_rounds: int = 2
    critic: bool = True
    samples: int = 1               # >1: self-consistency; keep the candidate with fewest errors
    window_sentences: int = 40     # longer procedures are extracted in windows
    ops_extra: str | None = None   # path to locally curated ops (ops.local.yaml)
    stats: dict = field(default_factory=dict)


def render_graph(g, prepared):
    """Readable one-line-per-step rendering used by the critic (and humans)."""
    Q = prepared.q
    mats = {m["id"]: m["name"] for m in g["materials"]}
    eq = {e["id"]: e["name"] for e in g["equipment"]}
    labels = {o["id"]: (o["label"] or o["role"]) for s in g["steps"] for o in s["outputs"]}

    def ref(r):
        if r in mats:
            return f"{r}:{mats[r]}"
        if r in labels:
            return f"{r}<{labels[r]}>"
        return f"{r}?"

    def qs(ids):
        return " + ".join(f"{q}={Q[q].text}" if q in Q else q for q in ids)

    lines = []
    for s in g["steps"]:
        head = f"{s['id']} [{','.join(s['sentences'])}] {s['op'].upper()}" + (f"({s['op_label']})" if s["op_label"] else "")
        if s["origin"] == "described":
            head += " (described)"
        parts = []
        if s["target"]:
            parts.append("target=" + ref(s["target"]))
        if s["vessel"]:
            parts.append("vessel=" + eq.get(s["vessel"], s["vessel"]))
        if s["inputs"]:
            parts.append("inputs=[" + "; ".join(ref(x["ref"]) + (f" {qs(x['amounts'])}" if x["amounts"] else "")
                                               + (f" ({x['role']})" if x["role"] else "") for x in s["inputs"]) + "]")
        for k, v in s["params"].items():
            parts.append(f"{k}=" + (qs(v["q"]) if v.get("q") else repr(v.get("text", ""))))
        outs = ", ".join(f"{o['id']}<{o['label'] or o['role']}>" if o["role"] == "main" else f"{o['id']}<{o['role']}>"
                         for o in s["outputs"])
        lines.append(f"{head}: " + ", ".join(parts) + (f" -> {outs}" if outs else ""))
    for p in g["products"]:
        lines.append(f"PRODUCT {ref(p['ref'])} from {p['state']}: amounts {qs(p['amounts'])} yield {qs(p['yield'])}")
    for o in g["observations"]:
        lines.append(f"OBSERVATION [{','.join(o['sentences'])}] {o['text']} {qs(o['quantities'])}")
    for u in g["unbound"]:
        lines.append(f"UNBOUND {u['q']}: {u['reason']}")
    return "\n".join(lines)


def _score(errors, warnings):
    return (len(errors), sum(w["code"] in ("W_STATE_UNUSED", "W_NAME_UNGROUNDED", "W_OP_OTHER") for w in warnings))


class Extractor:
    def __init__(self, llm, config=None):
        self.llm = llm
        self.cfg = config or Config()
        self.ops = load_ops(self.cfg.ops_extra)
        self.system = extractor_system(prepare, self.ops)

    # ------------------------------------------------------------------ one document
    def run(self, source_id, text):
        t0 = time.monotonic()
        prepared = prepare(source_id, text)
        trace = []
        proc_sents = [s for s in prepared.sentences if s.kind == "procedure"]
        if len(proc_sents) > self.cfg.window_sentences:
            raw = self._windowed(prepared, trace)
        else:
            raw = self._sampled(prepared, trace)
        graph, log = coerce(raw, prepared, self.ops)
        errors, warnings = validate(graph, prepared, self.ops)
        trace.append({"stage": "extract", "errors": len(errors), "warnings": len(warnings), "coercions": len(log)})

        for r in range(self.cfg.repair_rounds):
            if not errors:
                break
            graph, errors, warnings, log = self._repair(prepared, graph, errors, warnings, log, [], trace, f"repair{r + 1}")

        issues = []
        if self.cfg.critic:
            reply, _ = self.llm.json("critic", CRITIC_SYSTEM,
                                     f"TEXT:\n{prepared.render()}\n\nGRAPH:\n{render_graph(graph, prepared)}\n\nJSON:")
            issues = [i for i in (reply.get("issues") or []) if isinstance(i, dict)
                      and i.get("severity", "major") in ("critical", "major")]
            trace.append({"stage": "critic", "issues": len(issues)})
            if issues:
                graph, errors, warnings, log = self._repair(prepared, graph, errors, warnings, log, issues, trace, "critic_repair")

        return {
            "source_id": source_id, "schema": "mosaic.procgraph-result/1", "prompt_version": PROMPT_VERSION,
            "text": prepared.text,
            "status": status_of(errors),
            "graph": graph, "errors": errors, "warnings": warnings, "critic_issues": issues,
            "coercions": log, "trace": trace, "prepared": prepared.as_dict(),
            "elapsed_s": round(time.monotonic() - t0, 2),
        }

    def _sampled(self, prepared, trace, user=None):
        user = user or extractor_user(prepared)
        best, best_score = None, None
        for k in range(max(1, self.cfg.samples)):
            raw, _ = self.llm.json("extractor", self.system, user, sample=k)
            if self.cfg.samples == 1:
                return raw
            g, _ = coerce(raw, prepared, self.ops)
            sc = _score(*validate(g, prepared, self.ops))
            trace.append({"stage": f"sample{k}", "score": sc})
            if best is None or sc < best_score:
                best, best_score = raw, sc
        return best

    def _windowed(self, prepared, trace):
        """Extract long procedures in sentence windows, carrying materials/states forward."""
        proc = [s for s in prepared.sentences if s.kind == "procedure"]
        size = self.cfg.window_sentences
        merged = {"materials": [], "equipment": [], "steps": [], "products": [], "observations": [], "unbound": []}
        for i in range(0, len(proc), size):
            window = proc[i:i + size]
            names = ", ".join(s.id for s in window)
            ctx = ""
            if merged["steps"]:
                g, _ = coerce(merged, prepared, self.ops)
                ctx = render_graph(g, prepared) + "\nMATERIALS: " + "; ".join(f"{m['id']}={m['name']}" for m in g["materials"])
                ctx += "\nEQUIPMENT: " + "; ".join(f"{e['id']}={e['name']}" for e in g["equipment"])
            ctx += f"\nWINDOW: {names}"
            raw = self._sampled(prepared, trace, extractor_user(prepared, ctx))
            for key in merged:
                seen = {x.get("id") for x in merged[key] if isinstance(x, dict)}
                for item in raw.get(key) or []:
                    if key in ("materials", "equipment") and isinstance(item, dict) and item.get("id") in seen:
                        continue
                    merged[key].append(item)
            trace.append({"stage": f"window{i // size + 1}", "sentences": names})
        return merged

    def _repair(self, prepared, graph, errors, warnings, log, issues, trace, stage):
        problems = [f"{e['code']} at {e['where']}: {e['message']}" for e in errors]
        problems += [f"AUDIT {i.get('kind')} ({i.get('severity')}) step {i.get('step')}: {i.get('problem')} -> {i.get('fix')}"
                     for i in issues]
        user = (f"TEXT:\n{prepared.render()}\n\nCURRENT GRAPH JSON:\n{json.dumps(_public(graph), ensure_ascii=False)}\n\n"
                f"PROBLEMS:\n" + "\n".join(problems) + "\n\nReturn the complete corrected graph JSON:")
        raw, _ = self.llm.json("repairer", REPAIR_SYSTEM, user)
        if "_invalid_json" in raw or not raw.get("steps"):
            trace.append({"stage": stage, "accepted": False, "reason": "invalid reply"})
            return graph, errors, warnings, log
        g2, log2 = coerce(raw, prepared, self.ops)
        e2, w2 = validate(g2, prepared, self.ops)
        accept = _score(e2, w2) <= _score(errors, warnings) if not issues else len(e2) <= len(errors)
        trace.append({"stage": stage, "accepted": accept, "errors_before": len(errors), "errors_after": len(e2)})
        if accept:
            return g2, e2, w2, log + log2
        return graph, errors, warnings, log


def _public(graph):
    return {k: v for k, v in graph.items() if k not in ("schema", "source_id", "text_sha256")}


# ----------------------------------------------------------------------------- batch
def load_sources(paths):
    """.txt/.md (one procedure), .json (object or list), .jsonl. Fields: id + procedure|text|notes.procedure_details."""
    out = []
    for path in map(Path, paths):
        files = sorted(path.glob("*")) if path.is_dir() else [path]
        for f in files:
            if f.suffix in (".txt", ".md"):
                out.append({"id": f.stem, "procedure": f.read_text(encoding="utf-8")})
            elif f.suffix == ".jsonl":
                for line in f.read_text(encoding="utf-8").splitlines():
                    if line.strip():
                        out.append(_record(json.loads(line)))
            elif f.suffix == ".json":
                data = json.loads(f.read_text(encoding="utf-8"))
                for rec in data if isinstance(data, list) else [data]:
                    if isinstance(rec, dict) and (rec.get("procedure") or rec.get("text") or rec.get("notes")):
                        out.append(_record(rec))
    return out


def _record(rec):
    text = rec.get("procedure") or rec.get("text") or (rec.get("notes") or {}).get("procedure_details")
    return {"id": str(rec.get("id") or rec.get("reaction_id") or rec.get("source_id")), "procedure": text}


def run_batch(sources, llm, out_dir, config=None, workers=4, compile_outputs=True, progress=print):
    from .compile import write_outputs
    out_dir = Path(out_dir)
    (out_dir / "graphs").mkdir(parents=True, exist_ok=True)
    extractor = Extractor(llm, config)
    results = {}

    def one(src):
        target = out_dir / "graphs" / f"{_safe(src['id'])}.json"
        if target.exists():
            return src["id"], json.loads(target.read_text(encoding="utf-8")), "resumed"
        try:
            res = extractor.run(src["id"], src["procedure"])
        except Exception as err:  # keep the batch going; record the failure
            res = {"source_id": src["id"], "status": "failed", "error": f"{type(err).__name__}: {err}",
                   "traceback": traceback.format_exc()[-3000:]}
        target.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
        if compile_outputs and res.get("graph"):
            try:
                write_outputs(res, out_dir)
            except Exception as err:  # outputs are derived; the graph JSON is already saved
                res["compile_error"] = f"{type(err).__name__}: {err}"
                target.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
        return src["id"], res, "done"

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = [pool.submit(one, s) for s in sources]
        for i, fut in enumerate(as_completed(futures), 1):
            sid, res, how = fut.result()
            results[sid] = res
            progress(f"[{i}/{len(sources)}] {sid}: {res.get('status')} ({how})"
                     + (f" errors={len(res.get('errors', []))}" if res.get("graph") else f" {res.get('error', '')}"))
    summary = {
        "n": len(sources), "ok": sum(r.get("status") == "ok" for r in results.values()),
        "incomplete": sum(r.get("status") == "incomplete" for r in results.values()),
        "has_errors": sum(r.get("status") == "has_errors" for r in results.values()),
        "failed": sum(r.get("status") == "failed" for r in results.values()),
        "llm_calls": dict(llm.calls), "usage": dict(llm.usage), "model": getattr(llm, "model", None),
        "prompt_version": PROMPT_VERSION,
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    return results, summary


def _safe(name):
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in str(name))[:120]
