import copy
import json
from pathlib import Path

import pytest

from mosaic.pg import llm as llm_mod
from mosaic.pg.__main__ import evaluate_dir, load_gold, main
from mosaic.pg.curate import apply, collect
from mosaic.pg.llm import LLM, LLMError, ScriptedLLM, parse_json_reply
from mosaic.pg.pipeline import Config, Extractor, render_graph, run_batch

ROOT = Path(__file__).resolve().parents[1]
GOLD = ROOT / "evaluation" / "procgraph_gold"


def gold(name):
    return json.loads((GOLD / f"{name}.json").read_text(encoding="utf-8"))


def model_form(graph):
    return {k: v for k, v in graph.items() if k not in ("schema", "source_id", "text_sha256")}


def flawed(graph):
    """Typical first-pass mistakes: composite used before it is prepared, a quantity dropped."""
    g = copy.deepcopy(model_form(graph))
    prep = [s for s in g["steps"] if s["op"] == "prepare"]
    rest = [s for s in g["steps"] if s["op"] != "prepare"]
    g["steps"] = rest[:1] + prep + rest[1:]
    g["steps"][0]["params"].pop("temperature", None)
    return g


def test_repair_loop_fixes_validator_errors():
    d = gold("syn-into-suspension")
    llm = ScriptedLLM({"extractor": [flawed(d["graph"])], "repairer": [model_form(d["graph"])]})
    res = Extractor(llm, Config(critic=False)).run(d["source_id"], d["text"])
    assert res["status"] == "ok" and res["errors"] == []
    assert [t["stage"] for t in res["trace"]] == ["extract", "repair1"]
    assert res["trace"][0]["errors"] == 1 and res["trace"][1]["accepted"] is True
    repair_prompt = llm.log[1][1]
    assert "E_Q_UNBOUND" in repair_prompt                    # the model is asked to place the dropped 0 °C
    assert "C_REORDER" in {c["code"] for c in res["coercions"]}  # the ordering mistake was fixed by the program


def test_bad_repair_is_rejected():
    d = gold("syn-into-suspension")
    worse = copy.deepcopy(model_form(d["graph"]))
    worse["steps"] = worse["steps"][2:]  # deletes the composites -> more errors
    llm = ScriptedLLM({"extractor": [model_form(d["graph"])], "critic": [{"issues": [
        {"step": "t3", "kind": "role", "severity": "critical", "problem": "x", "fix": "y"}]}], "repairer": [worse]})
    res = Extractor(llm, Config()).run(d["source_id"], d["text"])
    assert res["status"] == "ok"
    assert res["trace"][-1] == {"stage": "critic_repair", "accepted": False, "errors_before": 0,
                                "errors_after": res["trace"][-1]["errors_after"]}
    assert len(res["graph"]["steps"]) == 4


def test_critic_issue_triggers_role_fix():
    d = gold("syn-into-suspension")
    wrong = copy.deepcopy(model_form(d["graph"]))
    add = next(s for s in wrong["steps"] if s["op"] == "add")
    add["target"], add["inputs"][0]["ref"] = add["inputs"][0]["ref"], add["target"]  # reversed receiver
    issue = {"step": "t3", "kind": "role", "severity": "critical", "problem": "receiver reversed",
             "fix": "target must be the suspension x2"}
    llm = ScriptedLLM({"extractor": [wrong], "critic": [{"issues": [issue]}], "repairer": [model_form(d["graph"])]})
    res = Extractor(llm, Config()).run(d["source_id"], d["text"])
    fixed = next(s for s in res["graph"]["steps"] if s["op"] == "add")
    assert fixed["target"] == "x2"
    assert "receiver reversed" in llm.log[-1][1]
    assert "t3 [S1] ADD" in llm.log[1][1]  # critic sees the readable rendering


