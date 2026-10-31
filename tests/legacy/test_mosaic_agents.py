from concurrent.futures import ThreadPoolExecutor
from threading import Lock
import time

import pytest

from mosaic.agents import AgentRunner, CallBudgetExceeded
from mosaic.store import RunStore


def test_parallel_identical_requests_call_model_once_and_keep_event_chain(tmp_path):
    calls, lock = [], Lock()

    class Client:
        def complete(self, system, prompt, cache=True):
            with lock:
                calls.append(prompt)
            time.sleep(.02)
            return {"data": {"ok": True}, "model": "fixture-model", "cache_key": "fixture"}

    store = RunStore(tmp_path, {"fixture": "parallel"})
    runner = AgentRunner(store, max_calls=1, client_factory=lambda model: Client())
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(lambda _: runner.model_call("critic", "fixture", {"same": 1}), range(8)))
    assert len(calls) == 1 and runner.calls == 1
    assert all(r["data"] == {"ok": True} for r in responses)
    assert store.verify()
    with pytest.raises(CallBudgetExceeded):
        runner.model_call("critic", "fixture", {"different": 2})


def test_concurrent_distinct_requests_never_exceed_shared_call_budget(tmp_path):
    class Client:
        def complete(self, *args, **kwargs):
            time.sleep(.01)
            return {"data": {}, "model": "fixture-model"}

    store = RunStore(tmp_path, {"fixture": "budget"})
    runner = AgentRunner(store, max_calls=2, client_factory=lambda model: Client())
    def call(number):
        try:
            runner.model_call("critic", "fixture", {"number": number})
            return True
        except CallBudgetExceeded:
            return False
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(call, range(8))) == 2
    assert runner.calls == 2 and store.verify()
