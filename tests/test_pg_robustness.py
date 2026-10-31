"""Malformed model replies must degrade gracefully, never crash coerce/validate/compile."""
import copy
import json
import random
from pathlib import Path

from mosaic.pg.compile import write_outputs
from mosaic.pg.ir import coerce, status_of, validate
from mosaic.pg.llm import ScriptedLLM
from mosaic.pg.pipeline import Config, Extractor
from mosaic.pg.preprocess import prepare

GOLD = Path(__file__).resolve().parents[1] / "evaluation" / "procgraph_gold"


def _docs():
    for f in sorted(GOLD.glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        yield d, {k: v for k, v in d["graph"].items() if k not in ("schema", "source_id", "text_sha256")}


def _mutate(obj, rng):
    """Apply one realistic corruption somewhere in the reply."""
    g = copy.deepcopy(obj)
    steps = g.get("steps") if isinstance(g.get("steps"), list) else []
    s = rng.choice(steps) if steps else {}
    s = s if isinstance(s, dict) else {}
    kind = rng.randrange(16)
    if kind == 0 and s:
        s.pop(rng.choice(list(s)), None)                          # missing field
    elif kind == 1 and s and isinstance(s.get("inputs"), list):
        s["inputs"] = [x["ref"] if isinstance(x, dict) else x for x in s["inputs"]]       # bare id strings
    elif kind == 2 and s and isinstance(s.get("params"), dict):
        s["params"] = [{"name": k, **v} for k, v in s["params"].items() if isinstance(v, dict)]  # list-form params
    elif kind == 3 and s:
        s["target"] = {"state": s.get("target")}                   # nested ref
    elif kind == 4 and s:
        s["op"] = rng.choice(["Stirring", "charged", "evaporation", "vortexed", 42, None, ""])
    elif kind == 5 and s:
        o = s.get("outputs")
        s["outputs"] = o[0]["id"] if isinstance(o, list) and o and isinstance(o[0], dict) else "x_new"  # string output
    elif kind == 6:
        g = {"graph": g}                                           # wrapper
    elif kind == 7 and s and isinstance(s.get("inputs"), list) and s["inputs"] and isinstance(s["inputs"][0], dict):
        s["inputs"][0]["amounts"] = "25.4 g"                       # literal instead of Q id
    elif kind == 8 and s:
        s["target"] = rng.choice([m["name"] if isinstance(m, dict) else m for m in g.get("materials") or []] or ["unknown"])  # name as ref
    elif kind == 9:
        rng.shuffle(steps)                                         # arbitrary order
    elif kind == 10 and s:
        s["sentences"] = rng.choice(["S1", "S99", ["S1", "bogus"], None, 3])
    elif kind == 11:
        g["materials"] = [m["name"] if isinstance(m, dict) else m for m in g.get("materials") or []]  # names only
    elif kind == 12 and s:
        s["params"] = {"temperature": rng.choice([25, True, None, ["Q1"], {"value": "rt"}, "Q999"])}
    elif kind == 13:
        g["products"] = rng.choice(["x", [None], [{"ref": None, "yield": "91%"}]])
    elif kind == 14 and len(steps) > 1 and all(isinstance(x, dict) for x in steps[:2]):
        steps[1]["id"] = steps[0].get("id", "t1")                  # duplicate id
    elif kind == 15:
        g = rng.choice([{}, {"steps": None}, {"_invalid_json": "oops"}, []])
    return g


def test_fuzzed_replies_never_crash(tmp_path):
    rng = random.Random(7)
    n = 0
    for d, answer in _docs():
        p = prepare(d["source_id"], d["text"])
        for _ in range(30):
            bad = answer
            for _ in range(rng.randint(1, 3)):
                bad = _mutate(bad, rng) if isinstance(bad, dict) else bad
            g, _ = coerce(bad, p)
            errors, _ = validate(g, p)
            status_of(errors)
            write_outputs({"source_id": f"fuzz{n}", "graph": g, "prepared": p.as_dict(), "status": "x"}, tmp_path)
            n += 1
    assert n == 30 * len(list(GOLD.glob("*.json")))


def test_garbage_replies_end_as_has_errors_not_exceptions():
    d = next(iter(_docs()))[0]
    llm = ScriptedLLM({"extractor": [{"_invalid_json": "I cannot"}], "repairer": [{"_invalid_json": "x"}] * 3})
    res = Extractor(llm, Config()).run(d["source_id"], d["text"])
    assert res["status"] == "has_errors" and res["errors"][0]["code"] == "E_EMPTY"