def test_windowed_extraction_merges_windows():
    d = gold("syn-explicit-prep")
    g = model_form(d["graph"])
    first = {"materials": g["materials"], "steps": g["steps"][:2]}
    second = {"materials": g["materials"], "steps": g["steps"][2:]}
    llm = ScriptedLLM({"extractor": [first, second]})
    res = Extractor(llm, Config(critic=False, window_sentences=2)).run(d["source_id"], d["text"])
    assert res["status"] == "ok" and len(res["graph"]["steps"]) == 4
    assert "CONTEXT FROM EARLIER SENTENCES" in llm.log[1][1] and "WINDOW: S3" in llm.log[1][1]


def test_batch_bench_end_to_end(tmp_path):
    gold_docs = load_gold(GOLD)
    answers = {sid: model_form(d["graph"]) for sid, d in gold_docs.items()}

    def reply(user):
        for sid, d in gold_docs.items():
            if d["text"][:60] in user.replace("«", "").replace("»", "") or _rendered(d) in user:
                return answers[sid]
        raise AssertionError("unknown text")

    llm = ScriptedLLM({"extractor": [reply] * len(gold_docs)})
    sources = [{"id": sid, "procedure": d["text"]} for sid, d in gold_docs.items()]
    results, summary = run_batch(sources, llm, tmp_path, Config(critic=False), workers=3, progress=lambda *_: None)
    assert summary["ok"] == len(gold_docs)
    per, agg = evaluate_dir(gold_docs, tmp_path)
    assert agg["overall"] == 1.0
    assert (tmp_path / "xdl" / "syn-into-suspension.xdl").exists()
    assert (tmp_path / "views" / "syn-into-suspension.md").read_text(encoding="utf-8").count("```mermaid") == 1
    # resumable: second run does not call the model
    llm2 = ScriptedLLM({})
    _, summary2 = run_batch(sources, llm2, tmp_path, Config(critic=False), progress=lambda *_: None)
    assert summary2["ok"] == len(gold_docs) and sum(llm2.calls.values()) == 0
    assert main(["tasks", str(tmp_path), "--n", "6"]) == 0
    items = (tmp_path / "task_items.jsonl").read_text(encoding="utf-8").splitlines()
    assert any(json.loads(i)["type"] == "order_pair" for i in items)


def _rendered(d):
    from mosaic.pg.preprocess import prepare
    return prepare(d["source_id"], d["text"]).render()[:80]


def test_curation_gate(tmp_path):
    res = {"r1": {"source_id": "r1", "prepared": {"sentences": [{"id": "S1", "text": "The vial was vortexed."}]},
                  "graph": {"equipment": [], "steps": [{"op": "other", "op_label": "vortex", "surface": "vortexed",
                                                        "sentences": ["S1"]}]}}}
    q = collect(res)
    assert q["ops"]["vortex"]["count"] == 1
    out = apply({"decisions": [
        {"label": "vortex", "decision": "alias", "op": "stir"},
        {"label": "zap", "decision": "alias", "op": "teleport"},
        {"label": "electroporate", "decision": "new", "op": "electroporate",
         "spec": {"desc": "Apply an electric pulse", "target": "required", "inputs": "none", "outputs": ["main"]}},
        {"label": "bad", "decision": "new", "op": "stir", "spec": {"desc": "dup", "target": "required", "inputs": "none"}},
    ]}, tmp_path / "ops.local.yaml")
    assert [a.get("alias_of") or a.get("new_op") for a in out["accepted"]] == ["stir", "electroporate"]
    assert len(out["rejected"]) == 2
    from mosaic.pg.ir import _lookup_op, load_ops
    ops = load_ops(str(tmp_path / "ops.local.yaml"))
    assert _lookup_op("vortex", ops) == "stir" and _lookup_op("electroporate", ops) == "electroporate"
    load_ops.cache_clear()


def test_render_graph_is_readable():
    d = gold("ord-8841b6b409c7485da9c83fc3053ea8a7")
    from mosaic.pg.preprocess import prepare
    text = render_graph(d["graph"], prepare(d["source_id"], d["text"]))
    assert "t3 [S1] ADD: target=x2<suspension>, inputs=[x1<15% sodium methylate in methanol> Q1=18 ml]" in text


