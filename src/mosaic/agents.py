"""Bounded specialist calls with explicit live, program and replay receipts."""
from __future__ import annotations

from collections import Counter
from threading import RLock
import time

from mosaic.protocol.api import Client, settings
from mosaic.protocol.io import digest


class MissingReplay(ValueError):
    pass


class CallBudgetExceeded(ValueError):
    pass


class AgentRunner:
    def __init__(self, store, *, models=None, max_calls=60, offline=False, client_factory=None, max_seconds=900):
        self.store = store
        self.models = models or {}
        self.max_calls, self.offline = max_calls, offline
        self.client_factory = client_factory or self._client
        self.calls = sum(e["engine"] in ("llm", "llm_failed") for e in store.manifest["events"])
        self.replayed = Counter()
        self._lock, self._requests = RLock(), {}
        self.deadline = time.monotonic() + max_seconds

    def _request_lock(self, key):
        with self._lock:
            return self._requests.setdefault(digest(key), RLock())

    @staticmethod
    def _client(model):
        config = settings()
        if model:
            config["model"] = model
        return Client(config)

    def model_call(self, role, system, payload):
        with self._request_lock(["agent", role, system, payload]):
            return self._model_call(role, system, payload)

    def _model_call(self, role, system, payload):
        model = self.models.get(role)
        request = {"role": role, "model": model, "system": system, "payload": payload}
        cached = self.store.find("agent/" + role, request)
        if cached:
            with self._lock:
                self.replayed[role] += 1
            return cached[0]
        if self.offline:
            raise MissingReplay("No saved response for role " + role)
        import json
        with self._lock:
            if self.calls >= self.max_calls:
                raise CallBudgetExceeded("Run model-call budget exhausted")
            if time.monotonic() >= self.deadline:
                raise CallBudgetExceeded("Batch wall-clock budget exhausted")
            self.calls += 1
            attempt = self.calls
        try:
            started = time.monotonic()
            client = self.client_factory(model)
            if isinstance(client, Client):
                client.deadline = self.deadline
                client.retries = 2
            response = client.complete(system, json.dumps(payload, ensure_ascii=False), cache=True)
        except Exception as error:
            self.store.save("failed/" + role, {**request, "attempt": attempt}, {"error_class": type(error).__name__,
                "transport_attempts": getattr(locals().get("client"), "transport_attempts", 0),
                "elapsed_seconds": round(time.monotonic() - started, 3)}, engine="llm_failed", model=model)
            raise
        result = {"data": response["data"], "model": response.get("model"),
                  "usage": response.get("usage", {}), "cache_key": response.get("cache_key"),
                  "transport_attempts": 0 if response.get("cache_hit") else response.get("transport_attempts", 0),
                  "elapsed_seconds": round(time.monotonic() - started, 3)}
        cached = response.get("cache_hit", False)
        if cached:
            with self._lock:
                self.calls -= 1
                self.replayed[role] += 1
        return self.store.save("agent/" + role, request, result, engine="cache_replay" if cached else "llm", model=result["model"], usage=result["usage"])

    def program(self, role, input_value, function):
        with self._request_lock(["program", role, input_value]):
            return self._program(role, input_value, function)

    def _program(self, role, input_value, function):
        cached = self.store.find("program/" + role, input_value)
        if cached:
            with self._lock:
                self.replayed[role] += 1
            return cached[0]
        output = function()
        return self.store.save("program/" + role, input_value, output, engine="program")

    def extraction_client(self):
        owner = self

        class RoleClient:
            def complete(self, system, prompt, cache=True):
                return owner.model_call("extractor", system, {"source_request": prompt})

        return RoleClient()
