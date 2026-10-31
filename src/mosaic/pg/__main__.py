"""mosaic-pg: procedure text -> ProcGraph (material-flow graph) -> XDL / task data.

  python -m mosaic.pg ping     --env .env
  python -m mosaic.pg prepare  examples/procedure.txt
  python -m mosaic.pg extract  examples/chemistry_holdout/sources.json --out outputs/pg_run --env .env
  python -m mosaic.pg bench    --gold evaluation/procgraph_gold --out outputs/pg_bench --env .env
  python -m mosaic.pg evaluate --gold evaluation/procgraph_gold --pred outputs/pg_bench
  python -m mosaic.pg curate   outputs/pg_run --env .env
  python -m mosaic.pg tasks    outputs/pg_run
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from .evaluate import METRIC_KEYS, aggregate, score
from .pipeline import Config, load_sources, run_batch


def _llm(args):
    from .llm import LLM
    return LLM(env_file=args.env, model=args.model, cache_dir=args.cache, mode=args.mode, max_calls=args.max_calls,
               temperature=args.temperature, api=args.api, effort=args.effort)


def _common(p):
    p.add_argument("--env", default=None, help=".env with api_key, base_url, model (default ./.env)")
    p.add_argument("--model", default=None)
    p.add_argument("--cache", default="outputs/pg_cache")
    p.add_argument("--mode", default="live", choices=["live", "replay", "record"])
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--max-calls", type=int, default=None)
    p.add_argument("--temperature", type=float, default=None)
    p.add_argument("--api", default=None, choices=["auto", "responses", "chat"], help="default: .env api= or auto")
    p.add_argument("--effort", default=None, help="reasoning effort for all roles (low/medium/high/none); "
                   "default per role: extractor/repairer=medium, critic=low")
    p.add_argument("--no-critic", action="store_true")
    p.add_argument("--repair-rounds", type=int, default=2)
    p.add_argument("--samples", type=int, default=1)
    p.add_argument("--window", type=int, default=40)
    p.add_argument("--ops-extra", default=None, help="locally curated ops (ops.local.yaml)")


def _config(args):
    return Config(repair_rounds=args.repair_rounds, critic=not args.no_critic, samples=args.samples,
                  window_sentences=args.window, ops_extra=args.ops_extra)


def load_gold(path):
    gold = {}
    for f in sorted(Path(path).glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        if d.get("schema") == "mosaic.procgraph-gold/1":
            gold[d["source_id"]] = d
    return gold


def evaluate_dir(gold, pred_dir):
    results = {}
    for sid, g in gold.items():
        f = Path(pred_dir) / "graphs" / ("".join(c if c.isalnum() or c in "-_." else "_" for c in sid)[:120] + ".json")
        if not f.exists():
            results[sid] = None
            continue
        r = json.loads(f.read_text(encoding="utf-8"))
        if not r.get("graph"):
            results[sid] = None
            continue
        results[sid] = score(g, r["graph"], r["prepared"]["quantities"])
        results[sid]["status"] = r.get("status")
        results[sid]["n_errors"] = len(r.get("errors", []))
    return results, aggregate(results)


def report_md(results, agg, meta):
    lines = ["# ProcGraph benchmark", "", "```", json.dumps(meta, ensure_ascii=False, indent=1), "```", "",
             "| source | " + " | ".join(METRIC_KEYS) + " | errors |", "|---|" + "---|" * (len(METRIC_KEYS) + 1)]
    for sid, r in results.items():
        if r is None:
            lines.append(f"| {sid} | " + " | ".join("FAIL" for _ in METRIC_KEYS) + " | - |")
        else:
            lines.append(f"| {sid} | " + " | ".join(f"{r[k]:.2f}" for k in METRIC_KEYS) + f" | {r['n_errors']} |")
    lines.append("| **macro avg** | " + " | ".join(f"**{agg[k]:.2f}**" for k in METRIC_KEYS) + " | |")
    lines += ["", "## Residual differences (first items per source)", ""]
    for sid, r in results.items():
        if r and (r["errors"]["quantities"] or r["errors"]["roles"]):
            lines.append(f"### {sid}")
            for e in (r["errors"]["roles"] + r["errors"]["quantities"])[:12]:
                lines.append(f"- {e}")
    return "\n".join(lines) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(prog="mosaic-pg", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("ping")
    _common(p)
    p = sub.add_parser("prepare")
    p.add_argument("paths", nargs="+")
    p = sub.add_parser("extract")
    p.add_argument("paths", nargs="+")
    p.add_argument("--out", default="outputs/pg_run")
    _common(p)
    p = sub.add_parser("bench")
    p.add_argument("--gold", default="evaluation/procgraph_gold")
    p.add_argument("--out", default="outputs/pg_bench")
    p.add_argument("--only", nargs="*", default=None)
    _common(p)
    p = sub.add_parser("evaluate")
    p.add_argument("--gold", default="evaluation/procgraph_gold")
    p.add_argument("--pred", required=True)
    p = sub.add_parser("curate")
    p.add_argument("run_dir")
    p.add_argument("--ops-local", default="src/mosaic/pg/ops.local.yaml")
    p.add_argument("--dry-run", action="store_true")
    _common(p)
    p = sub.add_parser("tasks")
    p.add_argument("run_dir")
    p.add_argument("--n", type=int, default=12)
    args = ap.parse_args(argv)

    if args.cmd == "ping":
        llm = _llm(args)
        t = time.monotonic()
        reply, meta = llm.json("ping", "Return only JSON.", 'Return {"ok": true}')
        print(json.dumps({"reply": reply, "model": llm.model, "api": llm.api, "seconds": round(time.monotonic() - t, 2),
                          "json_mode": llm.json_mode, "usage": dict(llm.usage)}, ensure_ascii=False))
        return 0
    if args.cmd == "prepare":
        from .preprocess import prepare
        for src in load_sources(args.paths):
            p = prepare(src["id"], src["procedure"])
            print(f"=== {src['id']}\n{p.render()}\n")
        return 0
    if args.cmd == "extract":
        sources = load_sources(args.paths)
        _, summary = run_batch(sources, _llm(args), args.out, _config(args), workers=args.workers)
        print(json.dumps(summary, ensure_ascii=False, indent=1))
        return 0
    if args.cmd == "bench":
        gold = load_gold(args.gold)
        if args.only:
            gold = {k: v for k, v in gold.items() if any(o in k for o in args.only)}
        sources = [{"id": sid, "procedure": g["text"]} for sid, g in gold.items()]
        llm = _llm(args)
        t0 = time.monotonic()
        _, summary = run_batch(sources, llm, args.out, _config(args), workers=args.workers)
        results, agg = evaluate_dir(gold, args.out)
        meta = {**summary, "wall_s": round(time.monotonic() - t0, 1), "config": vars(_config(args)), "macro": agg}
        Path(args.out, "bench.json").write_text(json.dumps({"meta": meta, "per_source": results}, ensure_ascii=False, indent=1), encoding="utf-8")
        Path(args.out, "bench.md").write_text(report_md(results, agg, meta), encoding="utf-8")
        print(report_md(results, agg, meta))
        return 0
    if args.cmd == "evaluate":
        results, agg = evaluate_dir(load_gold(args.gold), args.pred)
        print(report_md(results, agg, {"pred": args.pred}))
        return 0
    if args.cmd == "curate":
        from . import curate
        results = {f.stem: json.loads(f.read_text(encoding="utf-8")) for f in Path(args.run_dir, "graphs").glob("*.json")}
        queue = curate.collect(results)
        Path(args.run_dir, "curation_queue.json").write_text(json.dumps(queue, ensure_ascii=False, indent=1), encoding="utf-8")
        print(json.dumps(queue["ops"], ensure_ascii=False, indent=1))
        if args.dry_run or not queue["ops"]:
            return 0
        decisions = curate.propose(queue, _llm(args), args.ops_extra)
        print(json.dumps(curate.apply(decisions, args.ops_local), ensure_ascii=False, indent=1))
        return 0
    if args.cmd == "tasks":
        from .perturb import sample_tasks
        from .preprocess import prepare
        out = Path(args.run_dir, "task_items.jsonl")
        with out.open("w", encoding="utf-8") as fh:
            for f in sorted(Path(args.run_dir, "graphs").glob("*.json")):
                r = json.loads(f.read_text(encoding="utf-8"))
                if not r.get("graph"):
                    continue
                p = prepare(r["source_id"], r["text"])
                for item in sample_tasks(r["graph"], p, n=args.n):
                    fh.write(json.dumps({"source_id": r["source_id"], **item}, ensure_ascii=False) + "\n")
        print(out)
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