# ----------------------------------------------------------------------------- HTTP client
def test_parse_json_reply_variants():
    assert parse_json_reply('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json_reply('Here you go: {"a": 1} thanks') == {"a": 1}
    assert "_invalid_json" in parse_json_reply("nope")


class _Resp:
    def __init__(self, code, body):
        self.status_code, self._body, self.text = code, body, json.dumps(body)

    def json(self):
        return self._body


RESPONSES_OK = {"id": "resp_1", "object": "response", "model": "gpt-6.1-sol",
                "output": [{"type": "reasoning", "summary": []},
                           {"type": "message", "role": "assistant",
                            "content": [{"type": "output_text", "text": '{"ok": true}'}]}],
                "usage": {"input_tokens": 10, "output_tokens": 5, "output_tokens_details": {"reasoning_tokens": 3}}}


def _env(tmp_path, **extra):
    env = tmp_path / ".env"
    lines = ['api_key="sk-test"', 'base_url="https://gw.example.com/v1"', 'model="gpt-6.1-sol"']
    lines += [f'{k}="{v}"' for k, v in extra.items()]
    env.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return env


def test_responses_api_matches_sdk_call(tmp_path, monkeypatch):
    seen = []

    def fake_post(url, json=None, timeout=None, headers=None):
        seen.append((url, json))
        if "text" in json:  # this gateway rejects JSON mode -> client drops it and retries
            return _Resp(400, {"error": {"message": "unsupported parameter: text.format"}})
        return _Resp(200, RESPONSES_OK)

    monkeypatch.setattr(llm_mod.requests, "post", fake_post)
    client = LLM(env_file=_env(tmp_path), cache_dir=tmp_path / "cache")
    reply, _ = client.json("critic", "sys", "user")
    assert reply == {"ok": True}
    url, body = seen[-1]
    assert url == "https://gw.example.com/v1/responses"
    assert body == {"model": "gpt-6.1-sol", "instructions": "sys", "input": "user", "reasoning": {"effort": "low"}}
    assert client.usage["output_tokens_details.reasoning_tokens"] == 3
    client.json("critic", "sys", "user")  # cached
    assert len(seen) == 2
    offline = LLM(env_file=_env(tmp_path), cache_dir=tmp_path / "cache", mode="replay")
    assert offline.json("critic", "sys", "user")[0] == {"ok": True}
    with pytest.raises(LLMError):
        offline.json("critic", "sys", "other")


def test_falls_back_to_chat_completions(tmp_path, monkeypatch):
    seen = []

    def fake_post(url, json=None, timeout=None, headers=None):
        seen.append(url)
        if url.endswith("/responses"):
            return _Resp(404, {})
        return _Resp(200, {"choices": [{"message": {"content": '{"ok": 1}'}}], "usage": {"total_tokens": 7}})

    monkeypatch.setattr(llm_mod.requests, "post", fake_post)
    client = LLM(env_file=_env(tmp_path, reasoning_effort="high"), cache_dir=None)
    assert client.json("extractor", "s", "u")[0] == {"ok": 1}
    assert client.api == "chat" and seen == ["https://gw.example.com/v1/responses", "https://gw.example.com/v1/chat/completions"]
    client.json("extractor", "s", "u2")
    assert seen[-1].endswith("/chat/completions") and len(seen) == 3  # remembered


def test_retries_transient_errors(tmp_path, monkeypatch):
    codes = [503, 429, 200]
    monkeypatch.setattr(llm_mod.time, "sleep", lambda *_: None)
    monkeypatch.setattr(llm_mod.requests, "post",
                        lambda url, **k: _Resp(codes.pop(0), RESPONSES_OK if not codes else {}))
    client = LLM(env_file=_env(tmp_path, api="responses"), cache_dir=None)
    assert client.json("extractor", "s", "u")[0] == {"ok": True}
